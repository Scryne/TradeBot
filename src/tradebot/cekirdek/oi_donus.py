"""OI temizlenmesi sonrası dönüş (Dalga 16) — saf karar çekirdeği (kural 3). I/O yok.

Olay (saat `t`, kapanmış bar): perp'in `t` saatlik getirisi, önceki 720 saatin saatlik log getiri oynaklığının
`k` katından daha sert düşmüş VE açık pozisyon (OI, saatin son ölçümü) bir önceki saate göre `oi_esik`'ten fazla
azalmış (zorunlu kapanış: likidasyon / marj çağrısı). `oi_esik` None ise yalnız fiyat koşulu (kontrol kolu: OI
bilgisinin katkısını ayırır). Uygunluk: önceki 720 saatin ortalama günlük quote hacmi ≥ `asgari_hacim` ve en az 720
saatlik geçmiş. Giriş `t+1` açılışında (çağıran), çıkış `t+1+tut` açılışında.

`ozellik` yalnız `t`'ye kadar olan barları kullanır (bozma testi: `t`'den sonrası değişince sonuç değişmez).
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np

PENCERE = 720   # 30 gün × 24 saat


@dataclass(frozen=True)
class DonusKural:
    k: float = 4.0                      # düşüş eşiği: saatlik getiri ≤ −k × σ
    oi_esik: float | None = -0.05       # OI değişimi ≤ bu (None: koşul yok)
    tut: int = 4                        # tutma süresi (saat)
    asgari_hacim: float = 2e7           # günlük ortalama quote hacmi (USDT)


def ozellik(open_: np.ndarray, close: np.ndarray, qv: np.ndarray, oi: np.ndarray) -> dict[str, np.ndarray]:
    """Saatlik diziler (ardışık saat ızgarası, eksik = NaN) → her `t` için z, OI değişimi, hacim, geçmiş yeterli mi.

    z_t = log(close_t / open_t) / σ_t; σ_t = önceki PENCERE saatin (t hariç) close→close log getiri std'si."""
    n = len(close)
    lr = np.full(n, np.nan)
    lr[1:] = np.log(close[1:] / close[:-1])
    bar = np.log(close / open_)
    sig = np.full(n, np.nan)
    hacim = np.full(n, np.nan)
    if n > PENCERE:
        from numpy.lib.stride_tricks import sliding_window_view as kay
        w = kay(lr[:-1], PENCERE)                    # w[i] = lr[i .. i+PENCERE-1] → t = i + PENCERE için önceki pencere
        with np.errstate(invalid="ignore"):
            sig[PENCERE:] = np.nanstd(w, axis=1, ddof=1)[: n - PENCERE]
            gecerli = np.sum(~np.isnan(w), axis=1)[: n - PENCERE]
            sig[PENCERE:][gecerli < PENCERE * 0.9] = np.nan
        qw = kay(np.nan_to_num(qv[:-1]), PENCERE)
        hacim[PENCERE:] = qw.sum(axis=1)[: n - PENCERE] / 30.0
    doi = np.full(n, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        doi[1:] = oi[1:] / oi[:-1] - 1
    return {"z": bar / sig, "doi": doi, "hacim": hacim}


def olay_mu(z: float, doi: float, hacim: float, kural: DonusKural) -> bool:
    if not (np.isfinite(z) and np.isfinite(hacim)) or hacim < kural.asgari_hacim or z > -kural.k:
        return False
    if kural.oi_esik is None:
        return True
    return bool(np.isfinite(doi) and doi <= kural.oi_esik)
