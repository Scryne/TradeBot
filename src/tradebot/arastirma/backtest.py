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
    durum: np.ndarray | None = None  # risk durumu (0 normal, 1 günlük fren, 2 haftalık fren, 3 acil durdurma)

    @property
    def islem_sayisi(self) -> int:
        return int((self.devir > 1e-9).sum())


def calistir(t: np.ndarray, fiyat: np.ndarray, sinyal: np.ndarray, mm: MaliyetModeli,
             yari_spread_bps: np.ndarray | None = None, bar_ms: int | None = None, bant: float = 0.0,
             izleyici=None) -> Sonuc:
    """`bant`: yeniden dengeleme bandı. Hedef değişmedikçe ağırlık fiyatla kayar; kayan ağırlık hedeften `bant`'tan fazla
    saparsa hedefe döndürülür. 0 = her bar hedefe dengele (sabit ağırlık); büyük bant = adedi tut (yalnız sinyal
    değişince işlem; Nautilus'taki emir mantığıyla aynı).

    `izleyici`: `risk.motor.PortfoyIzleyici`. Verilirse her bar başında özkaynakla güncellenir: fren → yeni risk yok
    (pozisyon küçülebilir, büyüyemez); acil durdurma → pozisyon 0 ve öyle kalır (onaysız yeniden başlama yok)."""
    n = len(fiyat)
    if n < 3 or len(sinyal) != n or len(t) != n:
        raise ValueError("fiyat, sinyal ve t aynı uzunlukta ve ≥ 3 olmalı")
    fiyat = np.asarray(fiyat, dtype=float)
    hedef = np.r_[0.0, np.asarray(sinyal, dtype=float)[:-1]]  # bar i'de tutulacak = sinyal[i-1]
    r = fiyat[1:] / fiyat[:-1] - 1.0                           # bar i getirisi, i = 0..n-2
    ys = np.full(n - 1, mm.yari_spread_bps) if (yari_spread_bps is None or not mm.spread_veriden) \
        else np.nan_to_num(np.asarray(yari_spread_bps, dtype=float)[:-1], nan=mm.yari_spread_bps)
    taraf = (mm.ucret_bps * (1 + mm.ucret_vergisi) + ys + mm.kayma_bps) / 1e4
    sure = np.diff(np.asarray(t, dtype=np.int64)) if bar_ms is None else np.full(n - 1, bar_ms)
    fin_oran = mm.finansman_yillik * sure / YIL_MS
    w, devir = np.empty(n - 1), np.empty(n - 1)
    islem, finansman, net = np.empty(n - 1), np.empty(n - 1), np.empty(n - 1)
    kaymis, oz, onceki_h = 0.0, 1.0, 0.0
    durumlar = np.zeros(n - 1, dtype=np.int8)
    for i in range(n - 1):  # kayma bir önceki GERÇEK ağırlığa ve maliyete bağlı → döngü
        h = hedef[i]
        if izleyici is not None:
            d = izleyici.guncelle(oz, int(t[i]))
            durumlar[i] = ("normal", "fren_gunluk", "fren_haftalik", "acil_durdurma").index(d.value)
            if d.value == "acil_durdurma":
                h = 0.0
            elif d.value != "normal" and abs(h) > abs(kaymis):
                h = kaymis  # fren: yeni risk yok
        degisti = i == 0 or h != onceki_h  # etkin hedef değişti mi (sinyal ya da fren)
        onceki_h = h
        if degisti or abs(h - kaymis) > bant:
            w[i], devir[i] = h, abs(h - kaymis)
        else:
            w[i], devir[i] = kaymis, 0.0
        islem[i] = devir[i] * taraf[i]
        finansman[i] = abs(w[i]) * fin_oran[i]
        net[i] = w[i] * r[i] - islem[i] - finansman[i]
        # bar sonunda pozisyon değeri w·(1+r), özkaynak (1+net): maliyet özkaynağı düşürdüğü için paydada
        kaymis = w[i] * (1.0 + r[i]) / (1.0 + net[i]) if abs(1.0 + net[i]) > 1e-12 else 0.0
        oz *= 1.0 + net[i]
    brut = w * r
    return Sonuc(t=np.asarray(t[:-1]), pozisyon=w, brut=brut, maliyet=islem + finansman, net=net, devir=devir,
                 ozkaynak=np.cumprod(1.0 + net), durum=durumlar if izleyici is not None else None)
