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


def test_gunluk_yillik_dosya(ayar):
    import time as _t

    from tradebot.db import metadata, motor
    from tradebot.veri import enstruman as en
    from tradebot.veri.dukascopy import Dukascopy

    e = motor(ayar)
    metadata.create_all(e)
    d = Dukascopy(ayar.veri_dizini, e, evren={"dukascopy": {}}, aralik_sn=0)
    istenen = []

    def sahte_al(url, params=None):
        istenen.append(url)
        # 2024: Salı 2 Ocak ve Cumartesi 6 Ocak (hacimsiz → ayıklanır)
        return _bi5([(86400, 110000, 110100, 109900, 110200, 5.0), (5 * 86400, 1, 1, 1, 1, 0.0)])

    d.http.al = sahte_al
    ens = en.Enstruman("DUKASCOPY", "EURUSD", "fx", "fx_24x5", "USD", "dukascopy")
    r = d.gunluk(ens, "2024-01", _t.monotonic() + 60)
    assert istenen[0].endswith("EURUSD/2024/BID_candles_day_1.bi5") and r["yeni_dosya"] == len(istenen)
    df = d.bar.oku("DUKASCOPY:EURUSD", "1d")
    assert df["acilis_ms"].to_list()[0] == ms(datetime(2024, 1, 2, tzinfo=UTC))
    assert df["close"][0] == 1.101  # kayıt sırası: t, o, c, l, h, v
    assert ms(datetime(2024, 1, 6, tzinfo=UTC)) not in df["acilis_ms"].to_list()
    # tamamlanmış yıl yeniden istenmez
    n = len(istenen)
    d.gunluk(ens, "2024-01", _t.monotonic() + 60)
    assert len(istenen) == n + 1  # yalnız içinde bulunulan yıl yeniden


def test_gunluk_yarida_kesilse_de_kendini_onarir(ayar):
    import time as _t

    import pytest

    from tradebot.db import metadata, motor
    from tradebot.veri import enstruman as en
    from tradebot.veri.dukascopy import Dukascopy

    e = motor(ayar)
    metadata.create_all(e)
    d = Dukascopy(ayar.veri_dizini, e, evren={"dukascopy": {}}, aralik_sn=0)
    ens = en.Enstruman("DUKASCOPY", "EURUSD", "fx", "fx_24x5", "USD", "dukascopy")

    def yil_dosyasi(url):
        y = int(url.split("/")[-2])
        return _bi5([(86400, 100000 + y, 100000 + y, 100000 + y, 100000 + y, 1.0)])  # yılın 2. günü

    def bozuk(url, params=None):
        if "/2022/" in url:
            raise RuntimeError("503")
        return yil_dosyasi(url)

    d.http.al = bozuk
    with pytest.raises(RuntimeError):
        d.gunluk(ens, "2020-01", _t.monotonic() + 60)
    assert len(d.bar.oku("DUKASCOPY:EURUSD", "1d")) == 2  # 2020, 2021 yazıldı (kaybolmadı)
    istenen = []

    def saglam(url, params=None):
        istenen.append(url)
        return yil_dosyasi(url)

    d.http.al = saglam
    d.gunluk(ens, "2020-01", _t.monotonic() + 60)
    assert not any("/2020/" in u or "/2021/" in u for u in istenen)  # ham depodan okundu, yeniden istenmedi
    assert len(d.bar.oku("DUKASCOPY:EURUSD", "1d")) >= 3
