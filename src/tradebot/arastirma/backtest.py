"""Vektörel backtest motoru (tek enstrüman). Turnuvanın bağlayıcı metrik kaynağı (Final Doküman §7).

Zaman kuralı: sinyal[t] bar t'nin KAPANIŞINDA verilir → pozisyon bar t+1'in başında `fiyat[t+1]`'den kurulur.
`fiyat` varsayılan olarak açılıştır (sonraki bar açılışında dolum); Nautilus parity'si için başka bir yürütme fiyatı
(ör. sonraki ilk dakikanın kapanışı) verilebilir. Bar i getirisi: fiyat[i+1] / fiyat[i] − 1 (i tutulan pozisyonla).

Maliyet: her bar başında hedefe getirmek için gereken devir × taraf maliyeti. Devir kaymayı hesaba katar:
bar boyunca fiyat değişince ağırlık w·(1+r)/(1+w·r)'ye kayar; hedefe geri dönmek de işlemdir.
Finansman: |pozisyon| × yıllık oran × bar süresi (yalnız modelde finansman varsa).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from tradebot.arastirma.maliyet import YIL_MS, MaliyetModeli


@dataclass(frozen=True)
class Sonuc:
    t: np.ndarray           # bar açılışları (getiri dizisiyle aynı uzunluk: son bar hariç)
    pozisyon: np.ndarray    # bar i boyunca tutulan hedef ağırlık
    brut: np.ndarray        # maliyetsiz bar getirisi
    maliyet: np.ndarray     # işlem maliyeti + finansman (getiri birimi)
    net: np.ndarray         # net bar getirisi
    devir: np.ndarray       # bar başındaki |Δağırlık|
    ozkaynak: np.ndarray    # 1'den başlayan birikimli özkaynak (net)

    @property
    def islem_sayisi(self) -> int:
        return int((self.devir > 1e-9).sum())


def calistir(t: np.ndarray, fiyat: np.ndarray, sinyal: np.ndarray, mm: MaliyetModeli,
             yari_spread_bps: np.ndarray | None = None, bar_ms: int | None = None) -> Sonuc:
    n = len(fiyat)
    if n < 3 or len(sinyal) != n or len(t) != n:
        raise ValueError("fiyat, sinyal ve t aynı uzunlukta ve ≥ 3 olmalı")
    fiyat = np.asarray(fiyat, dtype=float)
    hedef = np.r_[0.0, np.asarray(sinyal, dtype=float)[:-1]]  # bar i'de tutulacak = sinyal[i-1]
    r = fiyat[1:] / fiyat[:-1] - 1.0                           # bar i getirisi, i = 0..n-2
    w = hedef[:-1]
    # kayma: bar i sonunda ağırlık w·(1+r)/(1+w·r); bar i+1 başında hedefe getirme devri
    kaymis = np.zeros(n - 1)
    payda = 1.0 + w * r
    np.divide(w * (1.0 + r), payda, out=kaymis, where=np.abs(payda) > 1e-12)
    onceki = np.r_[0.0, kaymis[:-1]]
    devir = np.abs(w - onceki)
    ys = np.full(n - 1, mm.yari_spread_bps) if (yari_spread_bps is None or not mm.spread_veriden) \
        else np.nan_to_num(np.asarray(yari_spread_bps, dtype=float)[:-1], nan=mm.yari_spread_bps)
    taraf = (mm.ucret_bps * (1 + mm.ucret_vergisi) + ys + mm.kayma_bps) / 1e4
    islem = devir * taraf
    sure = np.diff(np.asarray(t, dtype=np.int64)) if bar_ms is None else np.full(n - 1, bar_ms)
    finansman = np.abs(w) * mm.finansman_yillik * sure / YIL_MS
    brut = w * r
    net = brut - islem - finansman
    return Sonuc(t=np.asarray(t[:-1]), pozisyon=w, brut=brut, maliyet=islem + finansman, net=net, devir=devir,
                 ozkaynak=np.cumprod(1.0 + net))
