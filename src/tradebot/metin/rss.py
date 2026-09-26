"""RSS/Atom toplayıcısı (kripto basını, merkez bankaları, düzenleyiciler; Spike 03).

- Akış listesi `config/zeka.yaml` `rss`'te: `{ad, url, katalog, aralik_dk}`. Kaynak adı `rss:<ad>`.
- Akışlar yalnız son 15–35 öğeyi verir, geçmiş yoktur: toplama erken başlar ki C özellikleri için veri birikir.
- Zaman (kural 9): RSS `pubDate` / Atom `published` = ilk yayın zamanı (Atom `updated` yalnız `published` yoksa).
  Zaman damgası olmayan öğe atlanır ve log'a yazılır: ilk görülme anı yayın zamanı yerine geçemez.
- Gövde: akıştaki özet/içerik (HTML → düz metin). `sayfa: true` olan akışta (merkez bankaları: akış yalnız başlık
  veriyor) bağlantıdaki sayfa indirilir, `<p>` paragrafları gövde olur. Kripto basınında sayfa indirilmez.
- Ham: öğenin XML parçası (sayfa indirildiyse sayfa da) HamDepo'ya yazılır, `metin.ham_sha` gövdenin kaynağının hash'idir.
"""
from __future__ import annotations

import hashlib
import html
import re
import time
import xml.etree.ElementTree as ET
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

from sqlalchemy import insert, select
from sqlalchemy.engine import Engine

from tradebot.db import metin
from tradebot.kayit import log
from tradebot.veri.depo import HamDepo
from tradebot.veri.http import NazikIstemci

_log = log("metin.rss")
ATOM = "{http://www.w3.org/2005/Atom}"
ICERIK = "{http://purl.org/rss/1.0/modules/content/}encoded"


def duz_metin(h: str | None) -> str:
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", h or "", flags=re.S | re.I)
    t = re.sub(r"<br\s*/?>|</p>|</div>|</li>|</h\d>", "\n", t, flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    satirlar = (" ".join(s.split()) for s in t.split("\n"))
    return "\n".join(s for s in satirlar if s)


def zaman_ms(s: str | None) -> int | None:
    s = (s or "").strip()
    if not s:
        return None
    try:
        d = parsedate_to_datetime(s)
    except (TypeError, ValueError):
        try:
            d = datetime.fromisoformat(s.replace("Z", "+00:00"))
        except ValueError:
            return None
    if d.tzinfo is None:
        return None  # saat dilimi yoksa yayın anı belirsiz: atla (kural 11)
    return int(d.astimezone(UTC).timestamp() * 1000)


def _metin(e: ET.Element, *yollar: str) -> str | None:
    for y in yollar:
        x = e.find(y)
        if x is not None and (x.text or "").strip():
            return x.text.strip()
    return None


def ogeler(xml: bytes) -> list[dict]:
    """Akış → [{kimlik, baslik, govde, yayin_ms, ham}] (yayin_ms None olabilir)."""
    kok = ET.fromstring(xml)
    out = []
    for e in kok.iter("item"):
        link = _metin(e, "link")
        out.append({"kimlik": _metin(e, "guid") or link, "baslik": _metin(e, "title") or "",
                    "govde": duz_metin(_metin(e, ICERIK, "description")), "yayin_ms": zaman_ms(_metin(e, "pubDate")),
                    "link": link, "ham": ET.tostring(e, encoding="utf-8")})
    for e in kok.iter(f"{ATOM}entry"):
        ln = e.find(f"{ATOM}link")
        link = ln.get("href") if ln is not None else None
        out.append({"kimlik": _metin(e, f"{ATOM}id") or link, "baslik": duz_metin(_metin(e, f"{ATOM}title")),
                    "govde": duz_metin(_metin(e, f"{ATOM}content", f"{ATOM}summary")),
                    "yayin_ms": zaman_ms(_metin(e, f"{ATOM}published", f"{ATOM}updated")), "link": link,
                    "ham": ET.tostring(e, encoding="utf-8")})
    return out


def paragraflar(sayfa_html: str) -> str:
    """Sayfanın `<p>` paragrafları (gezinme ve alt bilgi çoğunlukla `<p>` dışında)."""
    ps = re.findall(r"<p\b[^>]*>(.*?)</p>", sayfa_html, flags=re.S | re.I)
    return "\n".join(t for t in (duz_metin(p).replace("\n", " ") for p in ps) if len(t) > 1)


def bolge(h: str, isaret: list[str] | None) -> str:
    """[baş, son] işaretleri arasındaki HTML (içerik bölgesi; gezinme ve çerez metni dışarıda). Bulunamazsa tamamı."""
    if not isaret:
        return h
    i = h.find(isaret[0])
    j = h.find(isaret[1], max(i, 0))
    return h[max(i, 0): j if j > 0 else None]


def dis_kimlik(k: str) -> str:
    return k if len(k) <= 128 else "sha1:" + hashlib.sha1(k.encode()).hexdigest()


class RssToplayici:
    KAYNAK = "rss"

    def __init__(self, ham: HamDepo, motor: Engine, akislar: list[dict], http: NazikIstemci | None = None) -> None:
        self.ham, self.motor, self.akislar = ham, motor, akislar
        self.http = http or NazikIstemci("rss", aralik_sn=1.0, deneme=3, geri_cekilme_sn=5.0,
                                         basliklar={"User-Agent": "Mozilla/5.0"})
        self._son: dict[str, float] = {}

    def akis_topla(self, a: dict) -> list[int]:
        kaynak, ham_kaynak = f"rss:{a['ad']}", f"rss_{a['ad']}"  # ham depo: klasör adında ":" olmaz
        yeni: list[tuple[int, int]] = []
        oler = [o for o in ogeler(self.http.al(a["url"])) if o["kimlik"]]
        with self.motor.connect() as b:
            bilinen = set(b.execute(select(metin.c.dis_kimlik).where(
                metin.c.kaynak == kaynak, metin.c.dis_kimlik.in_([dis_kimlik(o["kimlik"]) for o in oler]))).scalars())
        for o in oler:
            dk = dis_kimlik(o["kimlik"])
            if dk in bilinen:
                continue
            if o["yayin_ms"] is None:
                _log.warning("zamansiz_oge", kaynak=kaynak, baslik=o["baslik"][:120])
                continue
            anahtar = hashlib.sha1(dk.encode()).hexdigest()
            _, sha, _ = self.ham.kaydet(ham_kaynak, anahtar, o["ham"], "xml")
            govde = o["govde"]
            if a.get("sayfa") and o["link"]:
                try:
                    sayfa = self.http.al(o["link"])
                except Exception as e:  # noqa: BLE001 — öğe sonraki turda yeniden denenir
                    _log.warning("sayfa_alinamadi", kaynak=kaynak, link=o["link"], hata=str(e)[:200])
                    continue
                _, sha, _ = self.ham.kaydet(ham_kaynak, f"{anahtar}_sayfa", sayfa, "html")
                govde = paragraflar(bolge(sayfa.decode("utf-8", "ignore"), a.get("bolge"))) or govde
            satir = {"kaynak": kaynak, "dis_kimlik": dk, "katalog": a.get("katalog"), "baslik": o["baslik"][:1000],
                     "govde": govde, "yayin_ms": o["yayin_ms"], "ilk_gorulme_ms": int(time.time() * 1000),
                     "ham_sha": sha, "meta": {"link": o["link"]}}
            with self.motor.begin() as b:
                mid = b.execute(insert(metin).values(**satir)).inserted_primary_key[0]
            yeni.append((o["yayin_ms"], int(mid)))
            bilinen.add(dk)
        return [i for _, i in sorted(yeni)]

    def canli(self, ayar: dict) -> list[int]:
        """Servis turu: aralığı dolmuş akışlar. Bir akışın hatası diğerlerini durdurmaz."""
        yeni: list[int] = []
        for a in self.akislar:
            if time.monotonic() - self._son.get(a["ad"], -1e9) < float(a.get("aralik_dk", 10)) * 60:
                continue
            self._son[a["ad"]] = time.monotonic()
            try:
                yeni += self.akis_topla(a)
            except Exception as e:  # noqa: BLE001
                _log.warning("akis_hatasi", akis=a["ad"], hata=f"{type(e).__name__}: {e}"[:200])
        return yeni
