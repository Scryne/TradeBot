"""Yahoo indiricisi: ABD ETF'leri ve BIST (günlük), temettü ve bölünme olayları.

Kurallar (Spike 03):
- `range=max` aylığa düşüyor → her zaman `period1/period2`.
- Yahoo OHLC'si bölünmeye göre GERİYE DÖNÜK düzeltilmiştir (ham düzeltmesiz seri ücretsiz yok). Bu yüzden yeni bir
  bölünme/bedelsiz görüldüğünde tüm geçmiş yeniden indirilir ve barlar sıfırdan üretilir; aksi halde son 40 gün.
- `adj_close` bölünme + temettü düzeltmelidir (toplam getiri). Olaylar `kurumsal_islem` tablosuna yazılır.
- Seans kapanmadan gelen bugünkü bar atılır (tamamlanmamış). Zaman: seans günü 00:00 UTC.
- Her yanıt ham anlık görüntü olarak saklanır (ham veri değişmez; Yahoo geçmişi düzeltirse yeni sürüm).
"""
from __future__ import annotations

import json
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import polars as pl
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.engine import Engine

from tradebot.db import kurumsal_islem
from tradebot.kayit import log
from tradebot.veri import enstruman as en
from tradebot.veri.depo import BarDepo, HamDepo
from tradebot.veri.http import NazikIstemci, YokHatasi
from tradebot.veri.takvim import gun_basi, takvim

URL = "https://query1.finance.yahoo.com/v8/finance/chart/{s}"
ARTIMLI_GUN = 40
_log = log("veri.yahoo")


def yanit_coz(ham: bytes) -> tuple[pl.DataFrame, list[dict]]:
    """Yahoo chart JSON → (günlük barlar, olaylar). Olay: {tarih_ms, tur, deger}."""
    d = json.loads(ham)["chart"]
    if d.get("error"):
        raise YokHatasi(str(d["error"]))
    r = d["result"][0]
    if not r.get("timestamp"):
        return pl.DataFrame(), []
    q = r["indicators"]["quote"][0]
    adj = (r["indicators"].get("adjclose") or [{}])[0].get("adjclose") or [None] * len(r["timestamp"])
    df = pl.DataFrame({
        "acilis_ms": [gun_basi(int(t) * 1000) for t in r["timestamp"]],
        "open": q["open"], "high": q["high"], "low": q["low"], "close": q["close"],
        "volume": [float(v) if v is not None else None for v in q["volume"]], "adj_close": adj,
    }, schema_overrides={k: pl.Float64 for k in ("open", "high", "low", "close", "volume", "adj_close")})
    df = df.drop_nulls(["open", "high", "low", "close"]).unique("acilis_ms", keep="last").sort("acilis_ms")
    olaylar = []
    ev = r.get("events", {})
    for v in ev.get("dividends", {}).values():
        olaylar.append({"tarih_ms": gun_basi(int(v["date"]) * 1000), "tur": "temettu", "deger": float(v["amount"])})
    for v in ev.get("splits", {}).values():
        olaylar.append({"tarih_ms": gun_basi(int(v["date"]) * 1000), "tur": "bolunme",
                        "deger": float(v["numerator"]) / float(v["denominator"])})
    return df, olaylar


def normalize(df: pl.DataFrame, takvim_adi: str) -> tuple[pl.DataFrame, dict]:
    """Türetilmiş bar deposuna yazmadan önce (ham değişmez, kural 9). 2026-09-27 denetimi:
    - Yahoo, BIST kapalıyken bar üretiyor (bayramlar; 2023-02-08'de iptal edilen seans: THYAO O=K=115, hacim 2.500).
      Takvim kapalı diyorsa **ve** bar bayatsa (hacim son 20 barın medyanının %1'i altında ya da O=Y=D=K) atılır.
      Normal hacimli bar, takvim kapalı dese de kalır (takvim de yanılabilir; kalite raporu işaretler).
    - Düzeltilmiş seride seyrek OHLC tutarsızlığı (açılış ayrı ölçeklenmiş, ~%1): yüksek/düşük O/K'yı kapsayacak
      şekilde genişletilir."""
    if df.is_empty():
        return df, {"kapali_gun_atildi": 0, "ohlc_onarildi": 0, "sicrama_atildi": 0}
    t = df["acilis_ms"].to_numpy()
    acik = np.isin(t, takvim(takvim_adi).gunluk_barlar(int(t[0]), int(t[-1]) + 1))
    hacim = df["volume"].fill_null(0.0).to_numpy()
    medyan = pl.Series(hacim).shift(1).rolling_median(window_size=20, min_samples=5).fill_null(0.0).to_numpy()
    op, hi, lo, cl = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    duz = (op == hi) & (hi == lo) & (lo == cl)
    bayat = (hacim < 0.01 * medyan) | duz
    at = ~acik & bayat
    tutarsiz = (hi < np.maximum(op, cl)) | (lo > np.minimum(op, cl))
    # İmkânsız sıçra-dön: kapanıştan kapanışa > ±%25 ve ertesi gün en az yarısı kadar geri. BIST'in günlük fiyat limiti
    # bunun çok altında, büyük ETF'ler de bir günde %25 sıçrayıp dönmez. Denetim: TRHOL 2025-01-10 ×102; 243 BIST
    # serisinin 221'inde bölünme kaydı var (düzeltmenin yanlış güne uygulanması). Bar atılır (eksik gün olur).
    lr = np.diff(np.log(np.where(cl > 0, cl, np.nan)))
    sic = np.zeros(len(cl), dtype=bool)
    if len(lr) > 1:
        buyuk = np.abs(lr[:-1]) > np.log(1.25)
        don = (np.sign(lr[1:]) == -np.sign(lr[:-1])) & (np.abs(lr[1:]) >= 0.5 * np.abs(lr[:-1]))
        sic[1:-1] = buyuk & don
    df = df.with_columns(pl.max_horizontal("open", "high", "low", "close").alias("high"),
                         pl.min_horizontal("open", "high", "low", "close").alias("low")).filter(pl.Series(~(at | sic)))
    return df, {"kapali_gun_atildi": int(at.sum()), "ohlc_onarildi": int(tutarsiz.sum()),
                "sicrama_atildi": int((sic & ~at).sum())}


def olcek_kaydi(eski: pl.DataFrame | None, yeni: pl.DataFrame, tolerans: float = 1e-6) -> bool:
    """Örtüşen günlerde kapanış ya da `adj_close` farklı mı (kaynak geçmişi yeniden ölçeklemiş)."""
    if eski is None or eski.is_empty() or yeni.is_empty():
        return False
    k = [c for c in ("close", "adj_close") if c in eski.columns and c in yeni.columns]
    j = eski.select("acilis_ms", *k).join(yeni.select("acilis_ms", *k), on="acilis_ms", suffix="_y")
    for c in k:
        a, b = j[c].to_numpy().astype(float), j[f"{c}_y"].to_numpy().astype(float)
        ok = np.isfinite(a) & np.isfinite(b) & (a != 0)
        if ok.any() and (np.abs(b[ok] / a[ok] - 1) > tolerans).any():
            return True
    return False


def tamamlanmamis_at(df: pl.DataFrame, takvim_adi: str, simdi_ms: int, tampon_ms: int = 15 * 60_000) -> pl.DataFrame:
    """Seansı henüz kapanmamış günün barını atar."""
    if df.is_empty():
        return df
    son_gun = int(df["acilis_ms"][-1])
    kapanislar = [c for o, c in takvim(takvim_adi).seanslar(son_gun, son_gun) if gun_basi(o) == son_gun]
    if kapanislar and simdi_ms < kapanislar[0] + tampon_ms:
        return df.filter(pl.col("acilis_ms") != son_gun)
    return df


class Yahoo:
    def __init__(self, veri_dizini: Path, motor: Engine, evren: dict | None = None) -> None:
        self.ham = HamDepo(veri_dizini, motor)
        self.bar = BarDepo(veri_dizini)
        self.motor = motor
        self.evren = evren or en.evren_yukle()
        self.http = NazikIstemci("yahoo", aralik_sn=0.5, basliklar={"User-Agent": "Mozilla/5.0"})

    def _bilinen_olaylar(self, kimlik: str) -> set[tuple[int, str]]:
        with self.motor.connect() as b:
            return {(int(t), str(tur)) for t, tur in b.execute(select(kurumsal_islem.c.tarih_ms, kurumsal_islem.c.tur)
                                                               .where(kurumsal_islem.c.kimlik == kimlik)).all()}

    def _olay_yaz(self, kimlik: str, olaylar: list[dict], ham_sha: str) -> int:
        if not olaylar:
            return 0
        ins = pg_insert if self.motor.dialect.name == "postgresql" else sqlite_insert
        with self.motor.begin() as b:
            for o in olaylar:
                b.execute(ins(kurumsal_islem).values(kimlik=kimlik, kaynak="yahoo", ham_sha=ham_sha, **o)
                          .on_conflict_do_nothing(index_elements=["kimlik", "tarih_ms", "tur", "kaynak"]))
        return len(olaylar)

    def _cek(self, sembol: str, bas_ms: int, bit_ms: int) -> bytes:
        return self.http.al(URL.format(s=sembol), {"period1": bas_ms // 1000, "period2": bit_ms // 1000,
                                                   "interval": "1d", "events": "div,splits", "includeAdjustedClose": "true"})

    def gunluk(self, e: en.Enstruman, baslangic: str, tam: bool = False) -> dict:
        kimlik, ks = e.kimlik, e.meta["kaynak_sembol"]
        simdi = int(time.time() * 1000)
        mevcut = self.bar.oku(kimlik, "1d") if self.bar.yol(kimlik, "1d").exists() else None
        tam = tam or mevcut is None or mevcut.is_empty()
        # Artımlı pencere en geç son kayıtlı bardan 10 gün önce başlar: servis 40 günden uzun durursa delik kalmasın.
        if tam:
            bas = int(datetime.fromisoformat(baslangic).replace(tzinfo=UTC).timestamp() * 1000)
        else:
            bas = min(simdi - ARTIMLI_GUN * 86_400_000, int(mevcut["acilis_ms"][-1]) - 10 * 86_400_000)
        ham = self._cek(ks, bas, simdi)
        df, olaylar = yanit_coz(ham)
        if not tam:
            # Yahoo bölünmede OHLC'yi, temettüde `adj_close`'u TÜM geçmiş için yeniden ölçekler. Artımlı birleştirme eski
            # satırları eski ölçekte bırakır ve sınırda sahte getiri doğar (2026-10-18 denetimi): yeni olay ya da
            # örtüşen günlerde ölçek farkı görülürse seri baştan indirilir (hamdan yeniden üretilebilirlik, kural 9).
            yeni_olay = {(o["tarih_ms"], o["tur"]) for o in olaylar} - self._bilinen_olaylar(kimlik)
            if yeni_olay or olcek_kaydi(mevcut, df):
                _log.info("yahoo_tam_yenileme", kimlik=kimlik, olay=sorted(yeni_olay)[:5])
                return self.gunluk(e, baslangic, tam=True)
        _, sha, _ = self.ham.kaydet("yahoo", f"chart/{ks}/1d/{datetime.now(UTC):%Y-%m-%d}{'-tam' if tam else ''}", ham, "json")
        df = tamamlanmamis_at(df, e.takvim, simdi)
        df, duzeltme = normalize(df, e.takvim)
        if any(duzeltme.values()):
            _log.info("yahoo_normalize", kimlik=kimlik, **duzeltme)
        self._olay_yaz(kimlik, olaylar, sha)
        n = self.bar.yaz(kimlik, "1d", df, birlestir=not tam) if not df.is_empty() else 0
        tum = self.bar.oku(kimlik, "1d")
        ilk, son = (int(tum["acilis_ms"][0]), int(tum["acilis_ms"][-1])) if len(tum) else (None, None)
        return {"kimlik": kimlik, "tam": tam, "yeni_bar": len(df), "bar": n, "olay": len(olaylar), "ilk_ms": ilk, "son_ms": son}

    def evren_guncelle(self, bist_hisseleri: list[str] | None = None, tam: bool = False) -> list[dict]:
        etf = en.abd_etf_enstrumanlari(self.evren)
        bist = en.bist_enstrumanlari(self.evren, bist_hisseleri if bist_hisseleri is not None else bist_sirketleri())
        en.kaydet(self.motor, etf + bist)
        sonuc = []
        for e in etf + bist:
            bas = self.evren["abd_etf" if e.piyasa == "ARCA" else "bist"]["baslangic"]
            try:
                r = self.gunluk(e, bas, tam=tam)
            except YokHatasi:
                en.sinir_guncelle(self.motor, e.kimlik, None, None, "veri_yok")
                continue
            except Exception as ex:
                _log.error("sembol_hatasi", kimlik=e.kimlik, hata=str(ex)[:200])
                continue
            en.sinir_guncelle(self.motor, e.kimlik, r["ilk_ms"], r["son_ms"], "aktif")   # geçici 404 kalıcı olmasın
            sonuc.append(r)
        return sonuc


def bist_sirketleri() -> list[str]:
    """KAP şirket listesi (borsapy). Yahoo'da verisi olmayanlar indirmede 'veri_yok' olarak işaretlenir."""
    import borsapy as bp

    return sorted({t.strip().upper() for t in bp.companies()["ticker"].dropna()})
