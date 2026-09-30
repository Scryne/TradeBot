"""ABD hisse endeksi olay ve takvim primleri (dalga 11; docs/turnuva/Dalga-11-Endeks.md). Tek enstrüman, yalnız uzun;
saf ve nedensel. Sinyal yalnız bar zamanından (önceden bilinen takvim) üretilir, fiyata bakmaz.

Zaman kuralı: out[t] bar t'nin KAPANIŞINDA verilir, bar t+1 boyunca tutulur; [E, X) penceresinde tutulan barlar,
açılışı (t + bar) bu aralıkta olanlardır. Saatler New York yerel saatidir (ABD yaz saati `abd_yaz_saati`).

- `fomc_oncesi` (Lucca, Moench 2015, JF 70(1)): planlı FOMC açıklamasından önceki 24 saatte (önceki gün 14:00 NY →
  karar günü 14:00 NY) S&P 500 olağandışı pozitif getiri verir. `gun`: karar günü 16:00 NY kapanışına kadar tutar.
- `ay_donumu_saat` (Lakonishok, Smidt 1988, RFS; McConnell, Xu 2008, FAJ): hisse getirisi ayın son iş günü ile yeni
  ayın ilk birkaç iş gününde yoğunlaşır. Ayın son iş gününden önceki günün 16:00 NY kapanışından yeni ayın `sonra`.
  iş gününün 16:00 NY kapanışına kadar.
- `gece_kaymasi` (Cliff, Cooper, Gulen 2008, JEF; Lou, Polk, Skouras 2019, JFE): endeks getirisi nakit seans dışında
  (kapanıştan açılışa) birikir. 16:00 NY → ertesi iş günü 09:00 NY.

FOMC günleri `doviz_akis.fomc_ayarla` ile verilir (turnuva koşudan önce bir kez; önceden ilan edilen takvim).
Tatiller yok sayılır (iş günü = hafta içi).
"""
from __future__ import annotations

import numpy as np

from tradebot.cekirdek import doviz_akis as da
from tradebot.cekirdek.aileler import abd_yaz_saati
from tradebot.cekirdek.temel import Barlar

SAAT_MS = 3_600_000
GUN_MS = 86_400_000


def _bar_ms(t: np.ndarray) -> int:
    return int(np.min(np.diff(t))) if len(t) > 1 else SAAT_MS


def ny_ms(gun: np.ndarray, saat: int) -> np.ndarray:
    """New York yerel `saat`:00'ın UTC ms'si (gün datetime64[D])."""
    g = np.asarray(gun, dtype="datetime64[D]")
    return g.astype(np.int64) * GUN_MS + (saat + np.where(abd_yaz_saati(g), 4, 5)) * SAAT_MS


def _is_gunu_kaydir(gun: np.ndarray, adim: int) -> np.ndarray:
    """Hafta içi günlerle `adim` gün ileri (+) ya da geri (−)."""
    d = np.asarray(gun, dtype="datetime64[D]").copy()
    birim = np.timedelta64(1 if adim > 0 else -1, "D")
    for _ in range(abs(adim)):
        d = d + birim
        while True:
            hs = (d.astype(np.int64) + 3) % 7 >= 5
            if not hs.any():
                break
            d = np.where(hs, d + birim, d)
    return d


def _tutulan(b: Barlar) -> np.ndarray:
    return np.asarray(b.t, dtype=np.int64) + _bar_ms(b.t)


def fomc_oncesi(b: Barlar, pencere: str = "on") -> np.ndarray:
    """Planlı FOMC karar gününden önceki iş günü 14:00 NY → karar günü 14:00 NY (`on`) ya da 16:00 NY (`gun`) uzun."""
    if pencere not in ("on", "gun"):
        raise ValueError(f"bilinmeyen pencere: {pencere}")
    tut = _tutulan(b)
    f = da._FOMC
    if len(f) == 0:
        return np.zeros(len(tut))
    gun = (f // GUN_MS).astype("datetime64[D]")
    bas = ny_ms(_is_gunu_kaydir(gun, -1), 14)
    bit = ny_ms(gun, 14 if pencere == "on" else 16)
    i = np.searchsorted(bit, tut, side="right")                  # sonu tut'tan sonra olan ilk olay
    ok = i < len(bit)
    j = np.minimum(i, len(bit) - 1)
    return (ok & (bas[j] <= tut) & (tut < bit[j])).astype(float)


def ay_donumu_saat(b: Barlar, sonra: int = 3) -> np.ndarray:
    """Ayın son iş gününden önceki iş günü 16:00 NY → yeni ayın `sonra`. iş günü 16:00 NY uzun."""
    tut = _tutulan(b)
    if len(tut) == 0:
        return np.zeros(0)
    g0 = (tut[0] // GUN_MS).astype("datetime64[D]").astype("datetime64[M]") - np.timedelta64(1, "M")
    g1 = (tut[-1] // GUN_MS).astype("datetime64[D]").astype("datetime64[M]") + np.timedelta64(1, "M")
    aylar = np.arange(g0, g1 + np.timedelta64(1, "M"))
    ay_sonu = (aylar + np.timedelta64(1, "M")).astype("datetime64[D]") - np.timedelta64(1, "D")
    son_is = _is_gunu_kaydir(ay_sonu + np.timedelta64(1, "D"), -1)       # ayın son iş günü
    bas = ny_ms(_is_gunu_kaydir(son_is, -1), 16)
    bit = ny_ms(_is_gunu_kaydir(son_is, sonra), 16)
    i = np.searchsorted(bit, tut, side="right")
    ok = i < len(bit)
    j = np.minimum(i, len(bit) - 1)
    return (ok & (bas[j] <= tut) & (tut < bit[j])).astype(float)


def gece_kaymasi(b: Barlar) -> np.ndarray:
    """16:00 NY kapanışından sonraki iş günü 09:00 NY'ye kadar uzun (hafta sonu dahil tutulur)."""
    tut = _tutulan(b)
    if len(tut) == 0:
        return np.zeros(0)
    gun = (tut // GUN_MS).astype("datetime64[D]")
    # tut'un ait olabileceği iki pencere: dünkü (ya da son iş günü) kapanıştan bugünkü açılışa; bugünkü kapanıştan sonra
    kapanis_bugun = ny_ms(gun, 16)
    acilis_bugun = ny_ms(gun, 9)
    hs = (gun.astype(np.int64) + 3) % 7 >= 5
    onceki_is = _is_gunu_kaydir(gun, -1)
    sonraki_is = _is_gunu_kaydir(gun, 1)
    # 1) bugün iş günü ve kapanıştan sonra: sonraki iş gününün açılışına kadar (aynı UTC günü içinde kalan kısım)
    a = ~hs & (tut >= kapanis_bugun) & (tut < ny_ms(sonraki_is, 9))
    # 2) bugün iş günü ve açılıştan önce: önceki iş gününün kapanışından beri
    b_ = ~hs & (tut < acilis_bugun) & (tut >= ny_ms(onceki_is, 16))
    # 3) hafta sonu: Cuma kapanışından Pazartesi açılışına
    c = hs & (tut >= ny_ms(onceki_is, 16)) & (tut < ny_ms(sonraki_is, 9))
    return (a | b_ | c).astype(float)
