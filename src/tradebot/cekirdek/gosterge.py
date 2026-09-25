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
    from numpy.lib.stride_tricks import sliding_window_view

    out = np.full(len(x), np.nan)
    if len(x) >= n:
        out[n - 1:] = np.nanstd(sliding_window_view(x, n), axis=1, ddof=1)
    return out
