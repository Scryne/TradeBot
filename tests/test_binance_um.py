import io
import zipfile

from tradebot.veri.binance_um import metrics_zip_oku


def _zip(metin: str) -> bytes:
    b = io.BytesIO()
    with zipfile.ZipFile(b, "w") as z:
        z.writestr("x.csv", metin)
    return b.getvalue()


BASLIK = ("create_time,symbol,sum_open_interest,sum_open_interest_value,count_toptrader_long_short_ratio,"
          "sum_toptrader_long_short_ratio,count_long_short_ratio,sum_taker_long_short_vol_ratio\n")


def test_metrics_saatlik_son_deger():
    m = (BASLIK + '2022-01-01 00:00:00,BTCUSDT,10,100,"","","",""\n'
         + '2022-01-01 00:55:00,BTCUSDT,12,130,"","","",""\n'
         + '2022-01-01 01:00:00,BTCUSDT,9,90,1.2,1.1,1.0,0.9\n')
    df = metrics_zip_oku(_zip(m))
    assert df.to_dicts() == [{"acilis_ms": 1640995200000, "oi": 12.0, "oi_usdt": 130.0},
                             {"acilis_ms": 1640998800000, "oi": 9.0, "oi_usdt": 90.0}]


def test_metrics_bos():
    assert metrics_zip_oku(_zip(BASLIK)).is_empty()
