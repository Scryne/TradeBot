"""Veri kalite raporu: enstrüman × zaman dilimi başına.

Kontroller:
- tekrar eden açılış zamanı, OHLC tutarsızlığı (high < max(o,c), low > min(o,c), fiyat ≤ 0)       → HATA
- takvime göre eksik bar oranı, uzun boşluklar, 30 günden uzun boşluk ("kimlik kırılması şüphesi":
  aynı sembol farklı varlık olabilir, ör. LUNAUSDT 2022), kapalı saatte bar, sıçrama, sıfır hacim     → UYARI
- son barın yaşı (bayatlık)                                                                         → UYARI
"""
from __future__ import annotations

from datetime import UTC, datetime

import numpy as np
import polars as pl
from sqlalchemy import insert
from sqlalchemy.engine import Engine

from tradebot.db import kalite_raporu
from tradebot.veri.takvim import ZAMAN_DILIMI_MS, dt, takvim

GUN = 86_400_000
KIMLIK_KIRILMASI_MS = 30 * GUN
EKSIK_UYARI = 0.01
SICRAMA_KAT = 15.0  # |log getiri| > 15 × kayan MAD


def _t(ms: int) -> str:
    return dt(ms).strftime("%Y-%m-%d %H:%M")


def rapor(df: pl.DataFrame, zaman_dilimi: str, takvim_adi: str, simdi_ms: int | None = None) -> tuple[str, dict]:
    if df.is_empty():
        return "HATA", {"satir": 0, "not": "veri yok"}
    df = df.sort("acilis_ms")
    t = df["acilis_ms"].to_numpy()
    adim = ZAMAN_DILIMI_MS[zaman_dilimi]
    tk = takvim(takvim_adi)
    o = {"satir": len(df), "ilk": _t(int(t[0])), "son": _t(int(t[-1]))}

    o["tekrar"] = int(len(t) - len(np.unique(t)))
    op, hi, lo, cl = (df[k].to_numpy() for k in ("open", "high", "low", "close"))
    tutarsiz = (hi < np.maximum(op, cl) - 1e-12) | (lo > np.minimum(op, cl) + 1e-12) | (lo > hi) | (np.minimum(op, cl) <= 0)
    o["ohlc_tutarsiz"] = int(tutarsiz.sum())
    if o["ohlc_tutarsiz"]:
        o["ohlc_ornek"] = [_t(int(x)) for x in t[tutarsiz][:5]]

    # Beklenen barlar (borsa günlük: seans günleri; diğerleri: takvim maskesi)
    if zaman_dilimi == "1d" and hasattr(tk, "gunluk_barlar"):
        beklenen = tk.gunluk_barlar(int(t[0]), int(t[-1]) + 1)
        acik = np.isin(t, beklenen)
    else:
        beklenen = tk.beklenen_barlar(zaman_dilimi, int(t[0]), int(t[-1]) + 1) if zaman_dilimi != "1d" else \
            np.arange(t[0], t[-1] + 1, GUN, dtype=np.int64)
        acik = tk.acik_maske(t) if zaman_dilimi != "1d" else np.ones(len(t), dtype=bool)
    eksik = np.setdiff1d(beklenen, t, assume_unique=False)
    o["beklenen"], o["eksik"] = int(len(beklenen)), int(len(eksik))
    o["eksik_oran"] = round(len(eksik) / max(len(beklenen), 1), 5)
    o["kapali_saatte_bar"] = int((~acik).sum())

    fark = np.diff(t)
    buyuk = np.where(fark > adim * (3 if zaman_dilimi != "1d" else 5))[0]
    bosluklar = sorted(((int(fark[i]), int(t[i]), int(t[i + 1])) for i in buyuk), reverse=True)
    o["uzun_bosluk"] = [{"bas": _t(a), "bit": _t(b), "gun": round(f / GUN, 1)} for f, a, b in bosluklar[:5]]
    kirilma = [(a, b) for f, a, b in bosluklar if f > KIMLIK_KIRILMASI_MS]
    o["kimlik_kirilmasi_supheli"] = [{"bas": _t(a), "bit": _t(b)} for a, b in kirilma]

    lr = np.diff(np.log(cl))
    if len(lr) > 50:
        s = pl.Series(np.abs(lr)).rolling_median(window_size=50, min_samples=10).to_numpy()
        esik = SICRAMA_KAT * np.nan_to_num(s, nan=np.inf) / 0.6745
        buyuk = np.abs(lr) > np.maximum(esik, 1e-4)
        # Kötü tick izi: büyük hareketin hemen ardından en az yarısı kadar ters hareket (sıçra-dön). Geri dönmeyen büyük
        # hareket gerçek olabilir (küçük coinler, haber): yalnız sayılır, uyarı değildir. 2026-09-27 denetimi: eski
        # tanımla Binance serilerinin 711/735'i UYARI'ydı, uyarı anlamını yitirmişti.
        don = np.zeros(len(lr), dtype=bool)
        don[:-1] = buyuk[:-1] & (np.sign(lr[1:]) == -np.sign(lr[:-1])) & (np.abs(lr[1:]) >= 0.5 * np.abs(lr[:-1]))
        sic = np.where(don)[0]
        o["buyuk_hareket"] = int(buyuk.sum())
        o["sicrama"] = int(len(sic))
        o["sicrama_ornek"] = [{"t": _t(int(t[i + 1])), "getiri": round(float(lr[i]), 4), "donus": round(float(lr[i + 1]), 4)}
                              for i in sorted(sic, key=lambda i: -abs(lr[i]))[:5]]
    o["sifir_hacim_oran"] = round(float((df["volume"].to_numpy() <= 0).mean()), 4)
    if "spread" in df.columns:
        sp = df["spread"].drop_nulls()
        o["spread_medyan"] = float(sp.median()) if len(sp) else None

    if simdi_ms is not None:
        o["son_bar_yasi_saat"] = round((simdi_ms - int(t[-1])) / 3_600_000, 1)

    if o["tekrar"] or o["ohlc_tutarsiz"]:
        durum = "HATA"
    elif o["eksik_oran"] > EKSIK_UYARI or o["kapali_saatte_bar"] or o.get("sicrama") or kirilma:
        durum = "UYARI"
    else:
        durum = "OK"
    return durum, o


def kaydet(motor: Engine, kimlik: str, zaman_dilimi: str, durum: str, ozet: dict) -> None:
    with motor.begin() as b:
        b.execute(insert(kalite_raporu).values(zaman=datetime.now(UTC), kimlik=kimlik, zaman_dilimi=zaman_dilimi,
                                               durum=durum, ozet=ozet))
