"""Dukascopy indiricisi: FX, metal, endeks ve emtia CFD'leri (BID + ASK mumları, .bi5 = LZMA).

Kurallar (Spike 03 + Faz 2 ölçümü):
- Çok sıkı hız sınırı: 3 sn arayla bile isteklerin yarısı 503. İstekler arası ≥ 6 sn, 503'te üstel bekleme; iş zaman
  bütçesiyle çalışır ve kaldığı yerden devam eder (her dosya idempotent).
- Saatlik mum: AY başına bir dosya (ay 0 tabanlı), zaman = ay başından saniye. Dakikalık: GÜN başına, zaman = gün başından.
- Kayıt 24 bayt: >5if = (saniye, open, close, low, high, hacim). Fiyat = tamsayı / ölçek. Ölçek: JPY çiftleri 1e3,
  diğer FX 1e5, metal/endeks/emtia 1e3 (Temmuz 2026 örneklerine göre doğrulandı).
- Hafta sonu / kapalı saatler sıfır hacimli düz mumdur → ayıklanır (hacim 0 ve piyasa kapalı).
- İçinde bulunulan ayın SAATLİK dosyası ay bitince yayınlanıyor (ölçüldü: Eylül 2026 boş döndü). Araştırma verisi en çok
  bir ay geride kalabilir; canlı paper verisi MT5'ten gelir. Boş/eksik dosya ham depoda yeni sürüm olarak saklanır.
"""
from __future__ import annotations

import lzma
import time
from datetime import UTC, date, datetime
from pathlib import Path

import numpy as np
import polars as pl
from sqlalchemy.engine import Engine

from tradebot.kayit import log
from tradebot.veri import enstruman as en
from tradebot.veri.depo import BarDepo, HamDepo
from tradebot.veri.http import NazikIstemci, YokHatasi
from tradebot.veri.takvim import ms, takvim

URL = "https://datafeed.dukascopy.com/datafeed/{s}/{yol}"
_log = log("veri.dukascopy")


def olcek(sembol: str, sinif: str) -> float:
    if sinif == "fx":
        return 1e3 if sembol.endswith("JPY") else 1e5
    return 1e3


def bi5_coz(icerik: bytes, taban_ms: int, bolen: float) -> pl.DataFrame:
    """Sıkıştırılmış mum dosyası → DataFrame (acilis_ms, open, high, low, close, volume)."""
    if not icerik:
        return pl.DataFrame(schema={"acilis_ms": pl.Int64, "open": pl.Float64, "high": pl.Float64, "low": pl.Float64,
                                    "close": pl.Float64, "volume": pl.Float64})
    ham = np.frombuffer(lzma.decompress(icerik), dtype=np.dtype([("t", ">i4"), ("o", ">i4"), ("c", ">i4"), ("l", ">i4"),
                                                                  ("h", ">i4"), ("v", ">f4")]))
    return pl.DataFrame({
        "acilis_ms": taban_ms + ham["t"].astype(np.int64) * 1000,
        "open": ham["o"] / bolen, "high": ham["h"] / bolen, "low": ham["l"] / bolen, "close": ham["c"] / bolen,
        "volume": ham["v"].astype(np.float64),
    })


def kapali_ayikla(df: pl.DataFrame, takvim_adi: str) -> pl.DataFrame:
    if df.is_empty():
        return df
    acik = takvim(takvim_adi).acik_maske(df["acilis_ms"].to_numpy())
    return df.filter(pl.Series(acik) | (pl.col("volume") > 0))


def aylar(bas: str, bit: date) -> list[tuple[int, int]]:
    y, a = map(int, bas.split("-"))
    out = []
    while (y, a) <= (bit.year, bit.month):
        out.append((y, a))
        y, a = (y + 1, 1) if a == 12 else (y, a + 1)
    return out


class Dukascopy:
    def __init__(self, veri_dizini: Path, motor: Engine, evren: dict | None = None, aralik_sn: float = 6.0) -> None:
        self.ham = HamDepo(veri_dizini, motor)
        self.bar = BarDepo(veri_dizini)
        self.motor = motor
        self.evren = evren or en.evren_yukle()
        self.http = NazikIstemci("dukascopy", aralik_sn=aralik_sn, deneme=8, geri_cekilme_sn=15.0,
                                 basliklar={"User-Agent": "Mozilla/5.0"})

    def _dosya(self, sembol: str, yol: str, anahtar: str, tamamlanmis: bool) -> bytes | None:
        """Ham dosyayı getirir; tamamlanmış dönem daha önce indirildiyse None (atla)."""
        if tamamlanmis and self.ham.var_mi("dukascopy", anahtar):
            return None
        try:
            icerik = self.http.al(URL.format(s=sembol, yol=yol))
        except YokHatasi:
            icerik = b""
        self.ham.kaydet("dukascopy", anahtar, icerik, "bi5")
        return icerik

    def saatlik_ay(self, e: en.Enstruman, y: int, a: int, taraf: str) -> pl.DataFrame | None:
        bugun = date.today()
        tamamlanmis = (y, a) < (bugun.year, bugun.month)
        anahtar = f"{e.sembol}/{taraf}/1h/{y}-{a:02d}"
        icerik = self._dosya(e.sembol, f"{y}/{a - 1:02d}/{taraf}_candles_hour_1.bi5", anahtar, tamamlanmis)
        if icerik is None:
            return None
        return bi5_coz(icerik, ms(datetime(y, a, 1, tzinfo=UTC)), olcek(e.sembol, e.sinif))

    def dakikalik_gun(self, e: en.Enstruman, g: date) -> pl.DataFrame | None:
        tamamlanmis = g < date.today()
        anahtar = f"{e.sembol}/BID/1m/{g.isoformat()}"
        icerik = self._dosya(e.sembol, f"{g.year}/{g.month - 1:02d}/{g.day:02d}/BID_candles_min_1.bi5", anahtar, tamamlanmis)
        if icerik is None:
            return None
        return bi5_coz(icerik, ms(datetime(g.year, g.month, g.day, tzinfo=UTC)), olcek(e.sembol, e.sinif))

    def saatlik(self, e: en.Enstruman, bas: str, ask_yil: int, bitis_zamani: float) -> dict:
        """BID tam geçmiş + ASK son `ask_yil` yıl. `bitis_zamani` (monotonic) aşılınca bırakır, sonra devam eder."""
        bugun = date.today()
        bid, ask, yeni = [], [], 0
        ask_bas = f"{bugun.year - ask_yil}-{bugun.month:02d}"
        for y, a in aylar(bas, bugun):
            if time.monotonic() > bitis_zamani:
                break
            if (b := self.saatlik_ay(e, y, a, "BID")) is not None:
                bid.append(b)
                yeni += 1
            if f"{y}-{a:02d}" >= ask_bas and time.monotonic() <= bitis_zamani:
                if (k := self.saatlik_ay(e, y, a, "ASK")) is not None:
                    ask.append(k)
                    yeni += 1
        if bid:
            df = kapali_ayikla(pl.concat(bid), e.takvim)
            self.bar.yaz(e.kimlik, "1h", df)
        if ask:
            self._spread_isle(e, pl.concat(ask))
        tum = self.bar.oku(e.kimlik, "1h")
        ilk, son = (int(tum["acilis_ms"][0]), int(tum["acilis_ms"][-1])) if len(tum) else (None, None)
        return {"kimlik": e.kimlik, "yeni_dosya": yeni, "bar": len(tum), "ilk_ms": ilk, "son_ms": son}

    def _spread_isle(self, e: en.Enstruman, ask: pl.DataFrame) -> None:
        """Spread = (ASK − BID) açılış/kapanış ortalaması; bar deposundaki BID barlarına kolon olarak eklenir."""
        bid = self.bar.oku(e.kimlik, "1h")
        if bid.is_empty():
            return
        j = bid.drop("spread", strict=False).join(
            ask.select("acilis_ms", pl.col("open").alias("a_o"), pl.col("close").alias("a_c")), on="acilis_ms", how="left")
        eski = bid.select("acilis_ms", "spread") if "spread" in bid.columns else None
        j = j.with_columns((((pl.col("a_o") - pl.col("open")) + (pl.col("a_c") - pl.col("close"))) / 2).alias("spread_yeni"))
        if eski is not None:
            j = j.join(eski, on="acilis_ms", how="left").with_columns(pl.coalesce("spread_yeni", "spread").alias("spread"))
        else:
            j = j.with_columns(pl.col("spread_yeni").alias("spread"))
        self.bar.yaz(e.kimlik, "1h", j.drop("a_o", "a_c", "spread_yeni"), birlestir=False)

    def dakikalik(self, e: en.Enstruman, yil: int, bitis_zamani: float) -> dict:
        bugun = date.today()
        gunler = pl.date_range(date(bugun.year - yil, bugun.month, 1), bugun, eager=True).to_list()
        parca, yeni = [], 0
        for g in reversed(gunler):  # en yeniden eskiye: yürütme doğrulaması için yakın dönem önce
            if time.monotonic() > bitis_zamani:
                break
            if g.weekday() == 5:  # Cumartesi: FX kapalı
                continue
            if (d := self.dakikalik_gun(e, g)) is not None:
                parca.append(d)
                yeni += 1
        if parca:
            self.bar.yaz(e.kimlik, "1m", kapali_ayikla(pl.concat(parca), e.takvim))
        return {"kimlik": e.kimlik, "zd": "1m", "yeni_dosya": yeni}

    def evren_guncelle(self, butce_dk: float = 60.0) -> list[dict]:
        """Zaman bütçesi içinde saatlik (tüm semboller) sonra dakikalık (seçilenler) indirir; kalanı sonraki koşuya kalır."""
        d = self.evren["dukascopy"]
        liste = en.dukascopy_enstrumanlari(self.evren)
        en.kaydet(self.motor, liste)
        bitis = time.monotonic() + butce_dk * 60
        sonuc = []
        for e in liste:
            if time.monotonic() > bitis:
                break
            try:
                r = self.saatlik(e, d["baslangic"], d.get("ask_yil", 3), bitis)
            except Exception as ex:
                _log.error("sembol_hatasi", kimlik=e.kimlik, hata=str(ex)[:200])
                continue
            en.sinir_guncelle(self.motor, e.kimlik, r["ilk_ms"], r["son_ms"])
            sonuc.append(r)
        for s in d.get("dakikalik", []):
            if time.monotonic() > bitis:
                break
            e = next(x for x in liste if x.sembol == s)
            sonuc.append(self.dakikalik(e, d.get("dakikalik_yil", 3), bitis))
        _log.info("dukascopy_kosu", dosya=sum(r.get("yeni_dosya", 0) for r in sonuc), butce_doldu=time.monotonic() > bitis)
        return sonuc
