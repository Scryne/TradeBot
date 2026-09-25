from datetime import UTC, datetime

import numpy as np
import pytest

from tradebot.arastirma import metrik
from tradebot.arastirma.backtest import calistir
from tradebot.arastirma.maliyet import MaliyetModeli, model

SIFIR = MaliyetModeli("sifir", 0, 0, 0)
GUN = 86_400_000


def _t(n, adim=GUN):
    return np.arange(n, dtype=np.int64) * adim + int(datetime(2024, 1, 1, tzinfo=UTC).timestamp() * 1000)


def test_sinyal_sonraki_bar_uygulanir_elle_hesap():
    fiyat = np.array([100.0, 110.0, 121.0, 121.0, 60.5])
    sinyal = np.array([1.0, 1.0, 0.0, 0.0, 0.0])  # t=0 kapanışında al, t=2 kapanışında sat
    s = calistir(_t(5), fiyat, sinyal, SIFIR)
    # bar 0: pozisyon 0 (karar kapanışta); bar 1: 110→121 (+%10); bar 2: 121→121 (0, karar verildi ama pozisyon hâlâ 1)
    # bar 3: pozisyon 0 → %50 düşüş hiç yaşanmaz
    assert s.pozisyon.tolist() == [0.0, 1.0, 1.0, 0.0]
    np.testing.assert_allclose(s.brut, [0.0, 0.1, 0.0, 0.0])
    assert s.ozkaynak[-1] == pytest.approx(1.1)


def test_maliyet_giris_ve_cikis():
    fiyat = np.array([100.0, 100.0, 100.0, 100.0, 100.0])
    mm = MaliyetModeli("m", ucret_bps=10, yari_spread_bps=1, kayma_bps=2)  # taraf 13 bps
    s = calistir(_t(5), fiyat, np.array([1.0, 1.0, 0.0, 0.0, 0.0]), mm)
    np.testing.assert_allclose(s.maliyet, [0.0, 0.0013, 0.0, 0.0013], atol=1e-12)
    assert s.islem_sayisi == 2 and s.ozkaynak[-1] == pytest.approx((1 - 0.0013) ** 2)


def test_kayma_devri_sabit_agirlikta_yeniden_dengeleme():
    # %50 ağırlık, fiyat iki katına çıkınca ağırlık 2/3'e kayar; hedefe dönmek 1/6 devir
    fiyat = np.array([100.0, 100.0, 200.0, 200.0])
    s = calistir(_t(4), fiyat, np.array([0.5, 0.5, 0.5, 0.5]), SIFIR)
    np.testing.assert_allclose(s.devir, [0.0, 0.5, 2 / 3 - 0.5], atol=1e-12)


def test_finansman_yalniz_cfd():
    fiyat = np.full(366, 100.0)
    sinyal = np.ones(366)
    cfd = calistir(_t(366), fiyat, sinyal, MaliyetModeli("cfd", 0, 0, 0, finansman_yillik=0.06))
    spot = calistir(_t(366), fiyat, sinyal, SIFIR)
    assert spot.maliyet.sum() == 0
    assert cfd.maliyet.sum() == pytest.approx(0.06 * 364 / 365.25, rel=1e-9)  # bar 1..364 pozisyonda


def test_spread_veriden():
    mm = MaliyetModeli("fx", 0, 9.0, 0, spread_veriden=True)
    s = calistir(_t(4), np.full(4, 1.0), np.array([1.0, 1.0, 1.0, 1.0]), mm, yari_spread_bps=np.array([0.3, 0.4, 9.9, 9.9]))
    assert s.maliyet[1] == pytest.approx(0.4 / 1e4)  # bar 1'deki giriş: bar 1'in spread'i


def test_metrik_haftalik_ve_kapilar():
    n = 7 * 60
    fiyat = 100 * np.cumprod(np.r_[1.0, np.full(n - 1, 1.001)])
    s = calistir(_t(n), fiyat, np.ones(n), SIFIR)
    m = metrik.hesapla(s)
    assert m.hafta in (60, 61) and m.en_kotu_dusus == 0.0 and m.karli_hafta_orani == 1.0
    assert m.puan == pytest.approx(7 * np.log(1.001), rel=0.02)
    assert not m.kapilar_gecti  # tek işlem: asgari işlem kapısı


def test_en_kotu_hafta_kapisi():
    fiyat = np.r_[np.full(10, 100.0), np.full(10, 80.0)]  # tek seferde %20 düşüş
    s = calistir(_t(20), fiyat, np.ones(20), SIFIR)
    m = metrik.hesapla(s)
    assert m.en_kotu_hafta <= -0.19 and m.en_kotu_dusus <= -0.19


def test_model_secimi():
    assert model("BINANCE", "kripto").ad == "binance_spot"
    assert model("DUKASCOPY", "endeks").finansman_yillik == 0.06
    assert model("BIST", "hisse").ucret_vergisi == 0.05
    with pytest.raises(KeyError):
        model("YOK", "x")
