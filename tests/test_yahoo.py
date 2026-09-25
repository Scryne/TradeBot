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
