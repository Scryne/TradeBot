"""Dalga 3 vadeli serileri: CME takvimi, geçiş ayarı, fazla getiri vekili, faizin PIT kullanımı."""
from datetime import UTC, date, datetime

import numpy as np
import polars as pl
import pytest

from tradebot.veri import faiz as fz
from tradebot.veri import vadeli as vd

GUN = 86_400_000


def ms(y, a, g):
    return int(datetime(y, a, g, tzinfo=UTC).timestamp() * 1000)


def test_ucuncu_cuma():
    assert vd.ucuncu_cuma(2024, 3) == date(2024, 3, 15)
    assert vd.ucuncu_cuma(2024, 9) == date(2024, 9, 20)
    assert vd.ucuncu_cuma(2026, 12) == date(2026, 12, 18)
    assert vd.cme_vadeleri(ms(2024, 1, 1), ms(2025, 1, 1)) == [ms(2024, 3, 15), ms(2024, 6, 21), ms(2024, 9, 20),
                                                              ms(2024, 12, 20)]


def _is_gunleri(bas, n):
    t, g = [], bas
    while len(t) < n:
        if datetime.fromtimestamp(g / 1000, UTC).weekday() < 5:
            t.append(g)
        g += GUN
    return np.array(t)


def _bar(t, c):
    return pl.DataFrame({"acilis_ms": t, "open": c, "high": c * 1.001, "low": c * 0.999, "close": c,
                         "volume": np.zeros(len(t))})


def test_pencere_ayari_gecis_sicramasini_tamamen_cikarir():
    """Vadeli = spot × (1 + baz); baz her vade geçişinde iki güne yayılan +%1 sıçrar, arada erir. Ayarlı seri spotla
    aynı yolu izlemeli (baz erimesi hariç), ham seri geçişlerde fazladan kazanır."""
    t = _is_gunleri(ms(2024, 1, 2), 260)
    rng = np.random.default_rng(1)
    spot = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(t))))
    vadeler = vd.cme_vadeleri(int(t[0]), int(t[-1]))
    baz = np.zeros(len(t))
    for i in range(len(t)):
        once = [e for e in vadeler if e <= t[i] - 0]
        son = max(once) if once else None
        # geçiş vade gününde ve ertesi gün yarım yarım (NCM'de görülen iki güne yayılma)
        kac = 0.0 if son is None else (0.005 if t[i] == son else 0.01)
        gecen = 0 if son is None else (t[i] - son) / GUN
        baz[i] = kac * max(0.0, 1 - gecen / 91)
    vad = spot * (1 + baz)
    seri, r = vd.pencere_ayari(_bar(t, vad), _bar(t, spot), vadeler)
    ayarli = seri["close"].to_numpy()
    assert r["gecis"] == len(vadeler) == 4
    assert r["sicrama_medyan"] == pytest.approx(0.0095, abs=0.003)
    # pencere günlerinde ayarlı getiri = spot getirisi, dışında = ham vadeli getirisi (baz erimesi seride kalır)
    ra, rv, rs = ayarli[1:] / ayarli[:-1], vad[1:] / vad[:-1], spot[1:] / spot[:-1]
    spot_gibi = np.isclose(ra, rs, rtol=0, atol=1e-12) & ~np.isclose(rv, rs, rtol=0, atol=1e-12)
    assert spot_gibi.sum() >= 4 * 2                  # her geçişin sıçrama günleri
    assert np.all(np.isclose(ra, rv, atol=1e-12) | np.isclose(ra, rs, atol=1e-12))
    assert (np.isclose(ra, rs, atol=1e-12) & ~np.isclose(ra, rv, atol=1e-12)).sum() <= 4 * 6
    # ayarlı seri spotun gerisinde kalır: vadeli fazla getirisi = spot − taşıma (4 çeyrek × ~%1)
    geri = (ayarli[-1] / ayarli[0]) / (spot[-1] / spot[0]) - 1
    assert -0.045 < geri < -0.015
    assert ayarli[-1] == pytest.approx(vad[-1])      # son fiyat gerçek vadeli fiyatı


def test_fazla_getiri_tasima_ekler():
    t = _is_gunleri(ms(2024, 1, 2), 261)
    spot = np.full(len(t), 1.10)
    seri, r = vd.fazla_getiri(_bar(t, spot), np.full(len(t), 0.02), np.full(len(t), 0.05))
    c = seri["close"].to_numpy()
    yil = (t[-1] - t[0]) / GUN / 365
    assert c[-1] / c[0] == pytest.approx(np.exp(-0.03 * yil), rel=1e-9)   # spot sabit: yalnız −%3 taşıma
    assert c[-1] == pytest.approx(1.10)


def test_faiz_gecikmeli_kullanilir():
    aylik = {(2024, 1): 0.01, (2024, 2): 0.02, (2024, 3): 0.03, (2024, 4): 0.04}
    g = np.array([ms(2024, 3, 10), ms(2024, 4, 1), ms(2024, 6, 30), ms(2023, 12, 5)])
    r = fz.gunluk(aylik, g, gecikme_ay=2)
    assert r[0] == 0.01 and r[1] == 0.02 and r[2] == 0.04 and np.isnan(r[3])


def test_oecd_csv_cozulur():
    csv = ("STRUCTURE,REF_AREA,MEASURE,TIME_PERIOD,OBS_VALUE\n"
           "DATAFLOW,USA,IR3TIB,2024-01,5.3\nDATAFLOW,JPN,IR3TIB,2024-01,0.07\nDATAFLOW,JPN,IR3TIB,2024-02,\n")
    r = fz.coz(csv.encode())
    assert r.keys() == {"USA", "JPN"} and r["USA"] == {(2024, 1): pytest.approx(0.053)}
    assert r["JPN"] == {(2024, 1): pytest.approx(0.0007)}


class _Depo:
    def __init__(self, seriler):
        self.seriler = seriler

    def oku(self, kimlik, zd):
        return self.seriler[kimlik]


def test_tasima_farki_gomulu_faizi_geri_verir_ve_para_yonu():
    t = _is_gunleri(ms(2024, 1, 1), 300)
    rng = np.random.default_rng(1)
    c = 150 * np.exp(np.cumsum(rng.normal(0, 0.006, len(t))))
    rt = np.where(t < ms(2024, 6, 1), 0.05, 0.045)      # USD
    rk = np.full(len(t), -0.001)                        # JPY
    seri, _ = vd.fazla_getiri(_bar(t, c), rt, rk)
    depo = _Depo({"VADELI:USDJPY": seri, "DUKASCOPY:USDJPY": _bar(t, c)})
    izgara = np.r_[t[0] - GUN, t, t[-1] + 3 * GUN]
    f = vd.tasima_farki(depo, "VADELI:USDJPY", izgara)
    assert np.isnan(f[0]) and np.isnan(f[1])            # ızgara başı ve ilk bar (fark tanımsız)
    np.testing.assert_allclose(f[2:-1], (rt - rk)[1:], atol=1e-9)
    assert f[-1] == f[-2]                               # son bardan sonra ileri doldurulur
    assert vd.para_yonu("VADELI:USDJPY") == -1.0 and vd.para_yonu("VADELI:EURUSD") == 1.0
    with pytest.raises(ValueError):
        vd.para_yonu("VADELI:XAU")
