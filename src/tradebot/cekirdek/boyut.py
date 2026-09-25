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


def panel_oynaklik_hedefi(sinyal: np.ndarray, close: np.ndarray, evrende: np.ndarray, hedef_yillik: float,
                          bar_yil: float, pencere: int = 30, azami: float = 1.0, varlik_olcekle: bool = True,
                          varlik_tavani: float | None = None) -> np.ndarray:
    """Kol ağırlıkları [n, k] (nedensel, iki adım).

    1. Varlık: ham_j = sinyal_j / σ_j / N_t (σ_j: j'nin gerçekleşen yıllık oynaklığı, N_t: t anında evrendeki enstrüman
       sayısı). Her varlık eşit risk taşır; sinyali olmayan varlığın payı nakitte kalır. `varlik_olcekle=False` ise
       ham = sinyal (kesitsel ağırlıklar gibi zaten toplamı belli sinyaller).
    2. Kol: BUGÜNKÜ ham ağırlıkların son `pencere` barın getirilerine uygulanmasıyla bulunan ileriye dönük (ex-ante)
       oynaklık hedefe ölçeklenir. (Portföyün kendi geçmiş getirisi kullanılmaz: strateji nakitteyken o oynaklık ~0
       olur ve girişte ölçek patlar.) Tek enstrüman |ağırlık| ≤ `varlik_tavani` (risk motoru enstrüman tavanı; backtest canlı
       risk motorundan gevşek olamaz), sonra brüt maruziyet `azami`'yi aşarsa orantılı küçültülür (≤ 3x).
    Isınmada (oynaklık tanımsız) ağırlık 0."""
    azami = kaldirac_dogrula(azami)
    s = np.asarray(sinyal, dtype=float)
    c = np.asarray(close, dtype=float)
    n, k = s.shape
    ev = np.asarray(evrende, dtype=bool)
    with np.errstate(invalid="ignore", divide="ignore"):
        lr = np.vstack([np.full((1, k), np.nan), np.diff(np.log(c), axis=0)])
    if varlik_olcekle:
        sig = np.column_stack([kayan_std(lr[:, j], pencere) for j in range(k)]) * math.sqrt(bar_yil)
        adet = np.maximum(ev.sum(axis=1), 1)[:, None]
        with np.errstate(invalid="ignore", divide="ignore"):
            ham = np.where(np.isfinite(sig) & (sig > 0), s / np.where(sig > 0, sig, 1.0) / adet, 0.0)
    else:
        ham = np.nan_to_num(s)
    ham = np.where(ev, ham, 0.0)
    r = np.nan_to_num(np.expm1(lr))
    tanimli = np.isfinite(lr)
    w = np.zeros((n, k))
    kok = math.sqrt(bar_yil)
    for t in range(pencere, n):
        h = ham[t]
        aktif = h != 0
        if not aktif.any():
            continue
        # aktif varlıkların pencere boyunca getirisi tanımlı olmalı (yoksa oynaklık eksik tahmin edilir)
        if not tanimli[t - pencere + 1: t + 1, aktif].all():
            continue
        x = r[t - pencere + 1: t + 1, aktif] @ h[aktif]
        sp = float(x.std(ddof=1)) * kok
        if sp > 0:
            w[t] = h * (hedef_yillik / sp)
    if varlik_tavani is not None:
        w = np.clip(w, -varlik_tavani, varlik_tavani)
    brut = np.abs(w).sum(axis=1)
    kirp = np.where(brut > azami, azami / np.where(brut > 0, brut, 1.0), 1.0)
    return w * kirp[:, None]
