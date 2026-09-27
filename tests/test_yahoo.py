import json
from datetime import UTC, datetime

from tradebot.veri.takvim import ms
from tradebot.veri.yahoo import tamamlanmamis_at, yanit_coz


def _yanit(ts, kapanis, olaylar=None):
    return json.dumps({"chart": {"error": None, "result": [{
        "timestamp": ts,
        "indicators": {"quote": [{"open": kapanis, "high": kapanis, "low": kapanis, "close": kapanis,
                                  "volume": [100] * len(ts)}], "adjclose": [{"adjclose": kapanis}]},
        "events": olaylar or {}}]}}).encode()


def test_coz_gun_basi_bos_satir_ve_olaylar():
    t1 = int(datetime(2026, 6, 1, 13, 30, tzinfo=UTC).timestamp())
    t2 = int(datetime(2026, 6, 2, 13, 30, tzinfo=UTC).timestamp())
    t3 = int(datetime(2026, 6, 3, 13, 30, tzinfo=UTC).timestamp())
    olay = {"splits": {str(t2): {"date": t2, "numerator": 5, "denominator": 1}},
            "dividends": {str(t3): {"date": t3, "amount": 1.5}}}
    df, ev = yanit_coz(_yanit([t1, t2, t3], [10.0, None, 12.0], olay))
    assert df["acilis_ms"].to_list() == [ms(datetime(2026, 6, 1, tzinfo=UTC)), ms(datetime(2026, 6, 3, tzinfo=UTC))]
    assert {"tarih_ms": ms(datetime(2026, 6, 2, tzinfo=UTC)), "tur": "bolunme", "deger": 5.0} in ev
    assert {"tarih_ms": ms(datetime(2026, 6, 3, tzinfo=UTC)), "tur": "temettu", "deger": 1.5} in ev


def test_tamamlanmamis_gun_atilir():
    gun = ms(datetime(2026, 6, 2, tzinfo=UTC))
    df, _ = yanit_coz(_yanit([int(datetime(2026, 6, 1, 13, 30, tzinfo=UTC).timestamp()),
                              int(datetime(2026, 6, 2, 13, 30, tzinfo=UTC).timestamp())], [1.0, 2.0]))
    seans_ici = ms(datetime(2026, 6, 2, 18, 0, tzinfo=UTC))    # NYSE kapanış 20:00 UTC
    kapanis_sonrasi = ms(datetime(2026, 6, 2, 20, 30, tzinfo=UTC))
    assert gun not in tamamlanmamis_at(df, "XNYS", seans_ici)["acilis_ms"].to_list()
    assert gun in tamamlanmamis_at(df, "XNYS", kapanis_sonrasi)["acilis_ms"].to_list()


def test_normalize_kapali_gun_bayat_ise_atilir_ohlc_onarilir():
    import numpy as np
    import polars as pl

    from tradebot.veri.takvim import takvim
    from tradebot.veri.yahoo import normalize

    gun = 86_400_000
    t0 = 1_675_036_800_000  # 2023-01-30 Pazartesi
    t = np.arange(t0, t0 + 14 * gun, gun, dtype=np.int64)
    acik = set(takvim("XIST").gunluk_barlar(int(t[0]), int(t[-1]) + 1).tolist())
    kapali = [x for x in t if x not in acik]
    assert 1_675_814_400_000 in kapali  # 2023-02-08: deprem sonrası iptal edilen seans
    n = len(t)
    df = pl.DataFrame({"acilis_ms": t, "open": np.full(n, 10.0), "high": np.full(n, 10.5), "low": np.full(n, 9.5),
                       "close": np.full(n, 10.2), "volume": np.full(n, 1e6)})
    hafta_sonu = [x for x in kapali if x != 1_675_814_400_000]
    df = df.with_columns(
        pl.when(pl.col("acilis_ms") == 1_675_814_400_000).then(2500.0)          # bayat: hacim çok düşük
        .when(pl.col("acilis_ms").is_in(hafta_sonu[:1])).then(1e6)              # normal hacim: kalır (takvim yanılabilir)
        .when(pl.col("acilis_ms").is_in(hafta_sonu[1:])).then(0.0)
        .otherwise(pl.col("volume")).alias("volume"),
        pl.when(pl.col("acilis_ms") == int(t[0])).then(9.9).otherwise(pl.col("high")).alias("high"))  # tutarsız
    out, d = normalize(df, "XIST")
    assert 1_675_814_400_000 not in out["acilis_ms"].to_list() and hafta_sonu[0] in out["acilis_ms"].to_list()
    assert d == {"kapali_gun_atildi": len(kapali) - 1, "ohlc_onarildi": 1}
    ilk = out.row(0, named=True)
    assert ilk["high"] == 10.2 and ilk["low"] == 9.5
