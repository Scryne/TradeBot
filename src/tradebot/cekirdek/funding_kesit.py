"""Kesitsel funding (Dalga 17) — saf karar çekirdeği (kural 3). I/O yok.

Haftalık (Pazartesi 00:00 UTC) yeniden dengeleme: uygun evren (karar anında listelenmiş ≥ 30 gün, önceki 30 günün
ortalama günlük quote hacmine göre ilk `evren`, sabit paralar hariç) içinde son `pencere` günün ortalama günlük
funding'ine göre sıralanır. Funding'i en yüksek `n` perp kısa (kalabalık uzunlar; kısa funding alır), en düşük `n`
uzun. Her bacak eşit ağırlık, bacak toplamı `brut / 2` (dolar nötr). Yalnız karar anından önce ödenmiş funding görülür.
"""
from __future__ import annotations

from dataclasses import dataclass

SABIT = frozenset({"USDC", "BUSD", "TUSD", "FDUSD", "DAI", "USDP", "USDE", "PYUSD", "USD1", "EUR", "UST", "USTC"})


@dataclass(frozen=True)
class KesitKural:
    pencere: int = 7          # funding ortalama penceresi (gün)
    n: int = 5                # bacak başına perp sayısı
    evren: int = 50           # hacme göre ilk N
    brut: float = 1.0         # toplam brüt / özkaynak

    def __post_init__(self) -> None:
        if self.brut > 3.0:
            raise ValueError("brüt 3x tavanını aşamaz (kural 6)")
        if 2 * self.n > self.evren:
            raise ValueError("2n evrenden büyük olamaz")


def agirliklar(hacim: dict[str, float], funding_ort: dict[str, float], kural: KesitKural) -> dict[str, float]:
    """{sembol: ağırlık} (+ uzun, − kısa). `hacim` yalnız uygun (yaş, veri) adayları içerir; funding'i olmayan elenir."""
    aday = sorted((s for s in hacim if s not in SABIT and s in funding_ort), key=lambda s: (-hacim[s], s))[: kural.evren]
    if len(aday) < 2 * kural.n:
        return {}
    sirali = sorted(aday, key=lambda s: (funding_ort[s], s))
    w = kural.brut / 2 / kural.n
    return {**{s: w for s in sirali[: kural.n]}, **{s: -w for s in sirali[-kural.n:]}}
