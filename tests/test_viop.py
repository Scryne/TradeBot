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
