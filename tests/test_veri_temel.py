from datetime import UTC, datetime

import numpy as np
import polars as pl
import pytest

from tradebot.db import metadata, motor
from tradebot.veri import enstruman as en
from tradebot.veri.depo import BarDepo, HamDepo, sha256, turet
from tradebot.veri.takvim import ms, takvim

SAAT = 3_600_000


@pytest.fixture
def m(ayar):
    e = motor(ayar)
    metadata.create_all(e)
    return e


# --- takvim ---
def test_fx_hafta_sonu_kapali_ve_dst():
    fx = takvim("fx_24x5")
    # Kış (EST, UTC-5): Cuma 21:59 UTC açık, 22:00 kapalı; Pazar 21:59 kapalı, 22:00 açık
    assert fx.acik_mi(ms(datetime(2026, 1, 9, 21, 59, tzinfo=UTC)))
    assert not fx.acik_mi(ms(datetime(2026, 1, 9, 22, 0, tzinfo=UTC)))
    assert not fx.acik_mi(ms(datetime(2026, 1, 11, 21, 59, tzinfo=UTC)))
    assert fx.acik_mi(ms(datetime(2026, 1, 11, 22, 0, tzinfo=UTC)))
    # Yaz (EDT, UTC-4): Cuma 21:00 UTC kapanış
    assert not fx.acik_mi(ms(datetime(2026, 7, 10, 21, 0, tzinfo=UTC)))
    # Vektörel maske tekil kontrolle aynı
    t = np.arange(ms(datetime(2026, 7, 9, tzinfo=UTC)), ms(datetime(2026, 7, 14, tzinfo=UTC)), SAAT, dtype=np.int64)
    assert (fx.acik_maske(t) == np.array([fx.acik_mi(int(x)) for x in t])).all()


def test_fx_haftalik_bar_sayisi():
    bar = takvim("fx_24x5").beklenen_barlar("1h", ms(datetime(2026, 7, 5, tzinfo=UTC)), ms(datetime(2026, 7, 12, tzinfo=UTC)))
    assert len(bar) == 120  # 5 × 24 saat


def test_bist_seans_ve_tatil():
    b = takvim("XIST")
    assert b.acik_mi(ms(datetime(2026, 6, 2, 7, 0, tzinfo=UTC)))       # 10:00 TRT
    assert not b.acik_mi(ms(datetime(2026, 6, 2, 15, 0, tzinfo=UTC)))  # 18:00 TRT kapanış
    assert not b.acik_mi(ms(datetime(2026, 5, 28, 9, 0, tzinfo=UTC)))  # Kurban Bayramı
    gun = b.gunluk_barlar(ms(datetime(2026, 5, 25, tzinfo=UTC)), ms(datetime(2026, 6, 1, tzinfo=UTC)))
    assert [datetime.fromtimestamp(x / 1000, UTC).day for x in gun] == [25, 26]  # 26 yarım gün, 27-29 tatil


def test_nyse_seans():
    n = takvim("XNYS")
    assert n.acik_mi(ms(datetime(2026, 6, 2, 13, 30, tzinfo=UTC)))
    assert not n.acik_mi(ms(datetime(2026, 6, 2, 20, 0, tzinfo=UTC)))
    assert not n.acik_mi(ms(datetime(2026, 7, 3, 15, 0, tzinfo=UTC)))  # 4 Temmuz tatili (Cuma'ya kaydırılmış)


# --- ham depo ---
def test_ham_depo_degismez_ve_surumlu(m, ayar):
    d = HamDepo(ayar.veri_dizini, m)
    y1, h1, yeni1 = d.kaydet("test", "a/b", b"icerik-1", "json")
    y2, h2, yeni2 = d.kaydet("test", "a/b", b"icerik-1", "json")
    assert yeni1 and not yeni2 and y1 == y2 and h1 == h2 == sha256(b"icerik-1")
    y3, h3, yeni3 = d.kaydet("test", "a/b", b"icerik-2", "json")  # kaynak düzeltti: yeni sürüm, eski kalır
    assert yeni3 and y3 != y1 and y1.read_bytes() == b"icerik-1" and y3.read_bytes() == b"icerik-2"
    assert d.dosyalar("test") == [("a/b", y3, h3)]


def test_ham_depo_saglama(m, ayar):
    with pytest.raises(ValueError, match="sağlama"):
        HamDepo(ayar.veri_dizini, m).kaydet("test", "x", b"veri", "zip", beklenen_sha="0" * 64)


# --- bar depo ve türetme ---
def _bar(t0, n, fiyat=100.0):
    t = [t0 + i * SAAT for i in range(n)]
    return pl.DataFrame({"acilis_ms": t, "open": [fiyat + i for i in range(n)], "high": [fiyat + i + 2 for i in range(n)],
                         "low": [fiyat + i - 1 for i in range(n)], "close": [fiyat + i + 1 for i in range(n)],
                         "volume": [1.0] * n})


def test_bar_depo_birlestir_yeni_kazanir(ayar):
    d = BarDepo(ayar.veri_dizini)
    t0 = ms(datetime(2026, 1, 1, tzinfo=UTC))
    d.yaz("BINANCE:BTCUSDT", "1h", _bar(t0, 5))
    duzelt = _bar(t0 + 2 * SAAT, 5, fiyat=500.0)  # 2 bar çakışır, 3 yeni
    assert d.yaz("BINANCE:BTCUSDT", "1h", duzelt) == 7
    df = d.oku("BINANCE:BTCUSDT", "1h")
    assert df["acilis_ms"].is_sorted() and df.filter(pl.col("acilis_ms") == t0 + 2 * SAAT)["open"][0] == 500.0
    assert d.kimlikler("1h") == ["BINANCE:BTCUSDT"]


def test_turet_gunluk():
    t0 = ms(datetime(2026, 1, 1, tzinfo=UTC))
    g = turet(_bar(t0, 48), 86_400_000)
    assert len(g) == 2 and g["acilis_ms"].to_list() == [t0, t0 + 86_400_000]
    assert g["open"][0] == 100.0 and g["close"][0] == 124.0 and g["high"][0] == 125.0 and g["low"][0] == 99.0
    assert g["alt_bar"].to_list() == [24, 24]


# --- enstrüman kaydı ---
def test_evren_ve_kayit(m):
    e = en.evren_yukle()
    duk = en.dukascopy_enstrumanlari(e)
    kimlikler = {x.kimlik for x in duk}
    assert "DUKASCOPY:EURUSD" in kimlikler and "DUKASCOPY:DEUIDXEUR" in kimlikler
    assert next(x for x in duk if x.sembol == "DEUIDXEUR").para_birimi == "EUR"
    bist = en.bist_enstrumanlari(e, ["THYAO"])
    assert bist[-1].meta["kaynak_sembol"] == "THYAO.IS" and "evren_uyarisi" in bist[-1].meta
    n = en.kaydet(m, duk + en.abd_etf_enstrumanlari(e) + bist)
    en.kaydet(m, duk)  # ikinci kez: güncelleme, çift kayıt yok
    en.sinir_guncelle(m, "ARCA:SPY", 1, 2)
    satirlar = en.hepsi(m)
    assert len(satirlar) == n
    spy = next(r for r in satirlar if r["kimlik"] == "ARCA:SPY")
    assert spy["ilk_bar_ms"] == 1 and spy["takvim"] == "XNYS"
