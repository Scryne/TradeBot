"""Saf karar çekirdeği (spike örneği): I/O yok, yalnız verilen geçmişe bakar.

`hedef_agirlik(kapanis)` her t için hedef ağırlığı (0 ya da 1) döndürür; out[t] yalnız kapanis[: t + 1]'e bağlıdır.
Vektörel tarama tüm diziyi bir kerede verir; Nautilus sarmalayıcısı her barda o ana kadarki geçmişi verip son
elemanı alır. İki yol aynı fonksiyonu çağırır.
"""
from __future__ import annotations

import numpy as np


def hedef_agirlik(kapanis: np.ndarray, hizli: int = 20, yavas: int = 100) -> np.ndarray:
    n = len(kapanis)
    out = np.zeros(n)
    if n < yavas:
        return out
    c = np.concatenate([[0.0], np.cumsum(kapanis, dtype=float)])
    t = np.arange(yavas - 1, n)  # yavaş ortalamanın tanımlı olduğu barlar
    sma_h = (c[t + 1] - c[t + 1 - hizli]) / hizli
    sma_y = (c[t + 1] - c[t + 1 - yavas]) / yavas
    out[t] = (sma_h > sma_y).astype(float)
    return out
