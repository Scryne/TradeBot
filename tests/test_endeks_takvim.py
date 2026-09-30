"""Dalga 11: ABD hisse endeksi olay ve takvim primleri (cekirdek/endeks_takvim.py)."""
from datetime import UTC, datetime

import numpy as np
import pytest

from tradebot.cekirdek import Barlar, StratejiTanimi, nedensellik_testi
from tradebot.cekirdek import doviz_akis as da
from tradebot.cekirdek import endeks_takvim as et

SAAT = 3_600_000


def ms(s: str) -> int:
    return int(datetime.fromisoformat(s).replace(tzinfo=UTC).timestamp() * 1000)


def saatlik(bas: str, gun: int, tohum: int = 0) -> Barlar:
    t = ms(bas) + np.arange(gun * 24, dtype=np.int64) * SAAT
    rng = np.random.default_rng(tohum)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, len(t))))
    o = np.r_[c[0], c[:-1]]
    return Barlar(t, o, np.maximum(o, c), np.minimum(o, c), c, np.ones(len(t)))


@pytest.fixture(autouse=True)
def _fomc():
    da.fomc_ayarla([ms("2024-01-31"), ms("2024-03-20"), ms("2024-05-01")])
    yield
    da.fomc_ayarla([])


def tutulan(b: Barlar, s: np.ndarray) -> np.ndarray:
    return b.t[np.flatnonzero(s)] + SAAT


@pytest.mark.parametrize("fonk,param", [(et.fomc_oncesi, {"pencere": "on"}), (et.fomc_oncesi, {"pencere": "gun"}),
                                        (et.ay_donumu_saat, {"sonra": 3}), (et.gece_kaymasi, {})])
def test_nedensel(fonk, param):
    b = saatlik("2024-01-02", 150)
    nedensellik_testi(StratejiTanimi("x", "y", fonk, param), b, deneme=10)
    assert fonk(b, **param).sum() > 0


def test_fomc_oncesi_penceresi():
    b = saatlik("2024-01-25", 60)
    t = tutulan(b, et.fomc_oncesi(b, "on"))
    # Ocak (kış, EST): 30 Ocak 19:00 UTC → 31 Ocak 19:00 UTC
    ocak = t[t < ms("2024-02-15")]
    assert ocak[0] == ms("2024-01-30T19:00") and ocak[-1] == ms("2024-01-31T18:00") and len(ocak) == 24
    # Mart 20 (yaz saati başladı: 10 Mart): 19 Mart 18:00 UTC → 20 Mart 18:00 UTC
    mart = t[(t > ms("2024-03-01")) & (t < ms("2024-04-01"))]
    assert mart[0] == ms("2024-03-19T18:00") and mart[-1] == ms("2024-03-20T17:00")
    t = tutulan(b, et.fomc_oncesi(b, "gun"))
    assert t[t < ms("2024-02-15")][-1] == ms("2024-01-31T20:00")      # 16:00 EST = 21:00 UTC'ye kadar


def test_fomc_pazartesi_oncesi_cuma():
    da.fomc_ayarla([ms("2024-04-29")])  # Pazartesi (kurgu): önceki iş günü Cuma
    b = saatlik("2024-04-20", 12)
    t = tutulan(b, et.fomc_oncesi(b, "on"))
    assert t[0] == ms("2024-04-26T18:00") and t[-1] == ms("2024-04-29T17:00")


def test_ay_donumu_saat():
    b = saatlik("2024-01-20", 20)
    t = tutulan(b, et.ay_donumu_saat(b, sonra=3))
    # Ocak 2024 son iş günü 31 Çarşamba → başlangıç 30 Ocak 16:00 EST = 21:00 UTC; Şubat 3. iş günü 5 Şubat Pazartesi
    assert t[0] == ms("2024-01-30T21:00") and t[-1] == ms("2024-02-05T20:00")
    t = tutulan(b, et.ay_donumu_saat(b, sonra=1))
    assert t[-1] == ms("2024-02-01T20:00")


def test_gece_kaymasi():
    b = saatlik("2024-01-01", 14)  # 1 Ocak Pazartesi (tatil yok sayılır)
    s = et.gece_kaymasi(b)
    tut = b.t + SAAT
    acik = lambda x: bool(s[np.flatnonzero(tut == ms(x))[0]])  # noqa: E731
    assert acik("2024-01-02T21:00") and acik("2024-01-03T13:00") and not acik("2024-01-03T14:00")
    assert not acik("2024-01-03T20:00") and acik("2024-01-03T21:00")
    assert acik("2024-01-06T12:00") and acik("2024-01-08T13:00") and not acik("2024-01-08T15:00")  # hafta sonu
    # yaz saati: 16:00 EDT = 20:00 UTC
    b = saatlik("2024-06-03", 3)
    s = et.gece_kaymasi(b)
    tut = b.t + SAAT
    assert s[np.flatnonzero(tut == ms("2024-06-03T20:00"))[0]] == 1
    assert s[np.flatnonzero(tut == ms("2024-06-03T19:00"))[0]] == 0
    assert s[np.flatnonzero(tut == ms("2024-06-04T12:00"))[0]] == 1
    assert s[np.flatnonzero(tut == ms("2024-06-04T13:00"))[0]] == 0
