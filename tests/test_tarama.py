import numpy as np
import polars as pl
import pytest

from tradebot.arastirma import defter as df
from tradebot.arastirma.tarama import bar_yukle, tara
from tradebot.db import metadata, motor
from tradebot.veri.depo import BarDepo

SAAT = 3_600_000


@pytest.fixture
def ortam(ayar, monkeypatch):
    e = motor(ayar)
    metadata.create_all(e)
    monkeypatch.setattr(df, "kod_surumu", lambda: "abc1234")
    d = BarDepo(ayar.veri_dizini)
    rng = np.random.default_rng(3)
    n = 24 * 365 * 5
    c = 100 * np.exp(np.cumsum(rng.normal(0.00002, 0.006, n)))
    o = np.r_[c[0], c[:-1]]
    d.yaz("BINANCE:TESTUSDT", "1h", pl.DataFrame({
        "acilis_ms": 1_577_836_800_000 + np.arange(n, dtype=np.int64) * SAAT, "open": o, "high": np.maximum(o, c) * 1.001,
        "low": np.minimum(o, c) * 0.999, "close": c, "volume": rng.uniform(1, 2, n)}))
    return df.Defter(e), d


def test_bar_yukle_turetir(ortam):
    _, d = ortam
    b, ys, h = bar_yukle(d, "BINANCE:TESTUSDT", "1d")
    assert len(b) == 1825 and ys is None and len(h) == 64  # 24 × 365 × 5 saat


def test_tara_uctan_uca(ortam):
    defter, d = ortam
    defter.plan_ac("p", "trend", "sentetik", {"hizli": [5, 10], "yavas": [30, 60]}, ["BINANCE:TESTUSDT"], "puan > 0")
    r = tara(defter, d, "p", "sma_kesisim", "BINANCE:TESTUSDT", "BINANCE", "kripto", "1d",
             {"hizli": [5, 10], "yavas": [30, 60]})
    assert r["kombinasyon"] == 4 and defter.deneme_sayisi("trend") == 4
    assert 0 <= r["dsr"]["dsr"] <= 1 and r["dsr"]["deneme"] == 4
    assert r["walk_forward"]["pencere"] == 1 and r["plato"]["komsu_sayisi"] == 2
    assert set(r["yillik"]) >= {2020, 2024}
