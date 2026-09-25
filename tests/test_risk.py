from datetime import UTC, datetime

import numpy as np
import pytest

from tradebot.arastirma.backtest import calistir
from tradebot.arastirma.maliyet import MaliyetModeli
from tradebot.cekirdek import Barlar, StratejiTanimi, nedensellik_testi
from tradebot.cekirdek.boyut import (
    KALDIRAC_TAVANI,
    KaldiracHatasi,
    kaldirac_dogrula,
    kelly,
    oynaklik_hedefi,
    yarim_kelly_tavani,
)
from tradebot.risk.motor import Durum, EmirIstegi, Piyasa, Portfoy, PortfoyIzleyici, RiskAyar, RiskMotoru

GUN = 86_400_000
T0 = int(datetime(2026, 1, 5, tzinfo=UTC).timestamp() * 1000)  # Pazartesi 00:00 UTC


# --- kaldıraç tavanı (değişmez kural 6) ---
@pytest.mark.parametrize("x", [0.0, 1.0, 2.5, 3.0])
def test_kaldirac_izinli(x):
    assert kaldirac_dogrula(x) == x


@pytest.mark.parametrize("x,mesaj", [(3.01, "tavanını"), (4.99, "tavanını"), (5.0, "yasak"), (20.0, "yasak"),
                                     (-1.0, "geçersiz"), (float("nan"), "geçersiz"), (float("inf"), "geçersiz")])
def test_kaldirac_yasak_ve_tavan(x, mesaj):
    with pytest.raises(KaldiracHatasi, match=mesaj):
        kaldirac_dogrula(x)


def test_risk_ayari_tavani_asamaz():
    with pytest.raises(KaldiracHatasi):
        RiskAyar(kaldirac=10.0)
    with pytest.raises(KaldiracHatasi):
        oynaklik_hedefi(np.ones(10), np.linspace(1, 2, 10), 0.4, 365, azami=5.0)


# --- oynaklık hedefi ve Kelly ---
def test_oynaklik_hedefi_olcek_ve_kirpma():
    rng = np.random.default_rng(0)
    gunluk_sigma = 0.02
    close = 100 * np.exp(np.cumsum(rng.normal(0, gunluk_sigma, 2000)))
    w = oynaklik_hedefi(np.ones(2000), close, hedef_yillik=0.20, bar_yil=365, pencere=60, azami=3.0)
    beklenen = 0.20 / (gunluk_sigma * np.sqrt(365))  # ≈ 0,52
    assert np.nanmedian(w[100:]) == pytest.approx(beklenen, rel=0.1)
    assert w[:59].max() == 0.0  # ısınma
    sakin = 100 * np.exp(np.cumsum(rng.normal(0, 0.0005, 500)))
    assert oynaklik_hedefi(np.ones(500), sakin, 0.20, 365, azami=3.0)[100:].max() == pytest.approx(3.0)  # tavana kırpılır


def test_oynaklik_hedefi_gelecegi_gormez():
    rng = np.random.default_rng(1)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, 800)))
    b = Barlar(np.arange(800, dtype=np.int64) * GUN, c, c * 1.01, c * 0.99, c, np.ones(800))
    tanim = StratejiTanimi("vh", "test", lambda b: oynaklik_hedefi(np.ones(len(b)), b.close, 0.3, 365, azami=2.0))
    nedensellik_testi(tanim, b)


def test_kelly():
    assert kelly(0.01, 0.0004) == pytest.approx(25.0)
    rng = np.random.default_rng(2)
    haftalik = rng.normal(0.004, 0.04, 400)  # μ/σ² ≈ 2,5 → yarım ≈ 1,25
    assert yarim_kelly_tavani(haftalik) == pytest.approx(0.5 * haftalik.mean() / haftalik.var(ddof=1))
    assert yarim_kelly_tavani(rng.normal(0.05, 0.05, 400)) == KALDIRAC_TAVANI  # çok yüksek Kelly de 3'te kalır
    assert yarim_kelly_tavani(rng.normal(-0.01, 0.04, 400)) == 0.0             # negatif beklenti → 0
    assert yarim_kelly_tavani(haftalik[:10]) == 1.0                            # az gözlem → temkinli 1x


# --- risk motoru ---
def _pf(**k):
    return Portfoy(ozkaynak=100_000.0, pozisyonlar=k.pop("poz", {}), fiyatlar=k.pop("fiyat", {"BINANCE:BTCUSDT": 50_000.0}),
                   siniflar=k.pop("sinif", {"BINANCE:BTCUSDT": "kripto"}), **k)


def _e(miktar, fiyat=50_000.0, emir="e1", zaman=T0 + 3_600_000):
    return EmirIstegi("BINANCE:BTCUSDT", "kripto", miktar, fiyat, "kol1", zaman, emir)


PIY = Piyasa(son_fiyat=50_000.0, son_bar_ms=T0 + 3_600_000, bar_ms=3_600_000, acik=True, adim_miktar=0.00001)


def test_onay_ve_tavana_kucultme():
    m = RiskMotoru(RiskAyar(enstruman_tavani=0.5, azami_emir_orani=1.0))
    k = m.onayla(_e(2.0), PIY, _pf())  # 100 bin$ istek, enstrüman tavanı %50 → 1 BTC
    assert k.onay and k.miktar == pytest.approx(1.0) and "küçültüldü" in k.gerekceler[0]


def test_kaldirac_tavani_portfoyde():
    m = RiskMotoru(RiskAyar(kaldirac=1.0, enstruman_tavani=1.0, sinif_tavani=3.0, azami_emir_orani=1.0))
    pf = _pf(poz={"X": 1.6}, fiyat={"BINANCE:BTCUSDT": 50_000.0, "X": 50_000.0}, sinif={"X": "fx"})  # 80 bin$ açık
    k = m.onayla(_e(1.0), PIY, pf)
    assert k.onay and k.miktar == pytest.approx(0.4)  # 100 bin × 1x − 80 bin = 20 bin$


@pytest.mark.parametrize("durum", [Durum.FREN_GUNLUK, Durum.FREN_HAFTALIK, Durum.ACIL_DURDURMA])
def test_frende_risk_artmaz_azaltan_gecer(durum):
    m = RiskMotoru()
    pf = _pf(poz={"BINANCE:BTCUSDT": 0.5}, durum=durum)
    artiran = m.onayla(_e(0.1, emir="a"), PIY, pf)
    azaltan = m.onayla(_e(-0.5, emir="b"), PIY, pf)
    assert not artiran.onay and durum.value in artiran.gerekceler[0]
    assert azaltan.onay and azaltan.risk_azaltan and azaltan.miktar == -0.5


def test_veto_ve_kol_durdurma_yalniz_artirmayi_engeller():
    m = RiskMotoru()
    pf = _pf(poz={"BINANCE:BTCUSDT": 0.2}, veto={"BINANCE:BTCUSDT"}, durdurulan_kollar={"kol1"})
    k = m.onayla(_e(0.1, emir="a"), PIY, pf)
    assert not k.onay and any("veto" in g for g in k.gerekceler) and any("kol" in g for g in k.gerekceler)
    assert m.onayla(_e(-0.2, emir="b"), PIY, pf).onay


def test_temel_akil_kontrolleri():
    m = RiskMotoru()
    assert not m.onayla(_e(0.1, fiyat=60_000.0, emir="a"), PIY, _pf()).onay                        # fiyat bandı
    assert m.onayla(_e(0.1, emir="b"), PIY, _pf()).onay
    assert "çift emir" in m.onayla(_e(0.1, emir="b"), PIY, _pf()).gerekceler[0]                   # aynı kimlik
    bayat = Piyasa(50_000.0, T0, 3_600_000, True)
    assert "veri bayat" in m.onayla(_e(0.1, emir="c", zaman=T0 + 3 * 3_600_000), bayat, _pf()).gerekceler
    kapali = Piyasa(50_000.0, T0 + 3_600_000, 3_600_000, False)
    assert "piyasa kapalı" in m.onayla(_e(0.1, emir="d"), kapali, _pf()).gerekceler


def test_emir_hizi_siniri():
    m = RiskMotoru(RiskAyar(dakikalik_emir_sayisi=3, azami_emir_orani=1.0))
    sonuc = [m.onayla(_e(0.001, emir=f"e{i}"), PIY, _pf()).onay for i in range(5)]
    assert sonuc == [True, True, True, False, False]


def test_likidasyon_mesafesi():
    m = RiskMotoru()
    yakin = Piyasa(50_000.0, T0 + 3_600_000, 3_600_000, True, gunluk_oynaklik=0.04, likidasyon_fiyati=45_000.0)
    k = m.onayla(_e(0.1), yakin, _pf())  # mesafe %11 < 3 × %4
    assert not k.onay and "likidasyon" in k.gerekceler[0]


# --- portföy izleyici ---
def test_gunluk_fren_ertesi_gun_kalkar():
    iz = PortfoyIzleyici(baslangic_ozkaynak=100.0, baslangic_ms=T0)
    assert iz.guncelle(96.9, T0 + 3_600_000) == Durum.FREN_GUNLUK
    assert iz.guncelle(97.5, T0 + 5 * 3_600_000) == Durum.FREN_GUNLUK  # aynı gün
    assert iz.guncelle(97.5, T0 + GUN + 1) == Durum.NORMAL             # yeni UTC günü


def test_haftalik_fren_pazartesi_kalkar():
    iz = PortfoyIzleyici(baslangic_ozkaynak=100.0, baslangic_ms=T0)
    for g, oz in enumerate([98.0, 96.0, 94.0, 91.5]):  # her gün < %3 düşüş, hafta toplamı −%8,5
        d = iz.guncelle(oz, T0 + (g + 1) * GUN)
    assert d == Durum.FREN_HAFTALIK
    assert iz.guncelle(91.5, T0 + 6 * GUN) == Durum.FREN_HAFTALIK      # Pazar
    assert iz.guncelle(91.5, T0 + 7 * GUN + 1) == Durum.NORMAL          # Pazartesi


def test_acil_durdurma_yalniz_onayla_kalkar():
    iz = PortfoyIzleyici(baslangic_ozkaynak=100.0, baslangic_ms=T0)
    for g in range(1, 40):
        iz.guncelle(100.0 - 0.8 * g, T0 + g * GUN)  # yavaş erime: frenlere takılmadan −%25'e iner
    assert iz.durum == Durum.ACIL_DURDURMA
    assert iz.guncelle(200.0, T0 + 60 * GUN) == Durum.ACIL_DURDURMA  # toparlanma bile kaldırmaz
    with pytest.raises(ValueError):
        iz.acil_durdurma_kaldir("", "neden")
    iz_kayit = []
    iz.acil_durdurma_kaldir("Scryne", "inceledim, devam", denetim_kaydet=lambda *a: iz_kayit.append(a))
    assert iz.durum == Durum.NORMAL and iz_kayit[0][1] == "acil_durdurma_kaldirildi"
    assert iz.guncelle(199.0, T0 + 61 * GUN) == Durum.NORMAL  # tepe sıfırlandı: hemen yeniden durmaz


# --- frenler backtest'te ---
def test_backtest_acil_durdurma_sonrasi_duz():
    fiyat = np.r_[np.full(10, 100.0), 100 * 0.97 ** np.arange(1, 40), np.full(30, 40.0) * 1.05 ** np.arange(30)]
    n = len(fiyat)
    t = T0 + np.arange(n, dtype=np.int64) * GUN
    s = calistir(t, fiyat, np.ones(n), MaliyetModeli("0", 0, 0, 0), izleyici=PortfoyIzleyici(baslangic_ms=T0))
    acil = np.flatnonzero(s.durum == 3)
    assert len(acil) and s.pozisyon[acil].max() == 0.0          # acil durdurmadan sonra pozisyon yok
    assert s.ozkaynak.min() > 0.72                               # −%25 civarında kesildi (tek bar gecikme payı)
    assert s.ozkaynak[-1] == pytest.approx(s.ozkaynak[acil[0]])  # sonraki yükseliş kaçırıldı (onaysız dönüş yok)
