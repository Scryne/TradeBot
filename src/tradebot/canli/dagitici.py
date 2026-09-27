"""Sermaye dağıtıcı (Faz 7; Final Doküman §Sermaye dağıtıcı, gerekçe `docs/Paper-Tasarim.md`).

Haftada bir (Pazartesi 00:00 UTC) kaynak kolların paper defterinden, o ana kadar kesilmiş günlük getirilerle:
1. **Risk paritesi (korelasyonlu):** kovaryansla eşit risk katkısı (ERC). Ortak geçmiş yetersizse korelasyon 1 varsayılır
   (temkinli: çeşitlendirme varsayılmaz).
2. **Üstünlük eğimi (küçültülmüş tahmin):** Sharpe = (önsel × önsel_gün + paper × paper_gün) / toplam gün. Önsel, backtest
   walk-forward OOS Sharpe'ının `onsel_indirim` katıdır (seçim yanlılığı payı). Eğim = 1 + (Sharpe − ortalama), [0,5; 1,5]
   aralığında. Tahmini ≤ 0 olan kol pay almaz.
3. **Kaldıraç:** birleşik portföyün yarım Kelly'si (μ_p / σ_p² × 0,5), en fazla 3x (kural 6; `kaldirac_dogrula`).
4. **Kademe:** paper'daki gün sayısına göre 4 hafta %25, 8 hafta %50, 12 hafta %100. Yalnız A sınıfı kol sermaye alır;
   B kolunun katsayısı 0'dır, gölge ağırlığı yine hesaplanır ve kaydedilir.

Çıktı kaynak kol başına katsayıdır: portföy hedefi = Σ katsayı × kolun güncel (fren ve veto sonrası) hedefi.
Saf fonksiyonlar: I/O yok, girdi yalnız hafta başına kadar kesilmiş veridir.
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass

import numpy as np

from tradebot.cekirdek.boyut import KALDIRAC_TAVANI, kaldirac_dogrula

GUN_MS = 86_400_000
HAFTA_MS = 7 * GUN_MS
PAZARTESI_MS = 4 * GUN_MS  # 1970-01-05 Pazartesi
YIL_GUN = 365.0            # takvim günü: kapalı günlerin getirisi 0, yıllıklaştırma yine doğru


def hafta_basi(ms: int) -> int:
    """ms'yi içeren haftanın Pazartesi 00:00 UTC'si."""
    return ms - (ms - PAZARTESI_MS) % HAFTA_MS


@dataclass(frozen=True)
class DagiticiAyar:
    onsel_indirim: float = 0.5     # backtest OOS Sharpe'ı yarıya: seçim yanlılığı ve rejim payı
    onsel_gun: float = 365.0       # önselin ağırlığı (paper günü cinsinden)
    asgari_gun: int = 28           # altında kol dağıtıma girmez (σ tanımsız)
    pencere_gun: int = 180         # σ ve korelasyon penceresi
    egim_alt: float = 0.5
    egim_ust: float = 1.5
    kelly_kesri: float = 0.5       # yarım Kelly (Final Doküman); üstü reddedilir
    kademe: tuple[tuple[int, float], ...] = ((28, 0.25), (56, 0.5), (84, 1.0))

    def __post_init__(self) -> None:
        if not 0 <= self.kelly_kesri <= 0.5:
            raise ValueError(f"kelly_kesri {self.kelly_kesri}: yarım Kelly'nin üstü yok")

    def sozluk(self) -> dict:
        return {k: (list(map(list, v)) if k == "kademe" else v) for k, v in asdict(self).items()}


def kademe_orani(gun: float, ayar: DagiticiAyar) -> float:
    oran = 0.0
    for esik, o in ayar.kademe:
        if gun >= esik:
            oran = o
    return oran


def gunluk_getiri(isaretler: list[tuple[int, float]], bit_ms: int) -> dict[int, float]:
    """Saatlik özkaynak işaretlerinden günlük log getiri: gün sonu = o UTC gününün son işareti (bit_ms'den önce).
    Döndürür: {gün başı ms: önceki işaretli günden bu güne log getiri}."""
    gun_sonu: dict[int, float] = {}
    for t, oz in isaretler:
        if t < bit_ms and oz > 0:
            gun_sonu[t - t % GUN_MS] = oz  # sıralı gelir: son yazılan günün son işaretidir
    gunler = sorted(gun_sonu)
    return {g: math.log(gun_sonu[g] / gun_sonu[o]) for o, g in zip(gunler, gunler[1:], strict=False)}


def erc(kov: np.ndarray, yineleme: int = 500) -> np.ndarray:
    """Eşit risk katkısı ağırlıkları (toplam 1). Kovaryans pozitif katkı vermiyorsa ters oynaklığa düşer."""
    sd = np.sqrt(np.diag(kov))
    w = (1 / sd) / (1 / sd).sum()
    for _ in range(yineleme):
        kw = kov @ w
        if (kw <= 0).any():
            return (1 / sd) / (1 / sd).sum()
        rc = w * kw
        w = w * np.sqrt(rc.mean() / rc)
        w /= w.sum()
    return w


def dagit(getiri: dict[str, dict[int, float]], paper_gun: dict[str, float], sinif: dict[str, str],
          onsel: dict[str, float], ayar: DagiticiAyar) -> dict:
    """Kaynak kolların günlük log getirilerinden (hafta başına kadar) katsayılar. Bkz. modül açıklaması."""
    kollar = sorted(getiri)
    satir = {k: {"sinif": sinif.get(k, "B"), "gun": float(paper_gun.get(k, 0.0)), "gozlem": len(getiri[k]),
                 "katsayi": 0.0, "agirlik": 0.0} for k in kollar}
    uygun = [k for k in kollar if len(getiri[k]) >= ayar.asgari_gun]
    sonuc = {"ayar": ayar.sozluk(), "kollar": satir, "uygun": uygun, "kaldirac": 0.0, "kaldirac_golge": 0.0}
    if not uygun:
        return sonuc

    sigma, s_paper, s_kucuk = {}, {}, {}
    for k in uygun:
        gs = sorted(getiri[k])[-ayar.pencere_gun:]
        r = np.array([getiri[k][g] for g in gs])
        sd = float(r.std(ddof=1)) if len(r) > 1 else 0.0
        sigma[k] = sd * math.sqrt(YIL_GUN)
        s_paper[k] = float(r.mean() / sd * math.sqrt(YIL_GUN)) if sd > 0 else 0.0
        on = ayar.onsel_indirim * float(onsel.get(k, 0.0))
        n = float(len(getiri[k]))
        s_kucuk[k] = (on * ayar.onsel_gun + s_paper[k] * n) / (ayar.onsel_gun + n)
        satir[k] |= {"sigma": sigma[k], "sharpe_paper": s_paper[k], "sharpe_onsel": on, "sharpe": s_kucuk[k]}
    uygun = [k for k in uygun if sigma[k] > 0]
    if not uygun:
        return sonuc

    # korelasyon: ortak günlerde (pencere); yetersizse 1 (temkinli)
    ortak = sorted(set.intersection(*(set(getiri[k]) for k in uygun)))[-ayar.pencere_gun:]
    sd = np.array([sigma[k] for k in uygun])
    if len(uygun) > 1 and len(ortak) >= ayar.asgari_gun:
        m = np.array([[getiri[k][g] for g in ortak] for k in uygun])
        kor = np.nan_to_num(np.corrcoef(m), nan=1.0)
        np.fill_diagonal(kor, 1.0)
    else:
        kor = np.ones((len(uygun), len(uygun)))
    kov = kor * np.outer(sd, sd)

    temel = erc(kov)
    s = np.array([s_kucuk[k] for k in uygun])
    egim = np.where(s > 0, np.clip(1 + (s - s[s > 0].mean() if (s > 0).any() else 0.0), ayar.egim_alt, ayar.egim_ust), 0.0)
    ust = np.triu_indices(len(uygun), 1)
    sonuc |= {"ortak_gun": len(ortak), "korelasyon_ort": float(kor[ust].mean()) if len(uygun) > 1 else None}
    for j, k in enumerate(uygun):
        satir[k] |= {"erc": float(temel[j]), "egim": float(egim[j])}
    w = temel * egim
    if w.sum() <= 0:  # hiçbir kolun tahmini pozitif değil: dağıtım yok
        return sonuc
    w /= w.sum()

    mu_p = float(w @ (s * sd))
    var_p = float(w @ kov @ w)
    kelly = ayar.kelly_kesri * mu_p / var_p if var_p > 0 else 0.0
    L = kaldirac_dogrula(float(min(max(kelly, 0.0), KALDIRAC_TAVANI)))
    for j, k in enumerate(uygun):
        kd = kademe_orani(satir[k]["gun"], ayar)
        a_mi = satir[k]["sinif"] == "A"
        satir[k] |= {"agirlik": float(w[j]), "kademe": kd, "katsayi": float(L * w[j] * kd) if a_mi else 0.0}
    sonuc |= {"kaldirac_golge": L, "mu_p": mu_p, "sigma_p": math.sqrt(var_p),
              "kaldirac": float(sum(satir[k]["katsayi"] for k in uygun))}
    return sonuc


def portfoy_hedef(katsayi: dict[str, float], kaynak_hedef: dict[str, dict[str, float]], kimlikler: list[str],
                  tavan: float, long_short: bool) -> np.ndarray:
    """Portföy hedef ağırlığı = Σ katsayı × kaynak kolun güncel etkin hedefi; enstrüman tavanıyla kırpılır.
    Brüt tavanı risk motoru uygular."""
    h = np.zeros(len(kimlikler))
    for kol, c in katsayi.items():
        if c:
            h += c * np.array([kaynak_hedef.get(kol, {}).get(k, 0.0) for k in kimlikler])
    return np.clip(h, -tavan if long_short else 0.0, tavan)
