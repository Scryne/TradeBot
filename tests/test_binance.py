import io
import zipfile

from tradebot.veri.binance import funding_zip_oku, kline_zip_oku, zaman_birimi_ms


def _zip(metin: str) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("x.csv", metin)
    return b.getvalue()


SATIR_MS = "1704067200000,42283.58,42554.57,42261.02,42475.23,1271.68,1704070799999,54012345.1,52000,600.1,25500000.2,0\n"
SATIR_US = "1785542400000000,62887.88,62900.0,62887.87,62893.06,7.71,1785542459999999,485038.09,873,1.18,74456.29,0\n"


def test_birim_tespiti():
    assert zaman_birimi_ms(1704067200000) == 1
    assert zaman_birimi_ms(1785542400000000) == 1000


def test_ms_ve_us_ayni_olcege_iner():
    a = kline_zip_oku(_zip(SATIR_MS))
    b = kline_zip_oku(_zip(SATIR_US))
    assert a["acilis_ms"][0] == 1704067200000 and b["acilis_ms"][0] == 1785542400000
    assert a.columns == ["acilis_ms", "open", "high", "low", "close", "volume", "quote_volume", "trades"]


def test_baslik_satiri_atlanir():
    baslik = "open_time,open,high,low,close,volume,close_time,quote_volume,count,tb,tq,ignore\n"
    df = kline_zip_oku(_zip(baslik + SATIR_MS))
    assert len(df) == 1 and df["close"][0] == 42475.23


def test_funding():
    df = funding_zip_oku(_zip("calc_time,funding_interval_hours,last_funding_rate\n1704067200000,8,0.0001\n"))
    assert df.to_dicts() == [{"zaman_ms": 1704067200000, "oran": 0.0001, "aralik_saat": 8}]
