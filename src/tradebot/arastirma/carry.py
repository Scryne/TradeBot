"""Kripto funding carry (dalga 1b; Final Doküman: "carry … kripto funding: yalnız paper").

Pozisyon: spot long + USDⓈ-M perp short, eşit notional (yönden bağımsız). Getiri funding'den gelir: perp short, oran
pozitifken öder alır, negatifken öder.

Zaman kuralı: karar funding anı T_i'de, yalnız ≤ T_i oranlarıyla verilir; pozisyon T_{i+1}'deki ödemeden itibaren kazanır.

Sermaye: notional N için spot N + perp teminatı N (1x, likidasyon riski yok) → N ≤ özkaynak / 2. Toplam notional
`notional` (varsayılan 0,5), sinyali açık coinler arasında eşit bölünür.

Maliyet (aleyhte): notional değişiminin iki bacağı: spot taraf (Binance spot modeli) + perp taraf (taker 5 bps + yarım
spread 1 + kayma 2 = 8 bps).
SINIR: perp fiyatı indirilmediği için baz (perp − spot) dalgalanması modellenmez. Ortalamada sıfıra döner, ama
varyansı eksik tahmin edilir. Bu yüzden carry kolu en fazla B olabilir; kanıtı paper'da toplanır.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from tradebot.arastirma.backtest import Sonuc

PERP_TARAF_BPS = 8.0
YIL_MS = 365.25 * 86_400_000


def funding_izgarasi(oranlar: dict[str, pl.DataFrame], bit_ms: int | None = None) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """(t [n], oran [n, k] (olay yoksa NaN), kimlikler). Olay anları tüm coinlerin funding zamanlarının birleşimi."""
    adlar = sorted(oranlar)
    dfs = [oranlar[a] if bit_ms is None else oranlar[a].filter(pl.col("zaman_ms") < bit_ms) for a in adlar]
    t = np.unique(np.concatenate([d["zaman_ms"].to_numpy() for d in dfs]))
    o = np.full((len(t), len(adlar)), np.nan)
    for j, d in enumerate(dfs):
        o[np.searchsorted(t, d["zaman_ms"].to_numpy()), j] = d["oran"].to_numpy()
    return t, o, adlar


def funding_sinyali(t: np.ndarray, oran: np.ndarray, pencere_gun: float, esik_yillik: float) -> np.ndarray:
    """Coin j, T_i'de son `pencere_gun` gündeki funding ödemelerinin yıllık getirisi ≥ eşikse 1 (nedensel)."""
    n, k = oran.shape
    s = np.zeros((n, k))
    pen = int(pencere_gun * 86_400_000)
    o = np.nan_to_num(oran)
    c = np.vstack([np.zeros((1, k)), np.cumsum(o, axis=0)])
    bas = np.searchsorted(t, t - pen, side="right")  # (t_i − pencere, t_i] aralığı
    toplam = c[np.arange(n) + 1] - c[bas]
    ilk = np.array([np.flatnonzero(np.isfinite(oran[:, j]))[0] if np.isfinite(oran[:, j]).any() else n for j in range(k)])
    yeterli = (t[:, None] - t[ilk.clip(max=n - 1)][None, :]) >= pen
    yillik = toplam * (YIL_MS / pen)
    s[(yillik >= esik_yillik) & yeterli] = 1.0
    return s


def calistir_carry(t: np.ndarray, oran: np.ndarray, sinyal: np.ndarray, spot_taraf_bps: float,
                   notional: float = 0.5, maliyet_carpani: float = 1.0, gecikme: int = 0) -> Sonuc:
    """Olay i'de tutulan notional sinyal[i − 1 − gecikme]'den gelir; olay i'nin getirisi Σ N_j × oran_ij − maliyet."""
    n, k = oran.shape
    s = np.vstack([np.zeros((1 + gecikme, k)), sinyal[: n - 1 - gecikme]]) if n > 1 + gecikme else np.zeros((n, k))
    adet = s.sum(axis=1, keepdims=True)
    hedef = np.where(adet > 0, s * notional / np.maximum(adet, 1), 0.0)
    dv = np.abs(np.diff(np.vstack([np.zeros((1, k)), hedef]), axis=0))
    taraf = (spot_taraf_bps + PERP_TARAF_BPS) / 1e4 * maliyet_carpani
    brut = (hedef * np.nan_to_num(oran)).sum(axis=1)
    mal = dv.sum(axis=1) * taraf
    net = brut - mal
    return Sonuc(t=t, pozisyon=np.abs(hedef).sum(axis=1) * 2, brut=brut, maliyet=mal, net=net, devir=dv.sum(axis=1),
                 ozkaynak=np.cumprod(1 + net))
