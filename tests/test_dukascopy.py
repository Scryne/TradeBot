import lzma
import struct
from datetime import UTC, datetime

from tradebot.veri.dukascopy import aylar, bi5_coz, kapali_ayikla, olcek
from tradebot.veri.takvim import ms


def _bi5(kayitlar):
    return lzma.compress(b"".join(struct.pack(">5if", *k) for k in kayitlar), format=lzma.FORMAT_ALONE)


def test_coz_olcek_ve_zaman():
    taban = ms(datetime(2026, 7, 1, tzinfo=UTC))
    df = bi5_coz(_bi5([(0, 135000, 135034, 134990, 135050, 12.5), (3600, 135034, 135100, 135000, 135120, 3.0)]), taban, 1e5)
    assert df["acilis_ms"].to_list() == [taban, taban + 3_600_000]
    r = df.row(0, named=True)
    assert (r["open"], r["high"], r["low"], r["close"], r["volume"]) == (1.35, 1.3505, 1.3499, 1.35034, 12.5)


def test_olcek_kurallari():
    assert olcek("USDJPY", "fx") == 1e3 and olcek("EURUSD", "fx") == 1e5 and olcek("USA500IDXUSD", "endeks") == 1e3


def test_bos_dosya_ve_kapali_saat():
    assert bi5_coz(b"", 0, 1e5).is_empty()
    cumartesi = ms(datetime(2026, 7, 11, 12, tzinfo=UTC))
    carsamba = ms(datetime(2026, 7, 8, 12, tzinfo=UTC))
    df = bi5_coz(_bi5([(0, 1, 1, 1, 1, 0.0), ((carsamba - cumartesi) // 1000, 1, 1, 1, 1, 0.0)]), cumartesi, 1)
    assert kapali_ayikla(df, "fx_24x5")["acilis_ms"].to_list() == [carsamba]


def test_aylar():
    from datetime import date
    assert aylar("2025-11", date(2026, 2, 15)) == [(2025, 11), (2025, 12), (2026, 1), (2026, 2)]
