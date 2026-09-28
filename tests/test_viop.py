"""VİOP sürekli vadeli serisi: vade geçişi sıçraması ayıklanır, baz erimesi kalır, bozuk tik atılır, delik raporlanır."""
import numpy as np
import polars as pl
import pytest

from tradebot.veri.viop import GUN_MS, sicra_don, surekli, vade_sonlari

T0 = 1_577_836_800_000   # 2020-01-01


def _seriler(n=400, faiz=0.35, seed=1):
    """İş günü seri: spot rastgele yürüyüş; vadeli = spot × (1 + faiz × vadeye kalan yıl), vade her 42 günde."""
    r = np.random.default_rng(seed).normal(0, 0.015, n)
    spot = 1000 * np.cumprod(1 + r)
    t = T0 + np.arange(n) * GUN_MS
    vadeler_i = list(range(41, n, 42))
    kalan = np.array([min((v for v in vadeler_i if v >= i), default=n) - i for i in range(n)]) / 252
    vadeli = spot * (1 + faiz * kalan)
    df = lambda c: pl.DataFrame({"acilis_ms": t, "open": c, "high": c, "low": c, "close": c,  # noqa: E731
                                 "volume": np.ones(n)})
    # kurum geçişi vade gününden bir gün sonra yapıyor: vade günü eski kontrat (baz ~0), ertesi gün yeni (baz tam)
    return df(vadeli), df(spot), [int(t[i]) for i in vadeler_i], vadeler_i


def test_gecis_sicramasi_ayiklanir():
    v, s, vadeler, vi = _seriler()
    ham_r = v["close"].pct_change().to_numpy()
    spot_r = s["close"].pct_change().to_numpy()
    seri, rapor = surekli(v, s, vadeler)
    ayarli_r = seri["close"].pct_change().to_numpy()
    gecis = [i + 1 for i in vi if i + 1 < len(ham_r)]                 # vade ertesi gün
    assert rapor["gecis"] == len(vi) and [g["gecis_ms"] for g in rapor["gecisler"]][:len(gecis)] == \
        [int(v["acilis_ms"][i]) for i in gecis]
    assert ham_r[gecis[0]] - spot_r[gecis[0]] > 0.05                  # ham seride ~%5–6'lık sahte sıçrama
    assert np.allclose(ayarli_r[gecis], spot_r[gecis])                # geçişte spot getirisi
    diger = [i for i in range(1, len(ham_r)) if i not in gecis]
    assert np.allclose(ayarli_r[diger], ham_r[diger])                 # geri kalanı vadelinin kendisi (baz erimesi dahil)
    assert seri["close"][-1] == pytest.approx(v["close"][-1])         # son fiyat gerçek vadeli fiyatı
    carpim = np.prod([g["k"] for g in rapor["gecisler"]])
    assert carpim > 1.5                                               # 9 geçiş × ~%5–6 sahte getiri ayıklandı
    assert 1 + rapor["ayarli_toplam_getiri"] == pytest.approx((1 + rapor["ham_toplam_getiri"]) / carpim)


def test_bozuk_tik_ve_delik():
    v, s, vadeler, _ = _seriler()
    kapanis = v["close"].to_numpy().copy()
    kapanis[100] = 10.0                                               # 2008-10-23 gibi bozuk tik
    assert sicra_don(kapanis)[100] and sicra_don(kapanis).sum() == 1
    v = v.with_columns(pl.Series("close", kapanis))
    v = v.filter((pl.col("acilis_ms") < T0 + 200 * GUN_MS) | (pl.col("acilis_ms") >= T0 + 300 * GUN_MS))  # 100 günlük delik
    seri, rapor = surekli(v, s, vadeler)
    assert rapor["atilan_sicrama"] == 1 and seri.height == v.height - 1
    assert rapor["delikler"] == [{"bas_ms": T0 + 199 * GUN_MS, "bit_ms": T0 + 300 * GUN_MS, "gun": 101}]
    assert all(g["gecis_ms"] < T0 + 200 * GUN_MS or g["gecis_ms"] > T0 + 300 * GUN_MS for g in rapor["gecisler"])


def test_vade_sonlari_cift_aylarin_son_is_gunu():
    from datetime import UTC, datetime
    v = vade_sonlari(int(datetime(2024, 1, 1, tzinfo=UTC).timestamp() * 1000),
                     int(datetime(2025, 1, 1, tzinfo=UTC).timestamp() * 1000))
    gunler = [datetime.fromtimestamp(x / 1000, UTC).date().isoformat() for x in v]
    # 2024-04-30 ve 2024-06-28: kurum serisindeki sıçramaların günleri (2026-09-28 ölçümü); 08-30 Zafer Bayramı
    assert gunler == ["2024-02-29", "2024-04-30", "2024-06-28", "2024-08-29", "2024-10-31", "2024-12-31"]


# --- VİOP 2: TL taşıma ---

def _barlar(kapanis, t0=T0):
    from tradebot.cekirdek import Barlar
    c = np.asarray(kapanis, dtype=float)
    return Barlar(t0 + np.arange(len(c)) * GUN_MS, c, c, c, c, np.ones(len(c)))


def test_tasima_filtreler_ve_nedensellik():
    from tradebot.cekirdek import StratejiTanimi, nedensellik_testi
    from tradebot.cekirdek.aileler import tasima
    rng = np.random.default_rng(3)
    # 300 gün sakin, TL taşımadan yavaş değer kaybı (kısa kârlı: seri düşüyor) + 20 günlük kriz (+%2/gün sıçrama)
    r = np.r_[rng.normal(-0.0005, 0.004, 300), 0.02 + rng.normal(0, 0.03, 20).clip(-0.015, 0.015),
              rng.normal(-0.0005, 0.004, 80)]
    c = 30 * np.exp(np.cumsum(r))
    b = _barlar(c)
    assert (tasima(b) == -1).all()                                            # saf taşıma: hep kısa
    s = tasima(b, ufuk=20)
    assert (s[:20] == 0).all() and s[100] == -1 and (s[305:320] == 0).all()   # ısınma kapalı; krizde trend kapatır
    v = tasima(b, pencere=20, uzun=250, kat=1.5)
    assert (v[:260] == 0).sum() >= 249 and v[280] == -1 and (v[305:318] == 0).all()  # oynaklık patlayınca kapalı
    nedensellik_testi(StratejiTanimi("tasima", "tasima", tasima, {"ufuk": 20, "pencere": 20}, yon="long_short"), b)


def test_ters_kote_algila_ve_cevir():
    from tradebot.veri.viop import ters_cevir, ters_mi
    rng = np.random.default_rng(5)
    s = 30 * np.exp(np.cumsum(rng.normal(0, 0.01, 200)))
    t = T0 + np.arange(200) * GUN_MS
    spot = pl.DataFrame({"acilis_ms": t, "close": s})
    duz = pl.DataFrame({"acilis_ms": t, "open": s, "high": s * 1.01, "low": s * 0.99, "close": s})
    ters = ters_cevir(duz.with_columns(pl.col("close") * 0 + 1000 / s))  # TRY/USD × 1000 benzeri
    assert not ters_mi(duz, spot) and ters_mi(ters.with_columns(pl.Series("close", 1000 / s)), spot)
    c = ters_cevir(duz)
    assert (c["high"] >= c["low"]).all() and np.allclose(c["close"].to_numpy(), 1 / s)


def test_saatlik_kapanis_gunluk():
    from tradebot.veri.viop import saatlik_kapanis_gunluk
    t = T0 + np.arange(72) * 3_600_000
    g = saatlik_kapanis_gunluk(pl.DataFrame({"acilis_ms": t, "close": np.arange(72.0)}), 15)
    assert g["acilis_ms"].to_list() == [T0, T0 + GUN_MS, T0 + 2 * GUN_MS] and g["close"].to_list() == [14.0, 38.0, 62.0]


def test_usdtry_surekli_uctan_uca(tmp_path):
    from sqlalchemy import create_engine

    from tradebot.db import metadata
    from tradebot.veri import enstruman as en
    from tradebot.veri.depo import BarDepo
    from tradebot.veri.viop import usdtry_surekli
    m = create_engine(f"sqlite:///{tmp_path / 'v.db'}")
    metadata.create_all(m)
    d = BarDepo(tmp_path)
    v, s, _, _ = _seriler(n=300, faiz=0.40)
    # spot saatlik (her gün 24 bar; 14:00 barının kapanışı o günün spotu), kaynak ters kote (TRY/USD × 1000)
    tt = np.repeat(s["acilis_ms"].to_numpy(), 24) + np.tile(np.arange(24) * 3_600_000, 300)
    d.yaz("DUKASCOPY:USDTRY", "1h", pl.DataFrame({"acilis_ms": tt, "open": np.repeat(s["close"].to_numpy(), 24),
          "high": np.repeat(s["close"].to_numpy(), 24), "low": np.repeat(s["close"].to_numpy(), 24),
          "close": np.repeat(s["close"].to_numpy(), 24), "volume": np.ones(len(tt))}))
    k = 1000 / v["close"].to_numpy()
    d.yaz("VIOP:TRYUSD_YAKINVADE", "1d", v.with_columns(pl.Series("open", k), pl.Series("high", k), pl.Series("low", k),
                                                           pl.Series("close", k)))
    r = usdtry_surekli(d, m)
    assert r["ters_cevrildi"] and r["gecis"] >= 9
    seri = d.oku("VIOP:USDTRY_SUREKLI", "1d")
    assert seri["close"][-1] == pytest.approx(v["close"][-1] / 1000)          # çevrilmiş: 1/(1000/v); getiriler aynı
    kayit = {x["kimlik"]: x for x in en.hepsi(m)}["VIOP:USDTRY_SUREKLI"]
    assert kayit["sinif"] == "doviz_vadeli" and kayit["takvim"] == "viop" and kayit["meta"]["ters_cevrildi"]
