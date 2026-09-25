"""Piyasa takvimleri: bir anda piyasa açık mı, bir aralıkta hangi barlar beklenir?

Dört tür:
- `kripto_7x24`: her an açık.
- `fx_24x5`: New York saatiyle Pazar 17:00 → Cuma 17:00 (DST dahil). Dukascopy'nin hafta sonu mumları bu
  aralığın dışında kalır ve kalite raporunda "kapalı piyasa barı" olarak ayıklanır.
- `XNYS`, `XIST`: exchange_calendars; tatiller ve yarım günler dahil.

Tüm zamanlar UTC epoch milisaniye. Bar zaman damgası barın AÇILIŞ zamanıdır.
"""
from __future__ import annotations

from datetime import UTC, datetime
from functools import cache
from zoneinfo import ZoneInfo

import exchange_calendars as xc
import numpy as np
import pandas as pd

NY = ZoneInfo("America/New_York")
ZAMAN_DILIMI_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "1h": 3_600_000, "4h": 14_400_000, "1d": 86_400_000}


def ms(t: datetime) -> int:
    return int(t.astimezone(UTC).timestamp() * 1000)


def dt(t_ms: int) -> datetime:
    return datetime.fromtimestamp(t_ms / 1000, UTC)


class Takvim:
    ad: str

    def acik_mi(self, t_ms: int) -> bool:
        raise NotImplementedError

    def beklenen_barlar(self, zaman_dilimi: str, bas_ms: int, bit_ms: int) -> np.ndarray:
        """[bas, bit) aralığında, açılışı piyasanın açık olduğu bir ana denk gelen tüm bar açılış zamanları."""
        adim = ZAMAN_DILIMI_MS[zaman_dilimi]
        ilk = -(-bas_ms // adim) * adim
        aday = np.arange(ilk, bit_ms, adim, dtype=np.int64)
        return aday[self.acik_maske(aday)]

    def acik_maske(self, t_ms: np.ndarray) -> np.ndarray:
        return np.fromiter((self.acik_mi(int(t)) for t in t_ms), dtype=bool, count=len(t_ms))


class Kripto7x24(Takvim):
    ad = "kripto_7x24"

    def acik_mi(self, t_ms: int) -> bool:
        return True

    def acik_maske(self, t_ms: np.ndarray) -> np.ndarray:
        return np.ones(len(t_ms), dtype=bool)


class Fx24x5(Takvim):
    """Pazar 17:00 NY → Cuma 17:00 NY. Tatil günleri açık sayılır (düşük hacim kalite raporunda ayrıca görülür)."""

    ad = "fx_24x5"

    def acik_mi(self, t_ms: int) -> bool:
        t = dt(t_ms).astimezone(NY)
        gun, saat = t.weekday(), t.hour + t.minute / 60  # Pazartesi=0 … Pazar=6
        if gun == 5:  # Cumartesi
            return False
        if gun == 4:  # Cuma 17:00'a kadar
            return saat < 17
        if gun == 6:  # Pazar 17:00'den sonra
            return saat >= 17
        return True

    def acik_maske(self, t_ms: np.ndarray) -> np.ndarray:
        s = pd.to_datetime(t_ms, unit="ms", utc=True).tz_convert(NY)
        gun, saat = s.weekday.to_numpy(), (s.hour + s.minute / 60).to_numpy()
        return ~((gun == 5) | ((gun == 4) & (saat >= 17)) | ((gun == 6) & (saat < 17)))


class BorsaTakvimi(Takvim):
    """exchange_calendars sarmalayıcısı. Bar açık sayılır: açılışı seans içindeyse [open, close)."""

    def __init__(self, kod: str, baslangic: str = "1990-01-01") -> None:
        self.ad = kod
        self._c = xc.get_calendar(kod, start=baslangic)

    def seanslar(self, bas_ms: int, bit_ms: int) -> list[tuple[int, int]]:
        bas = pd.Timestamp(bas_ms, unit="ms", tz="UTC").tz_convert(None).normalize() - pd.Timedelta(days=1)
        bit = pd.Timestamp(bit_ms, unit="ms", tz="UTC").tz_convert(None).normalize() + pd.Timedelta(days=1)
        bas, bit = max(bas, self._c.first_session), min(bit, self._c.last_session)
        if bas > bit:
            return []
        s = self._c.schedule.loc[bas:bit]
        return [(int(o.value // 1_000_000), int(c.value // 1_000_000)) for o, c in zip(s["open"], s["close"], strict=True)]

    def acik_mi(self, t_ms: int) -> bool:
        return any(o <= t_ms < c for o, c in self.seanslar(t_ms, t_ms))

    def acik_maske(self, t_ms: np.ndarray) -> np.ndarray:
        if len(t_ms) == 0:
            return np.zeros(0, dtype=bool)
        maske = np.zeros(len(t_ms), dtype=bool)
        for o, c in self.seanslar(int(t_ms.min()), int(t_ms.max())):
            maske |= (t_ms >= o) & (t_ms < c)
        return maske

    def gunluk_barlar(self, bas_ms: int, bit_ms: int) -> np.ndarray:
        """Günlük bar açılış zamanları: seans günü 00:00 UTC (günlük veride kaynakların kullandığı gösterim)."""
        gunler = (gun_basi(o) for o, _ in self.seanslar(bas_ms, bit_ms))
        return np.array([g for g in gunler if bas_ms <= g < bit_ms], dtype=np.int64)


@cache
def takvim(ad: str) -> Takvim:
    if ad == "kripto_7x24":
        return Kripto7x24()
    if ad == "fx_24x5":
        return Fx24x5()
    return BorsaTakvimi(ad)


def gun_basi(t_ms: int) -> int:
    d = dt(t_ms)
    return ms(d.replace(hour=0, minute=0, second=0, microsecond=0))


__all__ = ["ZAMAN_DILIMI_MS", "Takvim", "takvim", "ms", "dt", "gun_basi"]
