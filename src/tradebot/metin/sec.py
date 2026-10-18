"""SEC EDGAR 8-K toplayıcısı (A3; Nasdaq kolları). Anahtar yok; SEC adil erişim kuralı: iletişim adresli User-Agent,
saniyede ≤ 10 istek (burada ~3).

Akış (`canli`): bugünkü Nasdaq-100 üyelerinin CIK'leri (`company_tickers.json`, günde bir, ham depoya) → her turda
sıradaki `SIRA` şirketin başvuru listesi (`data.sec.gov/submissions/CIK…json`; ~10 dakikada bütün üyeler) → son
`GERI_GUN` günün yeni 8-K'ları metin tablosuna. Zaman: `acceptanceDateTime` (SEC'in kabul anı = ilk yayın, kural 9).
Kalemleri yalnız rutin olan başvuru (`ROUTIN`: kazanç açıklaması, yönetici değişikliği, genel kurul…) `atla` işaretli
kaydedilir, modele sorulmaz; diğerlerinde ana belge indirilir, düz metne çevrilir (ilk `METIN_SINIRI` karakter).
"""
from __future__ import annotations

import html
import json
import re
import time
from datetime import datetime

from sqlalchemy import insert, select
from sqlalchemy.engine import Engine

from tradebot.db import metin
from tradebot.kayit import log
from tradebot.veri.depo import HamDepo
from tradebot.veri.http import NazikIstemci, YokHatasi

KAYNAK = "sec_8k"
TICKER_URL = "https://www.sec.gov/files/company_tickers.json"
SUB_URL = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
BELGE_URL = "https://www.sec.gov/Archives/edgar/data/{cik}/{acc}/{belge}"
UA = "TradeBot kisisel arastirma (218348029+Scryne@users.noreply.github.com)"
# Yalnız bu kalemlerden oluşan 8-K rutindir (veto adayı değil): 5.02 yönetici, 5.03 ana sözleşme, 5.07 genel kurul oyu,
# 5.08 aday gösterme, 9.01 ekler. 2.02 (sonuçlar) ve 7.01 (basın açıklaması) modele gider: spike 09'da Intel'in büyük
# yeniden yapılanması kazanç bildiriminde, Walgreens'in satışı 7.01 basın açıklamasındaydı.
ROUTIN = {"5.02", "5.03", "5.07", "5.08", "9.01"}
KALEM_ADI = {
    "1.01": "Entry into a Material Definitive Agreement", "1.02": "Termination of a Material Definitive Agreement",
    "1.03": "Bankruptcy or Receivership", "1.05": "Material Cybersecurity Incidents",
    "2.01": "Completion of Acquisition or Disposition of Assets", "2.03": "Creation of a Direct Financial Obligation",
    "2.04": "Triggering Events That Accelerate a Financial Obligation", "2.05": "Costs Associated with Exit Activities",
    "2.06": "Material Impairments", "3.01": "Notice of Delisting or Failure to Satisfy a Continued Listing Rule",
    "3.02": "Unregistered Sales of Equity Securities", "3.03": "Material Modification to Rights of Security Holders",
    "4.01": "Changes in Registrant's Certifying Accountant",
    "4.02": "Non-Reliance on Previously Issued Financial Statements", "5.01": "Changes in Control of Registrant",
    "8.01": "Other Events",
}
SIRA = 10
GERI_GUN = 7
METIN_SINIRI = 8000
_log = log("metin.sec")


def duz_metin(h: str) -> str:
    """HTML → düz metin (script/style atılır, etiketler boşluk, varlıklar çözülür, boşluk sıkıştırılır)."""
    h = re.sub(r"(?is)<(script|style)[^>]*>.*?</\1>", " ", h)
    h = re.sub(r"(?s)<[^>]+>", " ", h)
    return re.sub(r"\s+", " ", html.unescape(h)).strip()


def ms(acceptance: str) -> int:
    return int(datetime.fromisoformat(acceptance.replace("Z", "+00:00")).timestamp() * 1000)


def yeni_8kler(sub: dict, bas_ms: int) -> list[dict]:
    """Başvuru listesinden `bas_ms`'ten sonra kabul edilmiş 8-K'lar (8-K/A dahil)."""
    r = (sub.get("filings") or {}).get("recent") or {}
    out = []
    for i, form in enumerate(r.get("form", [])):
        if form not in ("8-K", "8-K/A"):
            continue
        t = ms(r["acceptanceDateTime"][i])
        if t < bas_ms:
            continue
        kalem = [k.strip() for k in (r.get("items", [""])[i] or "").split(",") if k.strip()]
        out.append({"acc": r["accessionNumber"][i], "belge": r["primaryDocument"][i], "zaman_ms": t, "form": form,
                    "kalemler": kalem, "tarih": r["filingDate"][i]})
    return out


class Sec8K:
    KAYNAK = KAYNAK

    def __init__(self, ham: HamDepo, motor: Engine, http: NazikIstemci | None = None,
                 uyeler=None) -> None:
        """`uyeler()`: bugünkü Nasdaq-100 kimlikleri (NASDAQ:SEMBOL). Verilmezse `veri.nasdaq` türetilmiş üyelikten."""
        self.ham, self.motor = ham, motor
        self.http = http or NazikIstemci("sec", aralik_sn=0.35, deneme=4, basliklar={"User-Agent": UA})
        self._uyeler = uyeler
        self._cik: dict[str, int] = {}
        self._cik_gun: int | None = None
        self._sira = 0

    def _uye_kimlikleri(self) -> list[str]:
        if self._uyeler is not None:
            return list(self._uyeler())
        from tradebot.ayar import ayarlar
        from tradebot.veri import nasdaq as nqv

        return nqv.uyelik_dosyadan(ayarlar().veri_dizini).uyeler(int(time.time() * 1000))

    def cikler(self) -> dict[str, int]:
        """Sembol → CIK (günde bir indirilir; alınamazsa son ham sürüm)."""
        gun = int(time.time() // 86_400)
        if self._cik_gun != gun:
            try:
                icerik = self.http.al(TICKER_URL)
                self.ham.kaydet(KAYNAK, "company_tickers", icerik, "json")
            except Exception as e:  # noqa: BLE001
                _log.warning("sec_ticker_alinamadi", hata=str(e)[:160])
                son = self.ham.dosyalar(KAYNAK, "company_tickers")
                if not son:
                    raise
                icerik = son[-1][1].read_bytes()
            self._cik = {v["ticker"].upper(): int(v["cik_str"]) for v in json.loads(icerik).values()}
            self._cik_gun = gun
        return self._cik

    def canli(self, ayar: dict) -> list[int]:
        cik = self.cikler()
        hedefler = [(k, cik[k.split(":", 1)[1].replace(".", "-")]) for k in self._uye_kimlikleri()
                    if k.split(":", 1)[1].replace(".", "-") in cik]
        if not hedefler:
            return []
        n = int(((ayar.get("sec") or {}).get("sira")) or SIRA)
        secili = [hedefler[(self._sira + i) % len(hedefler)] for i in range(min(n, len(hedefler)))]
        self._sira = (self._sira + n) % len(hedefler)
        bas = int(time.time() * 1000) - GERI_GUN * 86_400_000
        yeni = []
        for kimlik, c in secili:
            try:
                sub = json.loads(self.http.al(SUB_URL.format(cik=c)))
            except YokHatasi:
                continue
            yeni += self._kaydet(kimlik, c, sub, bas)
        return yeni

    def _ek99(self, cik: int, acc: str) -> str:
        kok = BELGE_URL.format(cik=cik, acc=acc.replace("-", ""), belge="")
        try:
            ad = _ek99_sec(self.http.al(f"{kok}{acc}-index-headers.html").decode("utf-8", "ignore"))
            if ad is None:
                return ""
            ham = self.http.al(kok + ad)
        except Exception as e:  # noqa: BLE001 — ek olmadan da yargılanır
            _log.warning("sec_ek_alinamadi", acc=acc, hata=str(e)[:160])
            return ""
        self.ham.kaydet(KAYNAK, f"8k-ek99/{acc}", ham, "htm")
        return duz_metin(ham.decode("utf-8", "ignore"))

    def _kaydet(self, kimlik: str, cik: int, sub: dict, bas_ms: int) -> list[int]:
        adaylar = yeni_8kler(sub, bas_ms)
        if not adaylar:
            return []
        with self.motor.connect() as b:
            bilinen = set(b.execute(select(metin.c.dis_kimlik).where(
                metin.c.kaynak == KAYNAK, metin.c.dis_kimlik.in_([a["acc"] for a in adaylar]))).scalars())
        out = []
        for a in adaylar:
            if a["acc"] in bilinen:
                continue
            atla = set(a["kalemler"]) <= ROUTIN
            govde = ""
            # Başvuru satırı (kalemler, kabul anı) her durumda ham kayda girer: metnin `ham_sha`'sı
            _, sha, _ = self.ham.kaydet(KAYNAK, f"8k-satir/{a['acc']}", json.dumps(a, sort_keys=True).encode(), "json")
            if not atla:
                url = BELGE_URL.format(cik=cik, acc=a["acc"].replace("-", ""), belge=a["belge"])
                try:
                    ham = self.http.al(url)
                except Exception as e:  # noqa: BLE001 — sonraki turda yeniden denenir (kayıt yazılmaz)
                    _log.warning("sec_belge_alinamadi", acc=a["acc"], hata=str(e)[:160])
                    continue
                self.ham.kaydet(KAYNAK, f"8k/{a['acc']}", ham, "htm")
                govde = duz_metin(ham.decode("utf-8", "ignore"))
                ek = self._ek99(cik, a["acc"])   # basın açıklaması çoğu zaman ek 99.1'de (spike 09: Intel 2.02)
                if ek:
                    govde = f"{govde[:2500]}\n\nEXHIBIT 99: {ek}"
                govde = govde[:METIN_SINIRI]
            baslik = f"{sub.get('name', kimlik)} {a['form']}: " + "; ".join(
                f"Item {k} {KALEM_ADI.get(k, '')}".strip() for k in a["kalemler"])
            satir = {"kaynak": KAYNAK, "dis_kimlik": a["acc"], "katalog": "8-K", "baslik": baslik[:1000], "govde": govde,
                     "yayin_ms": a["zaman_ms"], "ilk_gorulme_ms": int(time.time() * 1000), "ham_sha": sha,
                     "meta": {"kodlar": [kimlik.split(":", 1)[1]], "cik": cik, "kalemler": a["kalemler"], "atla": atla,
                              "form": a["form"], "sirket": sub.get("name")}}
            with self.motor.begin() as b:
                out.append(int(b.execute(insert(metin).values(**satir)).inserted_primary_key[0]))
        return out


def _ek99_sec(basliklar: str) -> str | None:
    """Başvuru başlık belgesinden (`…-index-headers.html`) ilk EX-99 ekinin dosya adı. Ek adları şirkete göre değişir
    (Intel: q224_earningsrelease.htm); tür satırı değişmez."""
    m = re.search(r"&lt;TYPE&gt;EX-99[^\n]*\s*(?:&lt;SEQUENCE&gt;[^\n]*\s*)?&lt;FILENAME&gt;([^\s<&]+)", basliklar)
    return m.group(1) if m else None


def gecmis(ham: HamDepo, motor: Engine, kimlik: str, cik: int, bas_ms: int, http: NazikIstemci | None = None) -> list[int]:
    """Spike/geri doldurma: bir şirketin `bas_ms`'ten sonraki 8-K'ları (son ~1000 başvuru içinde)."""
    s = Sec8K(ham, motor, http, uyeler=lambda: [kimlik])
    return s._kaydet(kimlik, cik, json.loads(s.http.al(SUB_URL.format(cik=cik))), bas_ms)
