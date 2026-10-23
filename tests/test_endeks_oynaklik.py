"""Dalga 23: QQQ oynaklık zamanlaması — ağırlık nedensel, finansman yalnız ödünç kısma, nakit yalnız boştaki kısma."""
import numpy as np
import pytest

from tradebot.arastirma import backtest as bt
from tradebot.arastirma import endeks_oynaklik as eo
from tradebot.arastirma.maliyet import YIL_MS, MaliyetModeli

GUN = 86_400_000
MM = MaliyetModeli("abd_etf", 1.0, 1.0, 1.0)


def _seri(n=400, tohum=1):
    g = np.random.default_rng(tohum)
    k = 100 * np.exp(np.cumsum(g.normal(0.0004, 0.015, n)))
    a = np.r_[k[0], k[:-1]] * (1 + g.normal(0, 0.002, n))
    return np.arange(n) * GUN + 1_000_000_000_000, a, k


def test_agirlik_nedensel_ve_tavanli():
    _, _, k = _seri()
    w = eo.agirlik(k, 0.20, 20, 2.0)
    bozuk = k.copy()
    bozuk[300:] *= np.linspace(1, 3, 100)          # gelecek değişir
    assert np.array_equal(w[:300], eo.agirlik(bozuk, 0.20, 20, 2.0)[:300])
    assert (w[:19] == 0).all() and w[19] > 0 and w.max() <= 2.0 and w.min() >= 0
    assert eo.agirlik(k, 0.20, 20, 1.0).max() <= 1.0


def test_tam_pozisyonda_motorla_ayni_bosta_nakit_kaldiracta_finansman():
    t, a, _ = _seri()
    nakit = np.full(len(t), 0.0002)
    borc = np.full(len(t), 0.05)
    s1 = eo.kos(t, a, np.ones(len(t)), MM, nakit, borc)
    m = bt.calistir(t, a, np.ones(len(t)), MM)
    # ilk bar pozisyonsuz (sinyal bir bar kayar): yalnız o bar nakit kazanır
    assert s1.net[1:] == pytest.approx(m.net[1:]) and s1.net[0] == pytest.approx(m.net[0] + 0.0002)
    s2 = eo.kos(t, a, np.full(len(t), 2.0), MM, nakit, borc)
    m2 = bt.calistir(t, a, np.full(len(t), 2.0), MM)
    fin = 0.05 * GUN / YIL_MS
    assert s2.net[5:] == pytest.approx(m2.net[5:] - fin)        # ödünç 1 birim (2 − 1), nakit yok
    s3 = eo.kos(t, a, np.full(len(t), 0.5), MM, nakit, borc)
    m3 = bt.calistir(t, a, np.full(len(t), 0.5), MM)
    assert s3.net[5:] == pytest.approx(m3.net[5:] + 0.5 * 0.0002)   # yarısı nakitte, finansman yok


def test_borc_ve_nakit_serisi():
    t = np.arange(5) * GUN
    assert eo.borc_serisi(t, None, 0.015, 0.07).tolist() == [0.07] * 5
    f = np.array([np.nan, 0.03, 0.03, np.nan, 0.04])
    assert eo.borc_serisi(t, f, 0.015, 0.07) == pytest.approx([0.07, 0.045, 0.045, 0.07, 0.055])
    r = eo.nakit_serisi(t, t[2:], np.array([100.0, 101.0, 102.01]))   # ilk iki gün nakit verisi yok → 0
    assert r == pytest.approx([0, 0, 0.01, 0.01, 0])


def test_ozet_acil_ve_yarilar():
    t, a, _ = _seri(600)
    s = eo.kos(t, a, np.ones(len(t)), MM, np.zeros(len(t)), np.zeros(len(t)))
    o = eo.ozet(s)
    assert o["gun"] == len(t) - 1 and o["en_kotu_dusus"] <= 0
    assert eo.ozet(s, bit_ms=int(t[300]))["gun"] == 300
