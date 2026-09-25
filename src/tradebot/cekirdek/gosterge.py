"""Nedensel göstergeler: her çıktı t yalnız girdi[: t + 1]'e bağlıdır. Tanımsız ısınma dönemi NaN."""
from __future__ import annotations

import numpy as np


def sma(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if n <= 0 or len(x) < n:
        return out
    c = np.cumsum(np.r_[0.0, x])
    out[n - 1:] = (c[n:] - c[:-n]) / n
    return out


def kayan_max(x: np.ndarray, n: int) -> np.ndarray:
    """Önceki n barın en yükseği (t HARİÇ): kırılım 'bugün geçmişin tepesini aştı mı' için."""
    from numpy.lib.stride_tricks import sliding_window_view

    out = np.full(len(x), np.nan)
    if len(x) > n:
        out[n:] = sliding_window_view(x[:-1], n).max(axis=1)
    return out


def kayan_min(x: np.ndarray, n: int) -> np.ndarray:
    from numpy.lib.stride_tricks import sliding_window_view

    out = np.full(len(x), np.nan)
    if len(x) > n:
        out[n:] = sliding_window_view(x[:-1], n).min(axis=1)
    return out


def log_getiri(close: np.ndarray) -> np.ndarray:
    r = np.full(len(close), np.nan)
    r[1:] = np.diff(np.log(close))
    return r


def kayan_std(x: np.ndarray, n: int) -> np.ndarray:
    """Pencere içindeki tanımlı değerlerin örneklem std'si (ddof=1; NaN'ler atlanır, < 2 değerde NaN). O(len) kümülatif
    toplamlarla; sayısal kararlılık için değerler önce ilk tanımlı değere göre ötelenir (std ötelemeden bağımsız)."""
    x = np.asarray(x, dtype=float)
    out = np.full(len(x), np.nan)
    if n < 2 or len(x) < n:
        return out
    ok = np.isfinite(x)
    ref = x[ok][0] if ok.any() else 0.0
    y = np.where(ok, x - ref, 0.0)
    c1 = np.r_[0.0, np.cumsum(y)]
    c2 = np.r_[0.0, np.cumsum(y * y)]
    cn = np.r_[0, np.cumsum(ok)]
    s1, s2, m = c1[n:] - c1[:-n], c2[n:] - c2[:-n], (cn[n:] - cn[:-n]).astype(float)
    with np.errstate(invalid="ignore", divide="ignore"):
        var = (s2 - s1 * s1 / m) / (m - 1)
    out[n - 1:] = np.where(m >= 2, np.sqrt(np.maximum(var, 0.0)), np.nan)
    return out
