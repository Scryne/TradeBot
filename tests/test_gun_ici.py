"""Dalga 20 gün içi ivme çekirdeği: NY saatleri (yaz/kış), işaret, tutma penceresi, nedensellik."""
from datetime import UTC, datetime

import numpy as np

from tradebot.cekirdek import Barlar, StratejiTanimi, nedensellik_testi
from tradebot.cekirdek.gun_ici import gun_ici_ivme, ny_saat

SAAT = 3_600_000


def _ms(s: str) -> int:
    return int(datetime.fromisoformat(s).replace(tzinfo=UTC).timestamp() * 1000)


def _barlar(bas: str, gun: int, tohum: int = 0) -> Barlar:
    t = _ms(bas) + np.arange(gun * 24, dtype=np.int64) * SAAT
    rng = np.random.default_rng(tohum)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.002, len(t))))
    return Barlar(t, c, c * 1.001, c * 0.999, c, np.ones(len(t)))


def test_ny_saat_yaz_ve_kis():
    g, s = ny_saat(np.array([_ms("2026-07-01T20:00:00"), _ms("2026-01-15T21:00:00"), _ms("2026-07-02T02:00:00")]))
    assert list(s) == [16.0, 16.0, 22.0]
    assert str(g[2]) == "2026-07-01"                      # UTC 02:00 → NY önceki gün 22:00


def test_pozisyon_yalniz_son_saatte_ve_r1_isaretinde():
    b = _barlar("2026-07-06", 5)                           # Pazartesi, yaz saati
    for tutma, kisa in ((1, False), (2, True)):
        s = gun_ici_ivme(b, tutma=tutma, kisa=kisa)
        gun, saat = ny_saat(b.t + SAAT)
        assert set(saat[s != 0]) <= set(range(16 - tutma, 16))
        for d in np.unique(gun[s != 0]):
            i10 = np.flatnonzero((gun == d) & (saat == 10.0))[0]
            once = np.flatnonzero((saat == 16.0) & (b.t + SAAT <= b.t[i10]))
            r1 = b.close[i10] / b.close[once[-1]] - 1
            isaret = np.sign(s[(gun == d) & (s != 0)])
            assert (isaret == np.sign(r1)).all()
        if not kisa:
            assert (s >= 0).all()


def test_gun_ici_ivme_nedensel():
    b = _barlar("2026-01-05", 30, tohum=3)
    nedensellik_testi(StratejiTanimi("gi", "gun_ici_ivme", gun_ici_ivme, {"tutma": 2, "kisa": True},
                                     yon="long_short"), b)
