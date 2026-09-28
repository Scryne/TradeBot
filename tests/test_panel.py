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
    StratejiTanimi("ay", "takvim", al.ay_donumu, {"son": 3, "ilk": 2}),
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
    np.testing.assert_array_equal(al.ay_donumu(b, son=4, ilk=3), [0, 1, 1, 1, 1, 0, 0])


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
    hf = r["haftalik"]
    assert len(hf["tam"]["hafta"]) == len(hf["tam"]["log"]) == r["en_iyi"]["hafta"] and len(hf["oos"]["log"]) > 0
    assert sum(hf["tam"]["log"]) == pytest.approx(r["en_iyi"]["puan"] * r["en_iyi"]["hafta"], abs=1e-6 * r["en_iyi"]["hafta"])


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
    o0 = tv.Olcut(dsr_b=0.0)  # Dalga-1 ek 3: B için DSR şartı yok, A için aynen
    assert tv.karar(temel | {"dsr": {"dsr": 0.1}}, o0) == "B" and tv.karar(temel | {"dsr": {"dsr": float("nan")}}, o0) == "B"
    assert tv.karar(temel | {"dsr": {"dsr": 0.97}}, o0) == "A"
    assert tv.karar(temel | {"dsr": {"dsr": 0.1}, "en_iyi": {"kapilar_gecti": False}}, o0) == "KALDI"
    assert tv.karar(temel | {"stres": {"maliyet_2x_puan": -0.001, "gecikme_puan": 0.001}}, o) == "KALDI"
    assert tv.karar(temel | {"rejim": {"yukari": {"t": 3.0}, "asagi": {"t": -2.5}}}, o) == "KALDI"
    assert tv.karar(temel | {"en_iyi": {"kapilar_gecti": False}}, o) == "KALDI"
    assert tv.karar(temel | {"en_fazla": "B"}, o) == "B"  # yanlılığı bilinen grup
    # risksiz faiz çıtası (2026-09-28): OOS %4 < T-bill %4,5 → kalır; varsayılan 0 eski dalgalarla aynı
    dusuk = temel | {"walk_forward": temel["walk_forward"] | {"oos_yillik": 0.04}}
    assert tv.karar(dusuk, o) == "A" and tv.karar(dusuk, tv.Olcut(risksiz_yillik=0.045)) == "KALDI"


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
    assert d["_ayar"].kaldirac <= 3.0 and d["_ayar"].olcut.dsr_a == 0.95 and d["_ayar"].olcut.dsr_b == 0.0
    assert all(k["en_fazla"] == "B" for k in ks if k["grup"] == "bist_hisse")


def test_panel_oynaklik_hedefi_nakitten_giriste_patlamaz():
    """Hata (d0625fa): kol ölçeği portföyün geçmiş getirisinden hesaplanınca, uzun nakit döneminden sonra girişte
    ölçek patlıyor ve kaldıraç tavana vuruyordu. Ex-ante ölçekte giriş ağırlığı hedef / varlık oynaklığı olmalı."""
    rng = np.random.default_rng(5)
    n = 1000
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.04, (n, 1)), axis=0))  # yıllık ~%76
    s = np.zeros((n, 1))
    s[600:] = 1.0  # 600 bar nakit, sonra long
    w = panel_oynaklik_hedefi(s, c, np.ones((n, 1), bool), 0.2, 365, pencere=60, azami=3.0)
    assert w[:600].max() == 0
    assert 0.15 < w[600, 0] < 0.4  # ≈ 0.2 / 0.76, 3x tavan DEĞİL


def test_dsr_sonlandir_nihai_deneme_sayisiyla(ortam):
    defter, d, kayit = ortam
    izgara = {"ufuk_gun": [20, 60]}
    defter.plan_ac("p", "trend", "sentetik", izgara, ["kol:etf"], "x")
    h = tv.grup_hazirla(d, kayit, {"kimlikler": list(kayit)}, "1d")
    r = tv.kol_kos(defter, h, "p", "tsmom", "etf", izgara, "long", tv.Ayar())
    assert r["dsr"]["deneme"] == 2
    tv.kol_kos(defter, h, "p", "ma_yon", "etf", {"hizli_gun": [5, 10], "yavas_gun": [40, 80]}, "long", tv.Ayar())
    s = tv.dsr_sonlandir(defter, r, tv.Olcut())
    assert s["dsr"]["deneme"] == 6 and s["dsr"]["nihai"] and s["dsr_kosu"]["deneme"] == 2
    assert s["dsr"]["sr_haftalik"] == r["dsr"]["sr_haftalik"]
    assert tv.dsr_sonlandir(defter, s, tv.Olcut())["dsr"]["deneme"] == 6  # tekrar uygulanabilir (idempotent)


# ------------------------------------------------------------------ carry (dalga 1b)
def _funding(n=3 * 365 * 5, tohum=0, ort=0.0001):
    rng = np.random.default_rng(tohum)
    t = T0 + np.arange(n, dtype=np.int64) * 8 * SAAT
    rejim = np.sin(np.arange(n) / 200) > -0.3  # pozitif ve negatif funding dönemleri
    o = np.where(rejim, ort, -ort) + rng.normal(0, 0.00005, n)
    return pl.DataFrame({"zaman_ms": t, "oran": o})


def test_carry_sinyali_nedensel_ve_getiri():
    from tradebot.arastirma import carry as cr

    t, o, _ = cr.funding_izgarasi({"A": _funding(tohum=1), "B": _funding(tohum=2)})
    s = cr.funding_sinyali(t, o, 7, 0.05)
    o2 = o.copy()
    o2[2000:] *= -5
    np.testing.assert_array_equal(cr.funding_sinyali(t, o2, 7, 0.05)[:2000], s[:2000])  # gelecek-bozma
    assert s[:21].sum() == 0  # pencere dolmadan sinyal yok
    son = cr.calistir_carry(t, o, s, 13.0, notional=0.5)
    assert son.ozkaynak[-1] > 1.0 and son.pozisyon.max() <= 1.0 + 1e-12  # brüt = 2 × notional ≤ 1
    # sinyal olay i'de → getiri olay i+1'den: ilk açık olayda getiri yok, yalnız maliyet
    ilk = int(np.flatnonzero(s.any(axis=1))[0])
    assert son.brut[ilk] == 0 and son.maliyet[ilk + 1] > 0
    assert cr.calistir_carry(t, o, s, 13.0, maliyet_carpani=2).ozkaynak[-1] < son.ozkaynak[-1]


def test_carry_kol_kos(ortam):
    defter, _, _ = ortam
    izgara = {"pencere_gun": [3, 7], "esik_yillik": [0.05, 0.1]}
    defter.plan_ac("c", "carry", "sentetik", izgara, ["kol:kripto_funding"], "x")
    r = tv.carry_kol_kos(defter, "c", {"A": _funding(tohum=1), "B": _funding(tohum=2)}, izgara, tv.Ayar(), 13.0, "h" * 64)
    assert defter.deneme_sayisi("carry") == 4 and r["karar"] in {"B", "KALDI"} and r["rejim"] == {}
    assert r["walk_forward"]["pencere"] >= 1


def test_portfoy_birlestirme_cesitlendirme_ve_tavan():
    from tradebot.arastirma import portfoy as pf

    rng = np.random.default_rng(0)
    h = np.arange(300)
    seriler = {f"k{i}": {"hafta": h.tolist(), "log": np.log1p(rng.normal(0.003, 0.03, 300)).tolist()} for i in range(4)}
    r = pf.birlestir(seriler, {f"k{i}": 0.5 for i in range(4)})
    tek = pf.birlestir({"k0": seriler["k0"]}, {"k0": 0.5})
    assert abs(r["ort_korelasyon"]) < 0.2
    assert r["1x"]["sharpe"] > tek["1x"]["sharpe"]  # ilişkisiz kollar birleşince Sharpe artar
    assert 0 <= r["kaldirac"] <= 3.0 and r["kaldirac"] <= r["brut_tavan_kaldirac"] + 1e-12
    # brüt tavan: kolların maruziyeti 2x ise kaldıraç en fazla 1,5
    assert pf.birlestir(seriler, {f"k{i}": 2.0 for i in range(4)})["kaldirac"] <= 1.5 + 1e-12
    # eksik haftalar: kol yokken ağırlık 0
    s2 = seriler | {"yeni": {"hafta": h[200:].tolist(), "log": [0.01] * 100}}
    assert pf.birlestir(s2, {})["son_agirlik"]["yeni"] == 0.0  # sıfır oynaklık → ağırlık yok


# ------------------------------------------------------------------ gün içi kırılım (dalga 1c)
def test_abd_yaz_saati_bilinen_tarihler():
    g = np.array(["2024-03-09", "2024-03-10", "2024-11-02", "2024-11-03", "2025-03-09", "2023-03-12", "2023-11-05"],
                 dtype="datetime64[D]")
    np.testing.assert_array_equal(al.abd_yaz_saati(g), [False, True, True, False, True, True, False])


def test_ny_seans_takvimle_ayni():
    from tradebot.veri.takvim import takvim

    t = np.array([np.datetime64(g, "ms").astype(np.int64) for g in ["2024-01-10", "2024-07-10", "2025-03-11", "2025-11-12"]])
    acilis, kapanis = al.ny_seans(t)
    for a, c, g in zip(acilis, kapanis, t, strict=True):
        o, k = takvim("XNYS").seanslar(int(g), int(g))[1]  # aynı günün seansı (seanslar bir gün önceden başlar)
        assert (a, c) == (o, k)


def _dakika_gun(gun: str, yol: np.ndarray, bar_dk=5):
    """gun 13:00 UTC'den 21:00'e bar_dk'lık barlar; fiyat yolu verilir."""
    t0 = np.datetime64(gun, "ms").astype(np.int64) + 13 * 3_600_000
    t = t0 + np.arange(len(yol), dtype=np.int64) * bar_dk * 60_000
    o = np.r_[yol[0], yol[:-1]]
    return Barlar(t, o, np.maximum(o, yol), np.minimum(o, yol), yol, np.ones(len(yol)))


def test_acilis_araligi_kirilim_kurallari():
    # 2024-07-10 (yaz saati): seans 13:30 UTC → bar 6 (13:30) ... aralık 30 dk = bar 6..11; 96 bar = 21:00'e kadar
    yol = np.full(96, 100.0)
    yol[6:12] = [100, 101, 99, 100, 100.5, 100]   # aralık: tepe ~101, dip ~99
    yol[14] = 102                                  # kırılım yukarı
    yol[15:] = 102
    yol[40] = 98.5                                 # stop (dibin altı)
    yol[41:] = 103                                 # yeniden kırılım: günde tek giriş → girmez
    b = _dakika_gun("2024-07-10", yol)
    s = al.acilis_araligi_kirilim(b, aralik_dk=30, cikis_dk=15)
    assert s[:14].sum() == 0 and s[14] == 1 and s[39] == 1 and s[40] == 0 and s[41:].sum() == 0
    # çıkış: kapanıştan 15 dk önce (20:00 − 15 dk = 19:45 UTC) pozisyon kapanır
    yol2 = yol.copy()
    yol2[40:] = 102
    s2 = al.acilis_araligi_kirilim(_dakika_gun("2024-07-10", yol2), 30, 15)
    kapanis_bari = (19 * 60 + 45 - 13 * 60) // 5  # kapanışı 19:45 olan bar = açılışı 19:40 → indeks 80
    assert s2[kapanis_bari - 2] == 1 and s2[kapanis_bari - 1:].sum() == 0
    # kış saati: seans 14:30 UTC → aynı yol bir saat geç işlenir
    s3 = al.acilis_araligi_kirilim(_dakika_gun("2024-01-10", yol), 30, 15)
    assert s3[:26].sum() == 0


def test_acilis_araligi_kirilim_gelecegi_gormez():
    rng = np.random.default_rng(0)
    parca = [_dakika_gun(g, 100 * np.exp(np.cumsum(rng.normal(0, 0.002, 96))))
             for g in ["2024-07-08", "2024-07-09", "2024-07-10", "2024-07-11"]]
    b = Barlar(*(np.concatenate([getattr(p, k) for p in parca]) for k in ("t", "open", "high", "low", "close", "volume")))
    nedensellik_testi(StratejiTanimi("orb", "gun_ici_kirilim", al.acilis_araligi_kirilim, {"aralik_dk": 30},
                                     yon="long_short"), b, deneme=20)


def test_gun_ici_kol_seans_maskesi(tmp_path):
    d = BarDepo(tmp_path)
    rng = np.random.default_rng(1)
    t0 = np.datetime64("2024-07-01", "ms").astype(np.int64)
    n = 12 * 24 * 12  # 12 gün, 5 dk (hafta sonu dahil; maske ayıklar)
    t = t0 + np.arange(n, dtype=np.int64) * 300_000
    c = 5000 * np.exp(np.cumsum(rng.normal(0, 0.0008, n)))
    o = np.r_[c[0], c[:-1]]
    d.yaz("DUKASCOPY:USA500IDXUSD", "5m", pl.DataFrame(
        {"acilis_ms": t, "open": o, "high": np.maximum(o, c) * 1.0003, "low": np.minimum(o, c) * 0.9997, "close": c,
         "volume": np.ones(n)}))
    kayit = {"DUKASCOPY:USA500IDXUSD": {"piyasa": "DUKASCOPY", "sinif": "endeks", "takvim": "fx_24x5"}}
    h = tv.grup_hazirla(d, kayit, {"kimlikler": list(kayit), "asgari_gecmis_gun": 1, "seans": "XNYS"}, "5m")
    hedef = tv.hedef_uret(h, "acilis_araligi", {"aralik_dk": 30, "cikis_dk": 15}, "long_short", tv.Ayar(vol_pencere_gun=1))
    from tradebot.veri.takvim import takvim

    seans = takvim("XNYS").acik_maske(h.g.t)
    assert np.abs(hedef).sum() > 0 and np.all(hedef[~seans] == 0)  # 4 Temmuz tatili ve hafta sonu dahil
    tatil = (h.g.t >= np.datetime64("2024-07-04", "ms").astype(np.int64)) & (
        h.g.t < np.datetime64("2024-07-05", "ms").astype(np.int64))
    assert np.all(hedef[tatil] == 0)


def test_toplam_getiri_temettu_dahil(depo):
    # 100'de sabit fiyat; 5. günde 2'lik temettü (fiyat 98'e düşer). adj_close: temettüden önceki günler 0,98 çarpanlı
    n = 10
    t = T0 + np.arange(n, dtype=np.int64) * GUN
    c = np.r_[np.full(5, 100.0), np.full(5, 98.0)]
    adj = np.r_[np.full(5, 98.0), np.full(5, 98.0)]
    depo.yaz("ARCA:DIV", "1d", pl.DataFrame({"acilis_ms": t, "open": c, "high": c, "low": c, "close": c,
                                             "volume": np.ones(n), "adj_close": adj}))
    g = grup_yukle(depo, ["ARCA:DIV"], "1d")
    np.testing.assert_allclose(g.acilis[:, 0], 98.0)  # toplam getiri serisi düz: temettü düşüşü getiri değil
    mm = MaliyetModeli("sifir", 0.0, 0.0, 0.0)
    kisa = calistir_panel(g, np.full((n, 1), -0.5), taraf_matrisi(g, [mm]), [mm])
    assert kisa.ozkaynak[-1] == pytest.approx(1.0)  # short temettü düşüşünden kâr ETMEZ


def test_enstruman_tavani():
    rng = np.random.default_rng(0)
    n = 400
    c = np.column_stack([100 * np.exp(np.cumsum(rng.normal(0, 0.001, n))),   # çok düşük oynaklık (SHY gibi)
                         100 * np.exp(np.cumsum(rng.normal(0, 0.03, n)))])
    w = panel_oynaklik_hedefi(np.ones((n, 2)), c, np.ones((n, 2), bool), 0.2, 252, pencere=30, azami=3.0,
                              varlik_tavani=0.5)
    assert np.abs(w).max() <= 0.5 + 1e-12 and w[100:, 0].max() == pytest.approx(0.5)


def test_karisik_takvim_yillik_bar_veriden(tmp_path):
    d = BarDepo(tmp_path)
    n = 730
    b = barlar(n=n, tohum=3)  # 7/24 günlük
    yaz(d, "BINANCE:KUSDT", b)
    hafta_ici = ((b.t // GUN + 3) % 7) < 5  # 1970-01-01 Perşembe → Pazartesi=0
    e = barlar(n=n, tohum=4)
    yaz(d, "ARCA:E", Barlar(*(x[hafta_ici] for x in (e.t, e.open, e.high, e.low, e.close, e.volume))))
    kayit = {"BINANCE:KUSDT": {"piyasa": "BINANCE", "sinif": "kripto", "takvim": "kripto_7x24"},
             "ARCA:E": {"piyasa": "ARCA", "sinif": "etf", "takvim": "XNYS"}}
    h = tv.grup_hazirla(d, kayit, {"kimlikler": list(kayit), "asgari_gecmis_gun": 5}, "1d")
    assert h.bar_yil_olcu == pytest.approx(365.25, rel=0.01)
    tek = tv.grup_hazirla(d, {"ARCA:E": kayit["ARCA:E"]}, {"kimlikler": ["ARCA:E"], "asgari_gecmis_gun": 5}, "1d")
    assert tek.bar_yil_olcu is None  # tek takvim: takvimin değeri (252)


def test_karma_grupta_kripto_yalniz_long(tmp_path):
    d = BarDepo(tmp_path)
    b = barlar(n=400, tohum=5)
    yaz(d, "BINANCE:KUSDT", b)
    yaz(d, "ARCA:E", barlar(n=400, tohum=6))
    kayit = {"BINANCE:KUSDT": {"piyasa": "BINANCE", "sinif": "kripto", "takvim": "kripto_7x24"},
             "ARCA:E": {"piyasa": "ARCA", "sinif": "etf", "takvim": "kripto_7x24"}}
    h = tv.grup_hazirla(d, kayit, {"kimlikler": list(kayit), "asgari_gecmis_gun": 5}, "1d")
    w = tv.hedef_uret(h, "tsmom", {"ufuk": 20}, "long_short", tv.Ayar(vol_pencere_gun=20))
    j_k, j_e = h.g.kimlikler.index("BINANCE:KUSDT"), h.g.kimlikler.index("ARCA:E")
    assert w[:, j_k].min() >= 0 and w[:, j_e].min() < 0  # kripto short açılmaz, ETF açılabilir


def test_veto_riski_artirmaz_ve_pit(depo):
    from tradebot.arastirma.panel import veto_maskesi

    a = barlar(n=100, tohum=7)
    yaz(depo, "BINANCE:VUSDT", a)
    g = grup_yukle(depo, ["BINANCE:VUSDT"], "1d")
    mm = MaliyetModeli("sifir", 0.0, 0.0, 0.0)
    hedef = np.zeros((100, 1))
    hedef[10:] = 0.5
    hedef[50:] = 0.8  # bar 50'de büyütme isteği
    v = veto_maskesi(g, [("BINANCE:VUSDT", int(g.t[40]), None), ("BAŞKA", 0, None)])
    assert not v[39, 0] and v[40, 0]  # geçerli olmadan önce görünmez
    s = calistir_panel(g, hedef, taraf_matrisi(g, [mm]), [mm], veto=v)
    s0 = calistir_panel(g, hedef, taraf_matrisi(g, [mm]), [mm])
    assert s0.pozisyon[52] > 0.7 and s.pozisyon[52] < 0.6  # vetosuz büyür, vetoda büyüyemez
    h2 = hedef.copy()
    h2[60:] = 0.2  # küçültme her zaman geçer
    s2 = calistir_panel(g, h2, taraf_matrisi(g, [mm]), [mm], veto=v)
    assert s2.pozisyon[62] == pytest.approx(0.2, abs=0.05)
    v2 = veto_maskesi(g, [("BINANCE:VUSDT", int(g.t[40]), int(g.t[45]))])
    assert v2[44, 0] and not v2[45, 0]  # süreli veto biter


def test_likidite_temettu_duzeltmesinden_bagimsiz(tmp_path):
    """2026-09-28 denetimi: likidite sıralaması temettü düzeltmeli fiyatla yapılıyordu; düzeltme çarpanı SONRAKİ
    temettülere bağlı olduğundan eski günlerin cirosu gelecek bilgisiyle küçülüyordu. Ciro düzeltmeden önce ölçülür."""
    from tradebot.arastirma.panel import evren_maskesi, grup_yukle
    d = BarDepo(tmp_path)
    n = 200
    t = np.arange(n, dtype=np.int64) * GUN + 1_600_000_000_000 // GUN * GUN
    for kimlik, hacim, adj in (("BIST:AAA", 1100.0, 0.5), ("BIST:BBB", 1000.0, 1.0)):
        c = np.full(n, 10.0)
        d.yaz(kimlik, "1d", pl.DataFrame({"acilis_ms": t, "open": c, "high": c, "low": c, "close": c,
                                           "volume": np.full(n, hacim), "adj_close": c * adj}))
    g = grup_yukle(d, ["BIST:AAA", "BIST:BBB"], "1d")
    e, lik = evren_maskesi(g, ilk_n=1, likidite_gun=10, asgari_gecmis_gun=20)
    # AAA'nın gerçek cirosu %10 fazla; düzeltilmiş fiyatla (×0,5) BBB'nin gerisinde görünürdü
    assert e[50, 0] and not e[50, 1] and lik[50, 0] == pytest.approx(11_000.0)
