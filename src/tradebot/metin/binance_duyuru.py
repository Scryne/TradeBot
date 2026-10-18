"""Binance duyuru toplayıcısı (CMS API, anahtarsız; Spike 03).

- Liste: katalog başına en yeni 20 duyuru (`pageSize` 20; küçük değerler 400 döndürüyor).
- Gövde: detay uç noktası, zengin metin JSON ağacı → düz metin.
- Zaman (kural 9): `releaseDate` = ilk yayın zamanı. Sonradan güncellenen duyuruda yeni sürüm yeni ham kayıttır ama
  `metin` satırı ilk yayın zamanını korur.
- Ham yanıt değişmez: HamDepo'ya yazılır, `metin.ham_sha` onun hash'idir.
"""
from __future__ import annotations

import json
import time

from sqlalchemy import insert, select
from sqlalchemy.engine import Engine

from tradebot.db import metin
from tradebot.kayit import log
from tradebot.veri.depo import HamDepo
from tradebot.veri.http import NazikIstemci

LISTE = "https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
DETAY = "https://www.binance.com/bapi/composite/v1/public/cms/article/detail/query"
KATALOGLAR = {161: "delist", 157: "bakim", 49: "haber", 48: "listeleme"}
BLOK = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "tr", "br", "div", "table", "ul", "ol"}
_log = log("metin.binance")


def govde_metni(govde_json: str) -> str:
    """Zengin metin ağacı → düz metin (blok öğeleri satır sonuyla ayrılır)."""
    try:
        kok = json.loads(govde_json)
    except (json.JSONDecodeError, TypeError):
        return str(govde_json or "")
    parca: list[str] = []

    def gez(d) -> None:
        if isinstance(d, dict):
            if d.get("node") == "text":
                parca.append(d.get("text", ""))
            for c in d.get("child", []) or []:
                gez(c)
            if d.get("tag") in BLOK:
                parca.append("\n")
        elif isinstance(d, list):
            for c in d:
                gez(c)

    gez(kok)
    satirlar = (" ".join(s.split()) for s in "".join(parca).split("\n"))
    return "\n".join(s for s in satirlar if s)


class BinanceDuyuru:
    KAYNAK = "binance_duyuru"

    def __init__(self, ham: HamDepo, motor: Engine, http: NazikIstemci | None = None) -> None:
        self.ham, self.motor = ham, motor
        # Ölçüm (2026-09-26): 0,5 sn aralıkla ~120 detay isteğinden sonra 429 → 2 sn aralık, uzun geri çekilme
        self.http = http or NazikIstemci("binance_cms", aralik_sn=2.0, deneme=8, geri_cekilme_sn=5.0,
                                         basliklar={"User-Agent": "Mozilla/5.0"})

    def liste(self, katalog: int, sayfa: int = 1) -> list[dict]:
        d = json.loads(self.http.al(LISTE, {"type": 1, "catalogId": katalog, "pageNo": sayfa, "pageSize": 20}))
        cats = (d.get("data") or {}).get("catalogs")
        if not cats:   # API biçimi değişti ya da boş yanıt: başarı sayılırsa A1 sessizce durur, nabız kör demezdi
            raise RuntimeError(f"Binance duyuru listesi boş/biçim dışı (katalog {katalog})")
        return cats[0].get("articles", [])

    def bilinen(self, kodlar: list[str]) -> set[str]:
        if not kodlar:
            return set()
        with self.motor.connect() as b:
            return set(b.execute(select(metin.c.dis_kimlik).where(metin.c.kaynak == "binance_duyuru",
                                                                  metin.c.dis_kimlik.in_(kodlar))).scalars())

    def topla(self, katalog_idleri: list[int] | None = None, sayfa_sayisi: int = 1) -> list[int]:
        """Yeni duyuruları indirip `metin`'e yazar. `sayfa_sayisi` > 1: geçmişi doldurur (boş sayfada durur).
        Döndürür: yeni metin id'leri (yayın zamanına göre sıralı)."""
        yeni: list[tuple[int, int]] = []
        for kid, sayfa in ((k, s) for k in (katalog_idleri or list(KATALOGLAR)) for s in range(1, sayfa_sayisi + 1)):
            makaleler = self.liste(kid, sayfa)
            if not makaleler:
                continue
            bilinen = self.bilinen([m["code"] for m in makaleler])
            for m in makaleler:
                if m["code"] in bilinen:
                    continue
                try:
                    ham = self.http.al(DETAY, {"articleCode": m["code"]})
                except Exception as e:  # noqa: BLE001 — bu duyuru sonraki turda yeniden denenir
                    _log.warning("duyuru_alinamadi", kod=m["code"], hata=str(e)[:200])
                    continue
                _, sha, _ = self.ham.kaydet("binance_duyuru", f"{m['code']}", ham, "json")
                d = json.loads(ham).get("data") or {}
                satir = {"kaynak": "binance_duyuru", "dis_kimlik": m["code"], "katalog": KATALOGLAR.get(kid, str(kid)),
                         "baslik": (d.get("title") or m.get("title") or "")[:1000], "govde": govde_metni(d.get("body")),
                         "yayin_ms": int(m.get("releaseDate") or d.get("publishDate") or 0),
                         "ilk_gorulme_ms": int(time.time() * 1000), "ham_sha": sha}
                with self.motor.begin() as b:
                    mid = b.execute(insert(metin).values(**satir)).inserted_primary_key[0]
                yeni.append((satir["yayin_ms"], int(mid)))
                bilinen.add(m["code"])
                _log.info("yeni_duyuru", katalog=satir["katalog"], baslik=satir["baslik"][:120])
        return [i for _, i in sorted(yeni)]

    def canli(self, ayar: dict) -> list[int]:
        """Servis turu: her kataloğun ilk sayfası."""
        return self.topla(ayar["binance"]["kataloglar"], 1)
