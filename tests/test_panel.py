"""Faz 5: aileler, kol backtest'i, point-in-time evren, turnuva koşucusu."""
import numpy as np
import polars as pl
import pytest

from tradebot.arastirma import defter as df
from tradebot.arastirma import turnuva as tv
from tradebot.arastirma.backtest import calistir
from tradebot.arastirma.maliyet import MaliyetModeli
from tradebot.arastirma.panel import (
    calistir_panel,
    evren_maskesi,
    grup_yukle,
    izgaraya,
    kripto_dislanir_mi,
    taraf_matrisi,
)
from tradebot.cekirdek import Barlar, StratejiTanimi, nedensellik_testi, ornek
from tradebot.cekirdek import aileler as al
from tradebot.cekirdek.boyut import KaldiracHatasi, panel_oynaklik_hedefi
from tradebot.db import metadata, motor
from tradebot.risk.motor import PortfoyIzleyici, RiskAyar
from tradebot.veri.depo import BarDepo

SAAT, GUN = 3_600_000, 86_400_000
T0 = 1_577_836_800_000  # 2020-01-01


def barlar(n=800, tohum=1, adim=GUN):
    rng = np.random.default_rng(tohum)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, n)))
    o = np.r_[c[0], c[:-1]]
    return Barlar(T0 + np.arange(n, dtype=np.int64) * adim, o, np.maximum(o, c) * 1.01, np.minimum(o, c) * 0.99, c,
                  rng.uniform(1, 10, n))


def yaz(d: BarDepo, kimlik, b: Barlar, zd="1d"):
    d.yaz(kimlik, zd, pl.DataFrame({"acilis_ms": b.t, "open": b.open, "high": b.high, "low": b.low, "close": b.close,
                                    "volume": b.volume}))


# ------------------------------------------------------------------ aileler
@pytest.mark.parametrize("tanim", [
    StratejiTanimi("ma_yon", "trend", al.ma_yon, {"hizli": 10, "yavas": 40}, yon="long_short"),
    StratejiTanimi("donchian_ls", "trend", al.donchian_ls, {"giris": 20, "cikis": 10}, yon="long_short"),
    StratejiTanimi("zskor", "ortalamaya_donus", al.zskor_donus, {"pencere": 20, "giris": 1.5, "cikis": 0.3}, yon="long_short"),
    StratejiTanimi("rsi", "ortalamaya_donus", al.rsi_donus, {"n": 2, "alt": 10, "trend": 50, "cikis_ma": 5}, yon="long_short"),
    StratejiTanimi("ay", "takvim", al.ay_donumu, {"son_gun": 3, "ilk_gun": 2}),
])
def test_aileler_gelecegi_gormez_ve_islem_uretir(tanim):
    b = barlar()
    nedensellik_testi(tanim, b, deneme=15)
    s = tanim.sinyal(b)
    assert np.abs(np.diff(s)).sum() >= 4  # gerçekten pozisyon değiştiriyor


def test_ma_yon_long_kolda_sma_kesisim_ile_ayni():
    b = barlar()
    a = StratejiTanimi("x", "trend", al.ma_yon, {"hizli": 10, "yavas": 40}).sinyal(b)
    np.testing.assert_array_equal(a, ornek.sma_kesisim(b, 10, 40))


def test_ay_donumu_pencere():
    t = np.array([np.datetime64(g, "ms").astype(np.int64) for g in
                  ["2024-01-26", "2024-01-27", "2024-01-31", "2024-02-01", "2024-02-02", "2024-02-03", "2024-02-15"]])
    b = Barlar(t, *(np.ones(len(t)) for _ in range(5)))
    # son_gun=4: 31 Ocak'a kalan ≤ 4 gün → 27 Ocak'tan itibaren; ilk_gun=3: ayın 1. ve 2. günü tutmaya devam
    np.testing.assert_array_equal(al.ay_donumu(b, son_gun=4, ilk_gun=3), [0, 1, 1, 1, 1, 0, 0])


def test_rsi_bilinen_deger():
    c = np.array([1.0, 2.0, 3.0, 2.0])
    r = al.rsi(c, 2)
    assert np.isnan(r[1]) and r[2] == 100.0 and 0 < r[3] < 100


def panel(k=6, n=500, tohum=2):
    rng = np.random.default_rng(tohum)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.02, (n, k)), axis=0))
    ev = np.ones((n, k), dtype=bool)
    ev[:100, 4:] = False  # sonradan listelenenler
    return al.Panel(T0 + np.arange(n, dtype=np.int64) * GUN, c, ev)


def test_kesitsel_momentum_nedensel_ve_evrende():
    p = panel()
    al.panel_nedensellik_testi(al.kesitsel_momentum, p, deneme=15, geriye=20, ust_n=2)
    w = al.kesitsel_momentum(p, geriye=20, ust_n=2, mutlak=False, haftalik=False)
    assert np.all(w.sum(axis=1) <= 1 + 1e-12) and np.all(w[:100, 4:] == 0)
    assert np.allclose(w[25:].sum(axis=1), 1.0)
    wm = al.kesitsel_momentum(p, geriye=20, ust_n=2, mutlak=True, haftalik=True)
    assert np.all(wm.sum(axis=1) <= 1 + 1e-12)
    degisim = np.flatnonzero(np.any(np.diff(wm, axis=0) != 0, axis=1)) + 1
    assert np.all(al.hafta_basi(p.t)[degisim])  # haftalık: yalnız haftanın ilk barında değişir


def test_panel_nedensellik_hileyi_yakalar():
    def hileli(p):
        return np.vstack([(p.close[1:] > p.close[:-1]).astype(float), np.zeros((1, p.close.shape[1]))])
    with pytest.raises(AssertionError, match="geleceği görüyor"):
        al.panel_nedensellik_testi(hileli, panel())


# ------------------------------------------------------------------ boyut
def test_panel_oynaklik_hedefi_nedensel_ve_tavanli():
    p = panel(n=600)
    s = np.ones_like(p.close)
    w = panel_oynaklik_hedefi(s, p.close, p.evrende, 0.5, 365, pencere=20, azami=1.5)
    assert np.all(np.abs(w).sum(axis=1) <= 1.5 + 1e-9) and np.all(w[:20] == 0)
    c2 = p.close.copy()
    c2[400:] *= 3.0
    w2 = panel_oynaklik_hedefi(s, c2, p.evrende, 0.5, 365, pencere=20, azami=1.5)
    np.testing.assert_array_equal(w[:400], w2[:400])
    with pytest.raises(KaldiracHatasi, match="yasak"):
        panel_oynaklik_hedefi(s, p.close, p.evrende, 0.5, 365, azami=5.0)


def test_panel_oynaklik_hedefi_hedefe_yakin():
    rng = np.random.default_rng(0)
    n, k = 4000, 5
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.03, (n, k)), axis=0))
    w = panel_oynaklik_hedefi(np.ones((n, k)), c, np.ones((n, k), bool), 0.2, 365, pencere=60, azami=3.0)
    r = c[1:] / c[:-1] - 1
    port = (w[:-1] * r).sum(axis=1)[100:]
    assert 0.15 < port.std() * np.sqrt(365) < 0.25


# ------------------------------------------------------------------ grup + backtest
@pytest.fixture
def depo(tmp_path):
    return BarDepo(tmp_path / "veri")


def test_tek_enstruman_panel_backtest_calistir_ile_ayni(depo):
    b = barlar(n=600)
    yaz(depo, "ARCA:AAA", b)
    g = grup_yukle(depo, ["ARCA:AAA"], "1d")
    mm = MaliyetModeli("x", 10.0, 2.0, 3.0, finansman_yillik=0.05)
    s = StratejiTanimi("s", "trend", ornek.sma_kesisim, {"hizli": 10, "yavas": 40}).sinyal(b)
    tek = calistir(b.t, b.open, s, mm)
    pan = calistir_panel(g, s[:, None], taraf_matrisi(g, [mm]), [mm])
    np.testing.assert_allclose(pan.net, tek.net, atol=1e-14)
    np.testing.assert_allclose(pan.ozkaynak, tek.ozkaynak, atol=1e-12)
    # frenlerle de aynı (long-only)
    iz = lambda: PortfoyIzleyici(RiskAyar(gunluk_fren=-0.01, haftalik_fren=-0.03), baslangic_ms=int(b.t[0]),  # noqa: E731
                                 acil_kalici=False)
    tek = calistir(b.t, b.open, s, mm, izleyici=iz())
    pan = calistir_panel(g, s[:, None], taraf_matrisi(g, [mm]), [mm], izleyici=iz())
    np.testing.assert_allclose(pan.net, tek.net, atol=1e-14)
    assert (pan.durum > 0).sum() > 0


def test_iki_enstruman_toplam_getiri_ve_takvim_boslugu(depo):
    a, b = barlar(n=300, tohum=1), barlar(n=300, tohum=2)
    yaz(depo, "ARCA:A", a)
    # B yalnız çift günlerde işlem görüyor (tatil gibi boşluklar)
    tek = np.arange(300) % 2 == 0
    yaz(depo, "ARCA:B", Barlar(b.t[tek], b.open[tek], b.high[tek], b.low[tek], b.close[tek], b.volume[tek]))
    g = grup_yukle(depo, ["ARCA:A", "ARCA:B"], "1d")
    assert g.acilis.shape == (300, 2) and g.bar_var[:, 1].sum() == 150
    mm = MaliyetModeli("sifir", 0.0, 0.0, 0.0)
    h = np.full((300, 2), 0.5)
    s = calistir_panel(g, h, taraf_matrisi(g, [mm, mm]), [mm, mm])
    # sıfır maliyet, sabit %50/%50 hedef: bar getirisi iki enstrümanın kaymış ağırlıklı getirisi, özkaynak pozitif
    assert np.isfinite(s.ozkaynak).all() and s.devir[0] == 0
    # B'nin 1. günde barı yok: A 1. günde, B ancak barı olan 2. günde alınır
    assert s.devir[1] == pytest.approx(0.5) and s.devir[2] >= 0.5
    # B'nin bar olmayan günlerde fiyatı sabit (getiri 0), işlem yapılmıyor
    assert np.all(np.diff(g.acilis[:, 1])[~g.bar_var[1:, 1]] == 0)


def test_kalkan_enstruman_zorla_kapanir(depo):
    a, b = barlar(n=300, tohum=1), barlar(n=200, tohum=2)
    yaz(depo, "ARCA:A", a)
    yaz(depo, "ARCA:B", b)  # 200. bardan sonra işlem yok
    g = grup_yukle(depo, ["ARCA:A", "ARCA:B"], "1d")
    mm = MaliyetModeli("x", 10.0, 0.0, 0.0)
    s = calistir_panel(g, np.full((300, 2), 0.5), taraf_matrisi(g, [mm, mm]), [mm, mm])
    assert s.devir[200] == pytest.approx(0.5, rel=0.2)       # B çıkışı
    assert s.pozisyon[201:].max() < 0.6                       # yalnız A kaldı
    # bar 200: B çıkışı 3 kat maliyetle + A'nın küçük yeniden dengelemesi 1 kat
    b_cikis = s.devir[200] - s.devir[199]
    assert s.maliyet[200] > 2.5 * 10e-4 * b_cikis


def _evren_depo(kok, gelecek_hacim=None):
    d = BarDepo(kok)
    for i in range(5):
        b = barlar(n=200, tohum=i)
        v = np.full(200, 10.0 ** (i + 1))
        if i == 0:
            v[150:] = 1e9  # en küçük, 150. günden sonra en likit olur
        if i == 1 and gelecek_hacim is not None:
            v[170:] = gelecek_hacim
        yaz(d, f"BINANCE:C{i}USDT", Barlar(b.t, b.open, b.high, b.low, b.close, v / b.close))
    return grup_yukle(d, [f"BINANCE:C{i}USDT" for i in range(5)], "1d")


def test_evren_point_in_time_ve_ilk_n(tmp_path):
    g = _evren_depo(tmp_path / "a")
    e, lik = evren_maskesi(g, ilk_n=2, likidite_gun=10, asgari_gecmis_gun=20)
    assert not e[:19].any() and (e.sum(axis=1)[30:] == 2).all()  # yeterli geçmiş yokken boş; sonra hep 2
    j0 = g.kimlikler.index("BINANCE:C0USDT")
    assert not e[100, j0] and e[199, j0]      # sonradan likit olunca girer
    # günlük bar d'nin kararı d'nin kapanışında: d'nin hacmi o anda bilinir → 149'da yok, 150'de var
    assert not e[149, j0] and e[150, j0]
    # gelecek-bozma: 170. günden itibaren hacim değişince 170'ten önceki barların maskesi aynı
    g2 = _evren_depo(tmp_path / "b", gelecek_hacim=1e15)
    e2, _ = evren_maskesi(g2, ilk_n=2, likidite_gun=10, asgari_gecmis_gun=20)
    np.testing.assert_array_equal(e2[:170], e[:170])
    assert not np.array_equal(e2[170:], e[170:])


def test_izgaraya_son_degeri_korur(depo):
    a = barlar(n=10)
    yaz(depo, "ARCA:A", a)
    yaz(depo, "ARCA:B", Barlar(a.t[::2], a.open[::2], a.high[::2], a.low[::2], a.close[::2], a.volume[::2]))
    g = grup_yukle(depo, ["ARCA:A", "ARCA:B"], "1d")
    np.testing.assert_array_equal(izgaraya(g, 1, np.arange(1.0, 6.0)), [1, 1, 2, 2, 3, 3, 4, 4, 5, 5])


def test_kripto_dislama():
    assert kripto_dislanir_mi("BINANCE:BTCUPUSDT") and kripto_dislanir_mi("BINANCE:USDCUSDT")
    assert kripto_dislanir_mi("BINANCE:WBTCUSDT") and kripto_dislanir_mi("BINANCE:BNBBEARUSDT")
    assert not kripto_dislanir_mi("BINANCE:BTCUSDT") and not kripto_dislanir_mi("BINANCE:SUPERUSDT")


# ------------------------------------------------------------------ turnuva uçtan uca
@pytest.fixture
def ortam(ayar, monkeypatch):
    e = motor(ayar)
    metadata.create_all(e)
    monkeypatch.setattr(df, "kod_surumu", lambda: "abc1234")
    d = BarDepo(ayar.veri_dizini)
    for i in range(4):
        b = barlar(n=24 * 365 * 5 // 24, tohum=10 + i)
        yaz(d, f"ARCA:E{i}", b)
    kayit = {f"ARCA:E{i}": {"piyasa": "ARCA", "sinif": "etf", "takvim": "XNYS"} for i in range(4)}
    return df.Defter(e), d, kayit


@pytest.mark.parametrize("strateji,izgara", [
    ("tsmom", {"ufuk_gun": [20, 60]}),
    ("kesitsel_momentum", {"geriye_gun": [20, 60], "ust_n": [2]}),
])
def test_kol_kos_uctan_uca(ortam, strateji, izgara):
    defter, d, kayit = ortam
    aile = tv.STRATEJILER[strateji][0]
    defter.plan_ac("p", aile, "sentetik", izgara, ["kol:etf"], "A/B ölçütü")
    h = tv.grup_hazirla(d, kayit, {"kimlikler": list(kayit)}, "1d")
    r = tv.kol_kos(defter, h, "p", strateji, "etf", izgara, "long", tv.Ayar(hedef_vol=0.2, kaldirac=2.0))
    assert defter.deneme_sayisi(aile) == 2 and r["dsr"]["deneme"] == 2
    assert r["karar"] in {"A", "B", "KALDI"} and r["walk_forward"]["pencere"] >= 1
    assert set(r["stres"]) >= {"maliyet_2x_puan", "gecikme_puan"} and set(r["rejim"]) == {"yukari", "asagi"}
    assert r["stres"]["maliyet_2x_puan"] <= r["en_iyi"]["puan"] + 1e-12
    assert r["en_iyi"]["yillik_oynaklik"] < 0.4  # oynaklık hedefi (%20) çalışıyor


def test_cevir_ve_bar_gun():
    assert tv.cevir({"ufuk_gun": 30, "ust_n": 3}, 24.0) == {"ufuk": 720, "ust_n": 3}
    assert tv.bar_gun("4h", "kripto_7x24") == 6 and tv.bar_gun("1d", "XNYS") == 1
    with pytest.raises(ValueError):
        tv.bar_gun("1h", "XNYS")


def test_karar_kurallari():
    o = tv.Olcut()
    temel = {"en_iyi": {"kapilar_gecti": True}, "yil_pozitif_orani": 0.7, "plato": {"plato_var": True},
             "walk_forward": {"pencere": 3, "oos_en_kotu_hafta": -0.05, "oos_en_kotu_dusus": -0.2, "oos_yillik": 0.1},
             "rejim": {"yukari": {"t": 1.0}, "asagi": {"t": -1.0}},
             "stres": {"maliyet_2x_puan": 0.001, "gecikme_puan": 0.001}, "dsr": {"dsr": 0.97}}
    assert tv.karar(temel, o) == "A"
    assert tv.karar(temel | {"dsr": {"dsr": 0.85}}, o) == "B"
    assert tv.karar(temel | {"plato": {"plato_var": False}}, o) == "B"
    assert tv.karar(temel | {"dsr": {"dsr": 0.5}}, o) == "KALDI"
    assert tv.karar(temel | {"stres": {"maliyet_2x_puan": -0.001, "gecikme_puan": 0.001}}, o) == "KALDI"
    assert tv.karar(temel | {"rejim": {"yukari": {"t": 3.0}, "asagi": {"t": -2.5}}}, o) == "KALDI"
    assert tv.karar(temel | {"en_iyi": {"kapilar_gecti": False}}, o) == "KALDI"
    assert tv.karar(temel | {"en_fazla": "B"}, o) == "B"  # yanlılığı bilinen grup


def test_evren_saatlik_bar_bitmemis_gunu_gormez(tmp_path):
    d = BarDepo(tmp_path)
    n = 24 * 40
    for i in range(2):
        b = barlar(n=n, tohum=i, adim=SAAT)
        v = np.full(n, 100.0 if i == 0 else 1000.0)
        if i == 0:
            v[24 * 30:] = 1e9  # 30. gün 00:00'dan itibaren çok likit
        yaz(d, f"BINANCE:H{i}USDT", Barlar(b.t, b.open, b.high, b.low, b.close, v / b.close), zd="1h")
    g = grup_yukle(d, ["BINANCE:H0USDT", "BINANCE:H1USDT"], "1h")
    e, _ = evren_maskesi(g, ilk_n=1, likidite_gun=3, asgari_gecmis_gun=5)
    # 30. günün saatlik barları o gün bitmeden 29. günün satırını kullanır; günün son barı (kapanışı 31. gün 00:00) 30'u
    assert not e[24 * 30 + 5, 0] and not e[24 * 30 + 22, 0] and e[24 * 30 + 23, 0]


def test_dalga1_on_kayit_dosyasi_gecerli():
    from pathlib import Path

    d = tv.dalga_oku(Path(__file__).resolve().parents[1] / "config" / "turnuva" / "dalga1.yaml")
    ks = tv.kollar(d)
    assert all(k["strateji"] in tv.STRATEJILER for k in ks)
    assert {k["plan"] for k in ks} == {p["kimlik"] for p in d["planlar"].values()}
    assert all(k["yon"] == "long" for k in ks if k["grup"].startswith(("kripto", "bist")))  # spot/BIST açığa satış yok
    assert all(k["yon"] == "long" for k in ks if k["strateji"] in ("kesitsel_momentum", "ay_donumu"))
    assert all(k["zd"] == "1d" for k in ks if k["grup"].startswith(("abd", "bist")))  # borsalarda gün içi veri yok
    assert d["_ayar"].kaldirac <= 3.0 and d["_ayar"].olcut.dsr_a == 0.95
    assert all(k["en_fazla"] == "B" for k in ks if k["grup"] == "bist_hisse")
