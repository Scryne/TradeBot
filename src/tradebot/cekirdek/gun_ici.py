"""Gün içi ABD endeks stratejileri, dalga 20 (docs/turnuva/Dalga-20-Gun-Ici.md). Tek enstrüman, saatlik barlar; saf ve
nedensel (kural 3): out[t] bar t'nin KAPANIŞINDA verilir ve bar t+1 boyunca tutulur.

- `gun_ici_ivme` (Gao, Han, Li, Zhou 2018, *Market Intraday Momentum*, JFE 129(2)): günün ilk yarım saatinin getirisi
  (önceki işlem gününün 16:00 NY kapanışından bugünün 10:00 NY'sine) son yarım saatin getirisini öngörür. Saatlik
  barla: r1 = close(10:00 NY) / close(önceki 16:00 NY) − 1; son `tutma` saat (16:00 − tutma → 16:00 NY) işaret(r1)
  yönünde tutulur, 16:00'da kapanır. `kisa=False`: r1 < 0 iken nakit (yalnız uzun).

Saatler New York yerel saatidir (`aileler.abd_yaz_saati`). Tatil ve yarım gün çekirdekte bilinmez: grup tanımındaki
`seans: XNYS` maskesi pozisyonu yalnız borsa seansında tutar (yarım günde 13:00'ten sonraki saatler seans dışıdır).
"""
from __future__ import annotations

import numpy as np

from tradebot.cekirdek.aileler import abd_yaz_saati
from tradebot.cekirdek.temel import Barlar

SAAT_MS = 3_600_000
GUN_MS = 86_400_000


def ny_saat(t_ms: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """UTC anı → (New York takvim günü [datetime64[D]], NY yerel saat [0, 24)). Yaz saati NY gününe göre."""
    t = np.asarray(t_ms, dtype=np.int64)
    kis = t - 5 * SAAT_MS                                          # önce kış saatiyle yerel an
    gun = (kis // GUN_MS).astype("datetime64[D]")
    yerel = np.where(abd_yaz_saati(gun), t - 4 * SAAT_MS, kis)
    return (yerel // GUN_MS).astype("datetime64[D]"), (yerel % GUN_MS) / SAAT_MS


def gun_ici_ivme(b: Barlar, tutma: int = 1, kisa: bool = False) -> np.ndarray:
    """Gün içi ivme (Gao ve ark. 2018), saatlik barlarla. Bkz. modül açıklaması."""
    n = len(b)
    out = np.zeros(n)
    if n < 2 or not 1 <= tutma <= 5:
        return out
    bar = int(np.min(np.diff(b.t)))
    if bar != SAAT_MS:
        raise ValueError("gun_ici_ivme saatlik bar ister")
    gun, saat = ny_saat(np.asarray(b.t, dtype=np.int64) + bar)      # barın KAPANIŞ anı (NY)
    onceki_kapanis = np.nan       # son 16:00 NY kapanışı (önceki işlem günü)
    r1, r1_gun = np.nan, None
    bas_saat = 16 - tutma
    for i in range(n):
        g, s = gun[i], saat[i]
        if s == 10.0 and np.isfinite(onceki_kapanis):
            r1, r1_gun = b.close[i] / onceki_kapanis - 1.0, g
        if s == 16.0:
            onceki_kapanis = b.close[i]
        # karar bar kapanışında: kapanışı [16 − tutma, 16) NY aralığındaysa sonraki bar son saat(ler)in içindedir
        if r1_gun == g and np.isfinite(r1) and bas_saat <= s < 16.0:
            out[i] = 1.0 if r1 > 0 else (-1.0 if (kisa and r1 < 0) else 0.0)
    return out
