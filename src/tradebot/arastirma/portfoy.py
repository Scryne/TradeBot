"""Kol birleştirme önizlemesi (Faz 7 sermaye dağıtıcısının araştırma karşılığı).

Girdi: kolların walk-forward ÖRNEKLEM DIŞI haftalık log getirileri (turnuva JSON'ları → "haftalik.oos").
Ağırlık: eşit risk (haftalık oynaklığın tersi, toplam 1), haftalık yeniden dengeleme.
Kaldıraç: birleşik 1x serinin yarım Kelly'si. Toplam brüt maruziyet 3x kod tavanını aşamaz: kolun kendi ortalama brüt
maruziyeti (en_iyi.maruziyet) × ağırlık × kaldıraç ≤ 3.

Sınır: kolların hangisinin birleştirileceği tam dönem sonuçlarına (A/B) bakılarak seçilir; bu bir seçim yanlılığıdır.
Önizleme bu yüzden bağlayıcı değildir, bağlayıcı kanıt paper'dadır.
"""
from __future__ import annotations

import math

import numpy as np

from tradebot.arastirma import metrik as mt
from tradebot.cekirdek.boyut import KALDIRAC_TAVANI


def hizala(seriler: dict[str, dict]) -> tuple[np.ndarray, np.ndarray, list[str]]:
    """{kol: {"hafta": [...], "log": [...]}} → (haftalar, [h, k] basit getiri; kolun olmadığı hafta NaN, adlar)."""
    adlar = sorted(seriler)
    haftalar = np.unique(np.concatenate([np.asarray(seriler[a]["hafta"], dtype=np.int64) for a in adlar]))
    g = np.full((len(haftalar), len(adlar)), np.nan)
    for j, a in enumerate(adlar):
        g[np.searchsorted(haftalar, np.asarray(seriler[a]["hafta"], dtype=np.int64)), j] = np.expm1(seriler[a]["log"])
    return haftalar, g, adlar


def birlestir(seriler: dict[str, dict], maruziyet: dict[str, float], asgari_hafta: int = 26) -> dict:
    haftalar, g, adlar = hizala(seriler)
    # ağırlık: o haftaya kadarki (nedensel) haftalık oynaklığın tersi; yeterli geçmişi olmayan kol 0
    h, k = g.shape
    w = np.zeros((h, k))
    for i in range(h):
        gecmis = g[:i]
        say = np.isfinite(gecmis).sum(axis=0)
        sd = np.array([np.nanstd(gecmis[:, j], ddof=1) if say[j] >= asgari_hafta else np.nan for j in range(k)])
        ok = np.isfinite(sd) & (sd > 0) & np.isfinite(g[i])
        if ok.any():
            w[i, ok] = (1 / sd[ok]) / (1 / sd[ok]).sum()
    port = np.nansum(w * np.nan_to_num(g), axis=1)
    aktif = w.sum(axis=1) > 0
    port, haftalar_a, w_a = port[aktif], haftalar[aktif], w[aktif]
    brut = w_a @ np.array([maruziyet.get(a, 1.0) for a in adlar])
    kelly = 0.5 * port.mean() / port.var(ddof=1) if len(port) > 2 and port.var(ddof=1) > 0 else 0.0
    tavan = float(KALDIRAC_TAVANI / brut.max()) if len(brut) and brut.max() > 0 else KALDIRAC_TAVANI
    L = float(max(0.0, min(kelly, tavan, KALDIRAC_TAVANI)))
    korelasyon = _korelasyon(g)
    return {"kollar": adlar, "hafta": int(len(port)), "ilk_hafta": int(haftalar_a[0]) if len(port) else None,
            "1x": _ozet(port), "yarim_kelly": float(kelly), "brut_tavan_kaldirac": tavan, "kaldirac": L,
            "kaldiracli": _ozet(port * L), "ort_korelasyon": korelasyon,
            "son_agirlik": dict(zip(adlar, [round(float(x), 4) for x in w_a[-1]], strict=True)) if len(port) else {}}


def _ozet(r: np.ndarray) -> dict:
    if len(r) == 0:
        return {}
    r = np.maximum(r, -1.0)          # kaldıraçla −%100'ün altı: hesap sıfırlanır (özkaynak negatif olamaz)
    lg = np.log1p(np.maximum(r, -0.999999))
    oz = np.cumprod(1 + r)
    tepe = np.maximum.accumulate(np.r_[1.0, oz])[1:]
    sd = float(r.std(ddof=1)) if len(r) > 1 else 0.0
    return {"puan": float(lg.mean()), "yillik": float(oz[-1] ** (mt.YIL_HAFTA / len(r)) - 1) if oz[-1] > 0 else -1.0,
            "sifirlandi": bool((oz <= 0).any()),
            "sharpe": float(r.mean() / sd * math.sqrt(mt.YIL_HAFTA)) if sd > 0 else 0.0,
            "en_kotu_hafta": float(r.min()), "en_kotu_dusus": float((oz / tepe - 1).min()),
            "karli_hafta": float((r > 0).mean())}


def _korelasyon(g: np.ndarray) -> float:
    k = g.shape[1]
    if k < 2:
        return float("nan")
    c = []
    for i in range(k):
        for j in range(i + 1, k):
            m = np.isfinite(g[:, i]) & np.isfinite(g[:, j])
            if m.sum() > 10 and g[m, i].std() > 0 and g[m, j].std() > 0:
                c.append(np.corrcoef(g[m, i], g[m, j])[0, 1])
    return float(np.mean(c)) if c else float("nan")
