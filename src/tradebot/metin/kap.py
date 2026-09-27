"""KAP bildirim toplayıcısı (kap.org.tr, anahtarsız; Spike 03/04).

- Liste: `api/disclosure/members/byCriteria` (POST), gün başına tek istek, bütün BIST şirketleri (`memberType` IGS).
  Sitenin kendi bildirim sorgu sayfasının çağrısı (2026-09-26 ölçüldü: sıradan bir günde ~290 bildirim).
- Gövde: `tr/Bildirim/<no>` sayfası. Next.js akış verisindeki `disclosureBody` referansı (`<ref>:T<uzunluk>,<html>`)
  çözülür, HTML düz metne çevrilir. Başa "Özet Bilgi" eklenir (Spike 04'te ölçülen metin biçimine yakın).
- Konu listesi `ATLA`'daki bildirimlerin gövdesi indirilmez ve Jev'e sorulmaz: tanım gereği veto olamazlar (devre kesici
  = geçici durdurma, "Temerrüt İşlemi" = yatırımcının takas temerrüdü, içeriden pay alım satımı, borçlanma aracı ihracı…).
  Liste kaydı yine `metin`'e yazılır (yalnız özetle); bu, hacmin yarısından fazlasını eler.
- Zaman (kural 9, 11): `publishDate` Türkiye saatidir → UTC. İlk yayın zamanıdır.
- Ham yanıt değişmez: HamDepo'ya yazılır, `metin.ham_sha` onun hash'idir.
"""
from __future__ import annotations

import html
import json
import re
import time
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import insert, select
from sqlalchemy.engine import Engine

from tradebot.db import metin
from tradebot.kayit import log
from tradebot.veri.depo import HamDepo
from tradebot.veri.http import NazikIstemci

KAYNAK = "kap"
LISTE = "https://www.kap.org.tr/tr/api/disclosure/members/byCriteria"
SAYFA = "https://www.kap.org.tr/tr/Bildirim/{}"
TR = ZoneInfo("Europe/Istanbul")
ATLA = frozenset({
    "Pay Bazında Devre Kesici Bildirimi",
    "Temerrüt İşlemi",
    "Pay Alım Satım Bildirimi",
    "Payların Geri Alınmasına İlişkin Bildirim",
    "Pay Dışında Sermaye Piyasası Aracı İşlemlerine İlişkin Bildirim (Faiz İçeren)",
    "Pay Dışında Sermaye Piyasası Aracı İşlemlerine İlişkin Bildirim (Faizsiz)",
    "Şirket Genel Bilgi Formu",
    "Yatırım Kuruluşu Varant - Sertifika - Senetlerine İlişkin Bildirim",
})
_AKIS = re.compile(r'self\.__next_f\.push\(\[1,"((?:[^"\\]|\\.)*)"\]\)')
_log = log("metin.kap")


def liste_govdesi(gun: date) -> dict:
    g = gun.isoformat()
    return {"fromDate": g, "toDate": g, "memberType": "IGS", "mkkMemberOidList": [], "inactiveMkkMemberOidList": [],
            "disclosureClass": "", "subjectList": [], "isLate": "", "mainSector": "", "sector": "", "subSector": "",
            "marketOid": "", "index": "", "bdkReview": "", "bdkMemberOidList": [], "year": "", "term": "",
            "ruleType": "", "period": "", "fromSrc": False, "srcCategory": "", "disclosureIndexList": []}


def tr_ms(s: str) -> int:
    """'25.09.2026 22:44:39' ya da '2026.09.25 22:44:39' (Türkiye saati) → UTC epoch ms."""
    bicim = "%Y.%m.%d %H:%M:%S" if re.match(r"\d{4}\.", s) else "%d.%m.%Y %H:%M:%S"
    return int(datetime.strptime(s, bicim).replace(tzinfo=TR).timestamp() * 1000)


def kodlar(k: dict) -> list[str]:
    """Bildirimin ilgili olduğu hisse kodları (`stockCodes` + `relatedStocks`, sırayla, tekil)."""
    out: list[str] = []
    for alan in ("stockCodes", "relatedStocks"):
        for c in (k.get(alan) or "").split(","):
            c = c.strip().upper()
            if c and c not in out:
                out.append(c)
    return out


def html_metni(h: str) -> str:
    t = re.sub(r"<(script|style)[^>]*>.*?</\1>", "", h, flags=re.S | re.I)
    t = re.sub(r"<br\s*/?>|</p>|</div>|</tr>|</h\d>|</li>", "\n", t, flags=re.I)
    t = re.sub(r"</t[dh]>", " ", t, flags=re.I)
    t = html.unescape(re.sub(r"<[^>]+>", "", t))
    t = re.sub(r"\b[a-z]{2,4}_[A-Za-z]+\|", "", t)       # form alan adları (oda_ExplanationTextBlock|)
    t = re.sub(r"\[[A-Z_]+\]", "", t)                     # [CONSOLIDATION_METHOD] yer tutucuları
    satirlar = (" ".join(s.replace("|", " ").split()) for s in t.split("\n"))
    return "\n".join(s for s in satirlar if s)


def sayfa_govdesi(sayfa_html: str) -> str:
    """Bildirim sayfası → gövde düz metni ('' bulunamazsa)."""
    akis = "".join(json.loads('"' + m.group(1) + '"') for m in _AKIS.finditer(sayfa_html))
    ref = re.search(r'"disclosureBody":\["\$(\w+)"\]', akis)
    if not ref:
        return ""
    m = re.search(r"(?:^|\n)" + re.escape(ref.group(1)) + r":T([0-9a-f]+),", akis)
    if not m:
        return ""
    ham = akis[m.end():].encode("utf-8")[: int(m.group(1), 16)].decode("utf-8", "ignore")
    return html_metni(ham)


class KapBildirim:
    KAYNAK = KAYNAK

    def __init__(self, ham: HamDepo, motor: Engine, http: NazikIstemci | None = None, aralik_sn: float = 0.5,
                 deneme: int = 2) -> None:
        """Ölçüm (2026-09-26): 0,5 sn aralıkla ~100 sayfa isteğinden sonra 429 "Request Limit Exceeded", ~3 dk sürüyor.
        Canlı: az istek, 2 deneme (engelde servis turu Binance'i bekletmesin; kalan sonraki turda). Geçmiş doldurma:
        `aralik_sn` 3, 6 deneme (üstel bekleme engeli aşar)."""
        self.ham, self.motor = ham, motor
        self.http = http or NazikIstemci("kap", aralik_sn=aralik_sn, deneme=deneme, geri_cekilme_sn=5.0,
                                         basliklar={"User-Agent": "Mozilla/5.0", "Accept-Language": "tr"})

    def liste(self, gun: date) -> list[dict]:
        return json.loads(self.http.gonder(LISTE, liste_govdesi(gun)))

    def bilinen(self, nolar: list[str]) -> set[str]:
        if not nolar:
            return set()
        with self.motor.connect() as b:
            return set(b.execute(select(metin.c.dis_kimlik).where(metin.c.kaynak == KAYNAK,
                                                                  metin.c.dis_kimlik.in_(nolar))).scalars())

    def topla(self, gunler: list[date]) -> list[int]:
        """Günlerin yeni bildirimlerini `metin`'e yazar. Döndürür: yeni metin id'leri (yayın zamanına göre)."""
        yeni: list[tuple[int, int]] = []
        for gun in gunler:
            kayitlar = sorted(self.liste(gun), key=lambda k: int(k["disclosureIndex"]))
            bilinen = self.bilinen([str(k["disclosureIndex"]) for k in kayitlar])
            for k in kayitlar:
                no = str(k["disclosureIndex"])
                if no in bilinen:
                    continue
                konu = k.get("subject") or ""
                ozet = k.get("summary") or ""
                atla = konu in ATLA
                try:
                    if atla:
                        ham, uzanti, govde = json.dumps(k, ensure_ascii=False).encode(), "json", ""
                    else:
                        ham, uzanti = self.http.al(SAYFA.format(no)), "html"
                        govde = sayfa_govdesi(ham.decode("utf-8", "ignore"))
                except Exception as e:  # noqa: BLE001 — bu bildirim sonraki turda yeniden denenir
                    _log.warning("bildirim_alinamadi", no=no, hata=str(e)[:200])
                    continue
                _, sha, _ = self.ham.kaydet(KAYNAK, no, ham, uzanti)
                satir = {"kaynak": KAYNAK, "dis_kimlik": no, "katalog": k.get("disclosureClass"),
                         "baslik": f"{konu}: {ozet}"[:1000] if ozet and ozet != konu else konu[:1000],
                         "govde": f"Özet Bilgi: {ozet}\n{govde}".strip() if govde else ozet,
                         "yayin_ms": tr_ms(k["publishDate"]), "ilk_gorulme_ms": int(time.time() * 1000), "ham_sha": sha,
                         "meta": {"kodlar": kodlar(k), "konu": konu, "sirket": k.get("kapTitle"), "atla": atla,
                                  "sinif": k.get("disclosureClass"), "tip": k.get("disclosureType")}}
                with self.motor.begin() as b:
                    mid = b.execute(insert(metin).values(**satir)).inserted_primary_key[0]
                yeni.append((satir["yayin_ms"], int(mid)))
                bilinen.add(no)
        return [i for _, i in sorted(yeni)]

    def canli(self, ayar: dict) -> list[int]:
        """Servis turu: Türkiye saatine göre bugün (gece yarısından sonraki ilk 15 dk dün de)."""
        simdi = datetime.now(TR)
        gunler = sorted({simdi.date(), (simdi - timedelta(minutes=15)).date()})
        return self.topla(gunler)
