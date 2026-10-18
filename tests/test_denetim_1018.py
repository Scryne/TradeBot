"""2026-10-18 tam denetiminin regresyon testleri (araştırma motoru, dağıtıcı, karar, terfi)."""
import math

import numpy as np
import pytest

from tradebot.arastirma.backtest import calistir
from tradebot.arastirma.dogrulama import walk_forward
from tradebot.arastirma.maliyet import MaliyetModeli
from tradebot.canli import dagitici as dg
from tradebot.canli import terfi
from tradebot.risk.motor import Durum

GUN = 86_400_000
T0 = 1_767_571_200_000  # 2026-01-05 Pazartesi 00:00 UTC


class _SahteIzleyici:
    """t ≥ esik'ten sonra hep günlük fren."""

    def __init__(self, esik_ms: int) -> None:
        self.esik = esik_ms

    def guncelle(self, oz: float, t: int) -> Durum:
        return Durum.FREN_GUNLUK if t >= self.esik else Durum.NORMAL


def test_backtest_frende_ters_donmez():
    n = 8
    t = T0 + np.arange(n, dtype=np.int64) * GUN
    fiyat = np.full(n, 100.0)
    sinyal = np.array([1, 1, -1, -1, -1, -1, -1, -1], dtype=float)
    s = calistir(t, fiyat, sinyal, MaliyetModeli("0", 0, 0, 0), izleyici=_SahteIzleyici(T0 + 2 * GUN))
    assert (s.pozisyon >= 0).all()                     # fren varken −1'e geçilmez (önce +1'den 0'a iner)
    assert s.pozisyon[3] == 0.0


def test_backtest_kisa_pozisyon_odunc_maliyeti_oder():
    n = 366
    t = T0 + np.arange(n, dtype=np.int64) * GUN
    fiyat = np.full(n, 100.0)
    mm = MaliyetModeli("x", 0, 0, 0, finansman_yillik=0.0, aciga_satis_yillik=0.10)
    kisa = calistir(t, fiyat, -np.ones(n), mm)
    uzun = calistir(t, fiyat, np.ones(n), mm)
    assert uzun.maliyet.sum() == pytest.approx(0.0)
    assert kisa.maliyet.sum() == pytest.approx(0.10 * 364 / 365.25, rel=1e-3)


def test_backtest_nan_fiyat_hata():
    t = T0 + np.arange(5, dtype=np.int64) * GUN
    with pytest.raises(ValueError):
        calistir(t, np.array([1.0, 1.0, np.nan, 1.0, 1.0]), np.ones(5), MaliyetModeli("0", 0, 0, 0))


def test_walk_forward_gecis_maliyeti_yon_degisiminde_sifir_degil():
    n = 6 * 365
    t = T0 + np.arange(n, dtype=np.int64) * GUN
    net_a = np.r_[np.full(3 * 365, 0.001), np.full(3 * 365, -0.001)]
    kosular = {"a": {"net": net_a, "pozisyon": np.ones(n)}, "b": {"net": -net_a, "pozisyon": np.ones(n)}}
    yil = int(365.25 * GUN)
    r = walk_forward(t, kosular, yil, yil, lambda tt, x: float(x.sum()), taraf_maliyet=0.001)
    ilk = [s["secilen"] for s in r["secimler"]]
    assert len(set(ilk)) == 2
    # aynı brüt maruziyetli varyantlar arasında geçiş: eski kapanır + yeni açılır = 2 × taraf
    i = next(j for j in range(1, len(ilk)) if ilk[j] != ilk[j - 1])
    bas = r["secimler"][i]["oos_bas"]
    k = int(np.flatnonzero(r["t"] == bas)[0])
    secilen = kosular[ilk[i]]["net"]
    assert r["net"][k] == pytest.approx(secilen[np.flatnonzero(t == bas)[0]] - 0.002)


def test_dagitici_kademe_bir_ustu_reddedilir():
    with pytest.raises(ValueError):
        dg.DagiticiAyar(kademe=((28, 5.0),))


def test_terfi_sabit_sapma_takip_hatasidir():
    gunler = [T0 + i * GUN for i in range(80)]
    bt = {g: 0.001 for g in gunler}
    paper = {g: 0.001 - 0.005 for g in gunler}         # her gün 50 bps geride: std 0, RMS 50 bps
    r = terfi.degerlendir(paper, bt, [0.005] * 100, -0.05, 0.0, 80, 5.0, 5.0)
    te = r["olcutler"]["takip_hatasi"]
    assert te["deger"] == pytest.approx(0.005 * math.sqrt(dg.YIL_GUN))
    assert not te["gecti"]


def test_terfi_az_ortak_gun_gecemez():
    gunler = [T0 + i * GUN for i in range(80)]
    paper = {g: 0.001 for g in gunler}
    bt = {g: 0.001 for g in gunler[:2]}                # yalnız iki ortak gün
    r = terfi.degerlendir(paper, bt, [0.005] * 100, -0.05, 0.0, 80, 5.0, 5.0)
    assert r["olcutler"]["takip_hatasi"]["deger"] == float("inf")
