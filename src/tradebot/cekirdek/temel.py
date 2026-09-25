"""Çekirdek tipler ve gelecek-bozma (nedensellik) testi."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np


@dataclass(frozen=True)
class Barlar:
    """Tek enstrümanın barları (numpy dizileri, açılış zamanına göre sıralı). `t`: UTC epoch ms, barın açılışı."""

    t: np.ndarray
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray

    def __len__(self) -> int:
        return len(self.t)

    def kes(self, n: int) -> Barlar:
        """İlk n bar (t = n − 1 anına kadar bilinenler)."""
        return Barlar(*(x[:n] for x in (self.t, self.open, self.high, self.low, self.close, self.volume)))

    @staticmethod
    def sozlukten(d: dict) -> Barlar:
        return Barlar(*(np.asarray(d[k], dtype=np.int64 if k == "t" else np.float64)
                        for k in ("t", "open", "high", "low", "close", "volume")))


StratejiFonksiyonu = Callable[..., np.ndarray]


@dataclass(frozen=True)
class StratejiTanimi:
    ad: str
    aile: str
    fonksiyon: StratejiFonksiyonu
    parametreler: dict = field(default_factory=dict)
    yon: str = "long"  # long | long_short

    def sinyal(self, b: Barlar) -> np.ndarray:
        s = np.asarray(self.fonksiyon(b, **self.parametreler), dtype=np.float64)
        if s.shape != (len(b),):
            raise ValueError(f"{self.ad}: sinyal boyu {s.shape}, beklenen ({len(b)},)")
        alt = -1.0 if self.yon == "long_short" else 0.0
        return np.clip(np.nan_to_num(s, nan=0.0), alt, 1.0)

    def kimlik(self) -> str:
        p = ",".join(f"{k}={v}" for k, v in sorted(self.parametreler.items()))
        return f"{self.aile}/{self.ad}({p})"


def nedensellik_testi(tanim: StratejiTanimi, b: Barlar, deneme: int = 30, tohum: int = 0) -> None:
    """t sonrası fiyatlar rastgele bozulunca out[: t + 1] değişmemeli; değişirse AssertionError (geleceği görüyor)."""
    rng = np.random.default_rng(tohum)
    temel = tanim.sinyal(b)
    n = len(b)
    for _ in range(deneme):
        t = int(rng.integers(n // 4, n - 2))
        k = rng.uniform(0.5, 2.0, n - t - 1)
        bozuk = Barlar(b.t, b.open.copy(), b.high.copy(), b.low.copy(), b.close.copy(), b.volume.copy())
        for dizi in (bozuk.open, bozuk.high, bozuk.low, bozuk.close, bozuk.volume):
            dizi[t + 1:] *= k
        yeni = tanim.sinyal(bozuk)
        if not np.array_equal(yeni[: t + 1], temel[: t + 1]):
            ilk = int(np.flatnonzero(yeni[: t + 1] != temel[: t + 1])[0])
            raise AssertionError(f"{tanim.kimlik()} geleceği görüyor: t={t} sonrası bozulunca bar {ilk} değişti")
