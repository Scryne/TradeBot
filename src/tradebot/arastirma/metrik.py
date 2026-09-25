"""Turnuva metrikleri (Final Doküman §Turnuva).

Ana puan: haftalık net log büyümenin ortalaması (haftalar UTC Pazartesi 00:00 başlar).
Kapılar: en kötü hafta ≥ −%10, en kötü düşüş ≥ −%30, yeterli işlem; DSR `dogrulama.py`'de.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np

HAFTA_MS = 7 * 86_400_000
PAZARTESI_KAYMA_MS = 4 * 86_400_000  # 1970-01-01 Perşembe → ilk Pazartesi 1970-01-05
YIL_HAFTA = 52.1775

KAPI_EN_KOTU_HAFTA = -0.10
KAPI_EN_KOTU_DUSUS = -0.30
KAPI_ASGARI_ISLEM = 20


@dataclass(frozen=True)
class Metrik:
    puan: float                # ortalama haftalık log büyüme
    hafta: int
    yillik_bilesik: float
    yillik_oynaklik: float
    sharpe: float              # haftalık getirilerden yıllıklandırılmış
    en_kotu_hafta: float
    en_iyi_hafta: float
    karli_hafta_orani: float
    en_kotu_dusus: float
    islem: int
    yillik_devir: float
    maruziyet: float
    maliyet_payi: float        # toplam maliyet / toplam |brüt getiri|
    kapilar_gecti: bool

    def sozluk(self) -> dict:
        return {k: (round(v, 6) if isinstance(v, float) else v) for k, v in asdict(self).items()}


def haftalik_log(t: np.ndarray, net: np.ndarray) -> np.ndarray:
    hafta = (np.asarray(t, dtype=np.int64) - PAZARTESI_KAYMA_MS) // HAFTA_MS
    lg = np.log1p(np.maximum(net, -0.999999))
    _, ters = np.unique(hafta, return_inverse=True)
    return np.bincount(ters, weights=lg)


def hesapla(sonuc) -> Metrik:
    hl = haftalik_log(sonuc.t, sonuc.net)
    hs = np.expm1(hl)
    oz = sonuc.ozkaynak
    tepe = np.maximum.accumulate(np.r_[1.0, oz])[1:]
    dusus = float((oz / tepe - 1).min()) if len(oz) else 0.0
    yil = max(len(hl) / YIL_HAFTA, 1e-9)
    std = float(hs.std(ddof=1)) if len(hs) > 1 else 0.0
    brut_mutlak = float(np.abs(sonuc.brut).sum())
    m = Metrik(
        puan=float(hl.mean()) if len(hl) else 0.0,
        hafta=int(len(hl)),
        yillik_bilesik=float(oz[-1] ** (1 / yil) - 1) if len(oz) and oz[-1] > 0 else -1.0,
        yillik_oynaklik=std * np.sqrt(YIL_HAFTA),
        sharpe=float(hs.mean() / std * np.sqrt(YIL_HAFTA)) if std > 0 else 0.0,
        en_kotu_hafta=float(hs.min()) if len(hs) else 0.0,
        en_iyi_hafta=float(hs.max()) if len(hs) else 0.0,
        karli_hafta_orani=float((hs > 0).mean()) if len(hs) else 0.0,
        en_kotu_dusus=dusus,
        islem=sonuc.islem_sayisi,
        yillik_devir=float(sonuc.devir.sum() / yil),
        maruziyet=float(np.abs(sonuc.pozisyon).mean()),
        maliyet_payi=float(sonuc.maliyet.sum() / brut_mutlak) if brut_mutlak > 0 else 0.0,
        kapilar_gecti=False,
    )
    gecti = m.en_kotu_hafta >= KAPI_EN_KOTU_HAFTA and m.en_kotu_dusus >= KAPI_EN_KOTU_DUSUS and m.islem >= KAPI_ASGARI_ISLEM
    return Metrik(**{**asdict(m), "kapilar_gecti": bool(gecti)})
