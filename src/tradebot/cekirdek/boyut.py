"""Boyutlandırma (saf fonksiyonlar): oynaklık hedefi, yarım Kelly, kaldıraç tavanı.

Değişmez kural 6: kaldıraç yarım Kelly; kodda SABİT 3x tavan; ≥ 5x hiçbir modda yok. Tavan bu dosyadaki sabitlerdir ve
parametreyle aşılamaz: her dış giriş `kaldirac_dogrula`dan geçer, 3'ü aşan istek hata, 5 ve üstü istek ayrı hata.
Araştırma (Spike 01): 5x ve üstü kaldıraç 12/12 yapılandırmada hesabı sıfırladı.
"""
from __future__ import annotations

import math

import numpy as np

from tradebot.cekirdek.gosterge import kayan_std, log_getiri

KALDIRAC_TAVANI = 3.0
YASAK_KALDIRAC = 5.0


class KaldiracHatasi(ValueError):
    pass


def kaldirac_dogrula(istenen: float) -> float:
    """Dışarıdan gelen her kaldıraç ayarı buradan geçer. ≥ 5x: yasak; > 3x: tavan aşımı. Döndürür: geçerli değer."""
    if not math.isfinite(istenen) or istenen < 0:
        raise KaldiracHatasi(f"geçersiz kaldıraç: {istenen}")
    if istenen >= YASAK_KALDIRAC:
        raise KaldiracHatasi(f"{istenen}x yasak: ≥ {YASAK_KALDIRAC:g}x hiçbir modda kullanılmaz (değişmez kural 6)")
    if istenen > KALDIRAC_TAVANI:
        raise KaldiracHatasi(f"{istenen}x kod tavanını ({KALDIRAC_TAVANI:g}x) aşıyor")
    return float(istenen)


def oynaklik_hedefi(sinyal: np.ndarray, close: np.ndarray, hedef_yillik: float, bar_yil: float,
                    pencere: int = 30, azami: float = 1.0) -> np.ndarray:
    """Ağırlık = sinyal × hedef oynaklık / gerçekleşen oynaklık (t'ye kadarki getirilerle, nedensel).

    `azami`: kaldıraç tavanı (≤ 3, `kaldirac_dogrula`dan geçer). Oynaklık tanımsızken (ısınma) ağırlık 0.
    """
    azami = kaldirac_dogrula(azami)
    s = kayan_std(log_getiri(close), pencere) * math.sqrt(bar_yil)
    olcek = np.where(np.isnan(s) | (s <= 0), 0.0, hedef_yillik / np.where(s > 0, s, 1.0))
    return np.clip(np.asarray(sinyal, dtype=float) * olcek, -azami, azami)


def kelly(ortalama: float, varyans: float) -> float:
    """Sürekli yaklaşımla büyümeyi azamileştiren kaldıraç: μ / σ² (aynı dönem biriminde)."""
    return ortalama / varyans if varyans > 0 else 0.0


def yarim_kelly_tavani(donem_getirileri: np.ndarray, asgari_gozlem: int = 26) -> float:
    """Stratejinin (1x) dönem getirilerinden yarım Kelly, [0, 3] aralığında. Az gözlemde 1x (temkinli)."""
    g = np.asarray(donem_getirileri, dtype=float)
    g = g[np.isfinite(g)]
    if len(g) < asgari_gozlem:
        return 1.0
    return float(min(max(0.5 * kelly(g.mean(), g.var(ddof=1)), 0.0), KALDIRAC_TAVANI))
