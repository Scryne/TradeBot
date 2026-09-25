"""Sağlamlık: Probabilistic / Deflated Sharpe, walk-forward, plato, yıllık kırılım.

PSR ve DSR: Bailey & López de Prado (2012, 2014). Sharpe'lar DÖNEMLİKTİR (yıllıklandırılmamış); T gözlem sayısı.
    PSR(SR*) = Φ( (SR − SR*) √(T−1) / √(1 − γ3·SR + (γ4 − 1)/4 · SR²) )
    SR*_0    = √V[SR_n] · ( (1−γ)·Φ⁻¹(1 − 1/N) + γ·Φ⁻¹(1 − 1/(N·e)) ),   γ = 0,5772 (Euler–Mascheroni)
    DSR      = PSR(SR*_0)
N = ailenin deneme sayısı (deneme defterinden), V[SR_n] = denemelerin Sharpe varyansı.
"""
from __future__ import annotations

import itertools
import math
from collections.abc import Callable
from dataclasses import dataclass
from statistics import NormalDist

import numpy as np

from tradebot.arastirma.metrik import haftalik_log

_N = NormalDist()
EULER = 0.5772156649015329


def carpiklik_basiklik(x: np.ndarray) -> tuple[float, float]:
    """Çarpıklık ve (fazlalık OLMAYAN) basıklık; normal dağılımda (0, 3)."""
    x = np.asarray(x, dtype=float)
    m, s = x.mean(), x.std()
    if s == 0:
        return 0.0, 3.0
    z = (x - m) / s
    return float((z**3).mean()), float((z**4).mean())


def psr(sr: float, sr_esik: float, t: int, carpiklik: float = 0.0, basiklik: float = 3.0) -> float:
    payda = 1 - carpiklik * sr + (basiklik - 1) / 4 * sr**2
    if t < 2 or payda <= 0:
        return float("nan")
    return _N.cdf((sr - sr_esik) * math.sqrt(t - 1) / math.sqrt(payda))


def beklenen_max_sr(deneme: int, sr_varyansi: float) -> float:
    if deneme <= 1 or sr_varyansi <= 0:
        return 0.0
    return math.sqrt(sr_varyansi) * ((1 - EULER) * _N.inv_cdf(1 - 1 / deneme) + EULER * _N.inv_cdf(1 - 1 / (deneme * math.e)))


def dsr(sr: float, t: int, deneme: int, sr_varyansi: float, carpiklik: float = 0.0, basiklik: float = 3.0) -> float:
    return psr(sr, beklenen_max_sr(deneme, sr_varyansi), t, carpiklik, basiklik)


def haftalik_dsr(t_ms: np.ndarray, net: np.ndarray, deneme: int, aile_haftalik_sr: list[float]) -> dict:
    """Stratejinin haftalık getirilerinden DSR.

    `aile_haftalik_sr`: ailenin denemelerinin haftalık (yıllıklandırılmamış) Sharpe'ları.
    """
    h = np.expm1(haftalik_log(t_ms, net))
    if len(h) < 10 or h.std(ddof=1) == 0:
        return {"dsr": float("nan"), "hafta": int(len(h))}
    sr = float(h.mean() / h.std(ddof=1))
    g3, g4 = carpiklik_basiklik(h)
    v = float(np.var(aile_haftalik_sr, ddof=1)) if len(aile_haftalik_sr) > 1 else 0.0
    return {"dsr": dsr(sr, len(h), max(deneme, 1), v, g3, g4), "sr_haftalik": sr, "sr_esik": beklenen_max_sr(deneme, v),
            "hafta": int(len(h)), "deneme": int(deneme), "carpiklik": g3, "basiklik": g4}


# --- walk-forward ---
@dataclass(frozen=True)
class Pencere:
    is_bas: int
    is_bit: int
    oos_bas: int
    oos_bit: int


def pencereler(t: np.ndarray, is_ms: int, oos_ms: int) -> list[Pencere]:
    """Kayan IS/OOS pencereleri. Son bar [t[-1], t[-1] + adım) aralığını kapsar; pencere sonu buna kadar gidebilir."""
    adim = int(np.median(np.diff(t))) if len(t) > 1 else 1
    out, bas = [], int(t[0])
    while bas + is_ms + oos_ms <= int(t[-1]) + adim:
        out.append(Pencere(bas, bas + is_ms, bas + is_ms, bas + is_ms + oos_ms))
        bas += oos_ms
    return out


def walk_forward(t: np.ndarray, kosular: dict[str, dict], is_ms: int, oos_ms: int,
                 puan: Callable[[np.ndarray, np.ndarray], float], taraf_maliyet: float = 0.0) -> dict:
    """`kosular`: parametre kimliği → {"net": bar net getirisi, "pozisyon": bar pozisyonu} (TÜM dönem, nedensel sinyalle).
    Her pencerede IS puanı en yüksek parametre seçilir, OOS getirileri art arda eklenir. Seçim değişince eski ve yeni
    pozisyon farkı kadar geçiş maliyeti OOS'un ilk barına yazılır."""
    t = np.asarray(t)
    oos_net, secimler, onceki = [], [], None
    for p in pencereler(t, is_ms, oos_ms):
        is_m = (t >= p.is_bas) & (t < p.is_bit)
        oos_m = (t >= p.oos_bas) & (t < p.oos_bit)
        en_iyi = max(kosular, key=lambda k: puan(t[is_m], kosular[k]["net"][is_m]))
        parca = kosular[en_iyi]["net"][oos_m].copy()
        if onceki is not None and onceki != en_iyi and len(parca):
            i0 = int(np.flatnonzero(oos_m)[0])
            parca[0] -= abs(kosular[en_iyi]["pozisyon"][i0] - kosular[onceki]["pozisyon"][i0]) * taraf_maliyet
        oos_net.append(parca)
        secimler.append({"oos_bas": p.oos_bas, "secilen": en_iyi, "is_puan": puan(t[is_m], kosular[en_iyi]["net"][is_m])})
        onceki = en_iyi
    if not oos_net:
        return {"pencere": 0}
    oos_t = np.concatenate([t[(t >= p.oos_bas) & (t < p.oos_bit)] for p in pencereler(t, is_ms, oos_ms)])
    net = np.concatenate(oos_net)
    return {"pencere": len(secimler), "secimler": secimler, "t": oos_t, "net": net, "ozkaynak": np.cumprod(1 + net),
            "farkli_secim": len({s["secilen"] for s in secimler})}


# --- plato ---
def izgara(uzay: dict[str, list]) -> list[dict]:
    anahtar = sorted(uzay)
    return [dict(zip(anahtar, deger, strict=True)) for deger in itertools.product(*(uzay[k] for k in anahtar))]


def plato(uzay: dict[str, list], puanlar: dict[str, float], kimlik: Callable[[dict], str]) -> dict:
    """En iyi parametrenin ızgaradaki komşuları (bir parametrede bir adım) ortalama olarak en iyinin en az yarısını
    koruyorsa plato var. Tek nokta tepe = aşırı uyum işareti."""
    ps = izgara(uzay)
    en_iyi = max(ps, key=lambda p: puanlar[kimlik(p)])
    en_iyi_puan = puanlar[kimlik(en_iyi)]
    komsu = []
    for k, degerler in uzay.items():
        i = degerler.index(en_iyi[k])
        for j in (i - 1, i + 1):
            if 0 <= j < len(degerler):
                komsu.append(puanlar[kimlik({**en_iyi, k: degerler[j]})])
    oran = float(np.mean(komsu) / en_iyi_puan) if komsu and en_iyi_puan > 0 else float("nan")
    return {"en_iyi": en_iyi, "en_iyi_puan": en_iyi_puan, "komsu_sayisi": len(komsu),
            "komsu_ortalama": float(np.mean(komsu)) if komsu else float("nan"), "plato_orani": oran,
            "plato_var": bool(oran >= 0.5) if not math.isnan(oran) else False}


def yillik_kirilim(t_ms: np.ndarray, net: np.ndarray) -> dict[int, float]:
    """Yıl başına bileşik getiri (performans tek yıla mı dayanıyor?)."""
    yil = (np.asarray(t_ms, dtype="datetime64[ms]").astype("datetime64[Y]").astype(int) + 1970)
    return {int(y): float(np.prod(1 + net[yil == y]) - 1) for y in np.unique(yil)}
