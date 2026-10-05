"""Sapma + Stokastik RSI + EMA sistemi (dalga 15; docs/turnuva/Dalga-15-Sapma-Stoch.md). Saf ve nedensel; yalnız alış.

Kaynak: Scryne'ın gönderdiği bir YouTube videosu ("gelmiş geçmiş en başarılı trade sistemi", 2026-10-05), BIST
hisseleri, 4 saatlik ve günlük. Videonun kuralları:
1. Moving Average Deviation(21) "yeşil" (fiyat ortalamanın çok altında, "çok ucuzladı") → takibe al. Gösterge
   TradingView'dadır; burada fiyatın SMA(21)'den sapmasının 21 barlık standart sapmaya oranı (z) `z_esik`'in altı.
2. Stokastik RSI(14): K, D'yi yukarı keserse (mavi turuncunun üstüne) → "riskli" giriş.
3. "Güvenli" giriş: ayrıca kapanış EMA(21)'in üstüne geçince.
4. Kâr al %5–7, stop %2 (videodaki RR).
Takip `bekle` bar içinde tetiklenmezse düşer. Stop ve hedef bar kapanışında denetlenir, çıkış sonraki barın açılışında
(kural 4; boşlukta kayıp %2'yi aşabilir, aleyhte). Stokastik RSI: K = SMA3((RSI − min14 RSI) / (max14 − min14)),
D = SMA3(K).
"""
from __future__ import annotations

import numpy as np

from tradebot.cekirdek.aileler import rsi
from tradebot.cekirdek.altin import ema
from tradebot.cekirdek.gosterge import kayan_max, kayan_min, kayan_std, sma
from tradebot.cekirdek.temel import Barlar


def _kuyruk(f, x: np.ndarray, n: int) -> np.ndarray:
    """Baştaki NaN'lar (ısınma) atlanarak kayan gösterge (kümülatif toplam NaN'ı ileri taşımasın)."""
    out = np.full(len(x), np.nan)
    ok = np.flatnonzero(np.isfinite(x))
    if len(ok):
        out[ok[0]:] = f(x[ok[0]:], n)
    return out


def stoch_rsi(close: np.ndarray, n_rsi: int = 14, n_stoch: int = 14) -> tuple[np.ndarray, np.ndarray]:
    r = rsi(close, n_rsi)
    lo, hi = _kuyruk(kayan_min, r, n_stoch), _kuyruk(kayan_max, r, n_stoch)
    with np.errstate(invalid="ignore", divide="ignore"):
        s = np.where(hi > lo, (r - lo) / (hi - lo), 0.5)
    s = np.where(np.isfinite(r) & np.isfinite(lo) & np.isfinite(hi), s, np.nan)
    k = _kuyruk(sma, s, 3)
    return k, _kuyruk(sma, k, 3)


def sapma_stoch(b: Barlar, z_esik: float = -2.0, guvenli: int = 1, tp: float = 0.05, sl: float = 0.02,
                n: int = 21, bekle: int = 20) -> np.ndarray:
    """Bar başına pozisyon ∈ {0, 1} (karar bar kapanışında)."""
    c = np.asarray(b.close, dtype=float)
    k_ = len(c)
    out = np.zeros(k_)
    if k_ < n + 2:
        return out
    with np.errstate(invalid="ignore", divide="ignore"):
        z = (c - sma(c, n)) / kayan_std(c, n)
    e = ema(c, n)
    k, d = stoch_rsi(c)
    poz, giris, takip, tetik = 0, 0.0, -1, -1
    for i in range(1, k_):
        if poz:
            r = c[i] / giris - 1
            if r >= tp or r <= -sl:
                poz = 0
            out[i] = poz
            continue
        if np.isfinite(z[i]) and z[i] <= z_esik:
            takip, tetik = i, -1
        if takip >= 0 and i - takip > bekle:
            takip, tetik = -1, -1
        kesis = np.isfinite(k[i]) and np.isfinite(d[i]) and np.isfinite(k[i - 1]) and np.isfinite(d[i - 1]) \
            and k[i - 1] <= d[i - 1] and k[i] > d[i]
        if takip >= 0 and tetik < 0 and kesis:
            tetik = i
        if tetik >= 0 and (not guvenli or (np.isfinite(e[i]) and c[i] > e[i])):
            poz, giris, takip, tetik = 1, c[i], -1, -1
        out[i] = poz
    return out
