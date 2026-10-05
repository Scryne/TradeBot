"""Dalga 15 sapma + stokastik RSI: nedensellik, giriş sırası (takip → kesişim → EMA), %2 stop ve kâr al."""
import numpy as np

from tradebot.cekirdek import StratejiTanimi, nedensellik_testi
from tradebot.cekirdek import sapma_stoch as ss
from tradebot.cekirdek.temel import Barlar


def _b(c):
    t = np.arange(len(c), dtype=np.int64) * 14_400_000
    return Barlar(t=t, open=c, high=c, low=c, close=c, volume=np.ones(len(c)))


def test_nedensel_ve_yalniz_alis():
    rng = np.random.default_rng(3)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 1500)))
    for g in (0, 1):
        out = ss.sapma_stoch(_b(c), z_esik=-1.5, guvenli=g)
        assert set(np.unique(out)) <= {0.0, 1.0} and out.sum() > 0
        tanim = StratejiTanimi("sapma_stoch", "sapma_stoch", ss.sapma_stoch, {"z_esik": -1.5, "guvenli": g})
        nedensellik_testi(tanim, _b(c), deneme=3)


def test_stop_ve_hedef():
    rng = np.random.default_rng(5)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 3000)))
    out = ss.sapma_stoch(_b(c), z_esik=-1.5, guvenli=0, tp=0.05, sl=0.02)
    i = 1
    while i < len(c):
        if out[i] == 1 and out[i - 1] == 0:           # giriş barı
            g = c[i]
            j = i + 1
            while j < len(c) and out[j] == 1:
                assert -0.02 < c[j] / g - 1 < 0.05     # pozisyon sürerken eşikler aşılmamış
                j += 1
            if j < len(c):
                r = c[j] / g - 1
                assert r >= 0.05 or r <= -0.02          # çıkış barında eşiklerden biri aşıldı
            i = j
        i += 1
