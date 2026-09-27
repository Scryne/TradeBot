"""Altın M15 aileleri: nedensellik (bozma testi) ve EA risk katmanları (yonet)."""
import numpy as np
import pytest

from tradebot.cekirdek import StratejiTanimi, altin, nedensellik_testi
from tradebot.cekirdek.temel import Barlar

DK15 = 15 * 60_000


def rastgele_barlar(n=3000, tohum=1, bas_ms=1_700_000_000_000 - 1_700_000_000_000 % 86_400_000):
    rng = np.random.default_rng(tohum)
    c = 2000 * np.exp(np.cumsum(rng.normal(0, 0.002, n)))
    o = np.concatenate([[c[0]], c[:-1]])
    h = np.maximum(o, c) * (1 + np.abs(rng.normal(0, 0.001, n)))
    lo = np.minimum(o, c) * (1 - np.abs(rng.normal(0, 0.001, n)))
    return Barlar(bas_ms + np.arange(n) * DK15, o, h, lo, c, np.ones(n))


def elle_barlar(kapanislar, bas_ms=0):
    c = np.asarray(kapanislar, dtype=float)
    return Barlar(bas_ms + np.arange(len(c)) * DK15, c, c + 0.5, c - 0.5, c, np.ones(len(c)))


@pytest.mark.parametrize("fonk,p", [
    (altin.seans_kirilim, {}), (altin.kanal_kirilim, {"n": 48}), (altin.trend_geri_cekilme, {}),
    (altin.bant_donus, {}), (altin.sikisma_kirilim, {"geriye": 200}), (altin.ea_birlesik, {}),
])
def test_nedensellik(fonk, p):
    b = rastgele_barlar()
    s = StratejiTanimi(fonk.__name__, "altin_m15", fonk, p, yon="long_short")
    nedensellik_testi(s, b, deneme=4)
    assert s.sinyal(b).min() >= -1 and s.sinyal(b).max() <= 1


def _yonet(c, giris, **kw):
    altin.haber_ayarla([])
    b = elle_barlar(c)
    kw.setdefault("atr_n", 2)
    return altin.yonet(b, np.asarray(giris, dtype=float), **kw), b


def test_yonet_stop_hedef_ve_sure():
    # ATR(2) = 1 (h−l sabit 1, fiyat sabitken) → sl_atr 1 → risk 1; hedef rr 2 → +2
    c = [100, 100, 100, 100, 99.5, 99, 100, 100, 100, 103, 100, 100, 100, 100, 100]
    g = [0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 1, 0, 0]
    out, _ = _yonet(c, g, sl_atr=1.0, rr=2.0, azami_bar=2)
    assert out[3] == 1 and out[4] == 1 and out[5] == 0            # 99 = −1R → stop
    assert out[8] == 1 and out[9] == 0                            # 103 ≥ +2R (ATR ~1,2) → hedef
    assert list(out[12:15]) == [1, 1, 0]                          # azami_bar=2 → süre dolunca çık


def test_yonet_yeni_sinyal_gerekir_ve_gun_kilidi():
    c = [100] * 3 + [100, 97] * 4 + [100] * 3
    g = [0, 0, 0] + [1, 1] * 4 + [0] * 3                          # sinyal sürekli 1: yalnız ilk geçişte giriş
    out, _ = _yonet(c, g, sl_atr=1.0)
    assert out[3] == 1 and out[4] == 0 and out[5:].sum() == 0
    g2 = [0, 0, 0] + [1, 0] * 4 + [0] * 3                         # her kayıptan sonra yeni sinyal
    out2, _ = _yonet(c, g2, sl_atr=0.5, ardisik=3, gunluk_r=100)  # ATR büyüse de −3 her seferinde stop
    assert [out2[i] for i in (3, 5, 7, 9)] == [1, 1, 1, 0]       # 3 ardışık kayıp → gün kilitli
    out3, _ = _yonet(c, g2, sl_atr=0.5, ardisik=3, gunluk_r=3)
    assert [out3[i] for i in (3, 5)] == [1, 0]                   # tek boşluk kaybı −6R ≥ günlük −3R → kilit


def test_yonet_haber_penceresi():
    b = elle_barlar([100] * 10, bas_ms=0)
    altin.haber_ayarla([5 * DK15])                                 # bar 3 kapanışından 15 dk, bar 9'dan 75 dk uzak
    g = np.array([0, 0, 0, 1, 0, 0, 0, 0, 0, 1], dtype=float)
    assert altin.yonet(b, g, haber_dk=60, atr_n=2)[3] == 0        # pencere içinde giriş yok
    assert altin.yonet(b, g, haber_dk=0, atr_n=2)[3] == 1
    assert altin.yonet(b, g, haber_dk=60, atr_n=2)[9] == 1        # pencere dışında giriş var
    altin.haber_ayarla([])


def test_seans_kirilim_gunde_yon_basina_bir():
    # UTC 00–07 aralığı (28 bar), sonra kırılım
    c = [100.0] * 28 + [101.0, 100.0, 101.2, 99.0, 98.0]
    b = elle_barlar(c, bas_ms=0)
    s = altin.seans_kirilim_giris(b)
    assert list(s[28:]) == [1, 0, 0, -1, 0]
