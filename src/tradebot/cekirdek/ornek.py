"""Örnek (referans) stratejiler: motorun, parity'nin ve nedensellik testinin sınanması için.

Turnuva aileleri Faz 5'te bu dosyanın yanına eklenir; bunlar da onlardan biri gibi saf fonksiyondur.
"""
from __future__ import annotations

import numpy as np

from tradebot.cekirdek.gosterge import kayan_max, kayan_min, kayan_std, log_getiri, sma
from tradebot.cekirdek.temel import Barlar


def sma_kesisim(b: Barlar, hizli: int = 20, yavas: int = 100) -> np.ndarray:
    """Hızlı ortalama yavaşın üstündeyse 1, değilse 0 (yavaş tanımlanana kadar 0)."""
    h, y = sma(b.close, hizli), sma(b.close, yavas)
    return np.where(np.isnan(y), 0.0, (h > y).astype(float))


def donchian(b: Barlar, giris: int = 20, cikis: int = 10) -> np.ndarray:
    """Kapanış önceki `giris` barın tepesini aşınca gir; önceki `cikis` barın dibini kırınca çık (durumlu, nedensel)."""
    ust, alt = kayan_max(b.high, giris), kayan_min(b.low, cikis)
    out = np.zeros(len(b))
    poz = 0.0
    for i in range(len(b)):
        if poz == 0.0 and not np.isnan(ust[i]) and b.close[i] > ust[i]:
            poz = 1.0
        elif poz == 1.0 and not np.isnan(alt[i]) and b.close[i] < alt[i]:
            poz = 0.0
        out[i] = poz
    return out


def tsmom(b: Barlar, ufuk: int = 60, vol_pencere: int = 30, hedef_vol: float = 0.0) -> np.ndarray:
    """Zaman serisi momentumu: son `ufuk` bar getirisinin işareti. hedef_vol > 0 ise |sinyal| = hedef / gerçekleşen oynaklık
    (bar başına), [-1, 1]'e kırpılır; yön kısıtı StratejiTanimi.yon ile uygulanır."""
    r = log_getiri(b.close)
    toplam = np.full(len(b), np.nan)
    if len(b) > ufuk:
        c = np.cumsum(np.r_[0.0, np.nan_to_num(r)])
        toplam[ufuk:] = c[ufuk + 1:] - c[1:-ufuk]
    yon = np.sign(np.nan_to_num(toplam))
    if hedef_vol > 0:
        s = kayan_std(r, vol_pencere)
        olcek = np.where(np.isnan(s) | (s <= 0), 0.0, hedef_vol / np.where(s > 0, s, 1.0))
        return np.clip(yon * olcek, -1.0, 1.0)
    return yon
