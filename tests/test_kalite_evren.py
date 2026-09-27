from datetime import UTC, datetime

import numpy as np
import polars as pl

from tradebot.veri import evren as ev
from tradebot.veri import kalite
from tradebot.veri.depo import BarDepo
from tradebot.veri.takvim import ms

SAAT, GUN = 3_600_000, 86_400_000


def _seri(t, fiyat=None, qv=1000.0):
    n = len(t)
    c = np.asarray(fiyat if fiyat is not None else np.linspace(100, 110, n), dtype=float)
    return pl.DataFrame({"acilis_ms": np.asarray(t, dtype=np.int64), "open": c, "high": c * 1.001, "low": c * 0.999,
                         "close": c, "volume": np.ones(n), "quote_volume": np.full(n, qv)})


def test_temiz_seri_ok():
    t0 = ms(datetime(2026, 1, 1, tzinfo=UTC))
    durum, o = kalite.rapor(_seri(np.arange(t0, t0 + 500 * SAAT, SAAT)), "1h", "kripto_7x24")
    assert durum == "OK" and o["eksik"] == 0 and o["ohlc_tutarsiz"] == 0


def test_eksik_bosluk_kimlik_kirilmasi_sicrama():
    t0 = ms(datetime(2022, 1, 1, tzinfo=UTC))
    a = np.arange(t0, t0 + 200 * SAAT, SAAT)
    b = np.arange(t0 + 60 * GUN, t0 + 60 * GUN + 200 * SAAT, SAAT)  # 58 günlük boşluk: yeni varlık şüphesi
    fiyat = np.r_[np.linspace(100, 101, 200), np.linspace(0.5, 0.6, 200)]  # LUNA benzeri
    durum, o = kalite.rapor(_seri(np.r_[a, b], fiyat), "1h", "kripto_7x24")
    assert durum == "UYARI" and o["kimlik_kirilmasi_supheli"] and o["eksik"] > 1000
    assert o["uzun_bosluk"][0]["gun"] > 50
    assert o["buyuk_hareket"] >= 1 and o["sicrama"] == 0  # kalıcı seviye kırılması kötü tick değil


def test_sicra_don_kotu_tick_uyari():
    t0 = ms(datetime(2026, 1, 1, tzinfo=UTC))
    t = np.arange(t0, t0 + 300 * SAAT, SAAT)
    fiyat = 100 * np.exp(np.cumsum(np.random.default_rng(1).normal(0, 0.003, 300)))
    fiyat[150] *= 1.3                                   # tek barlık kötü tick: sıçrar ve geri döner
    durum, o = kalite.rapor(_seri(t, fiyat), "1h", "kripto_7x24")
    assert durum == "UYARI" and o["sicrama"] == 1 and o["sicrama_ornek"][0]["donus"] < 0
    kalici = 100 * np.exp(np.cumsum(np.random.default_rng(1).normal(0, 0.003, 300)))
    kalici[150:] *= 1.3
    durum, o = kalite.rapor(_seri(t, kalici), "1h", "kripto_7x24")
    assert durum == "OK" and o["sicrama"] == 0 and o["buyuk_hareket"] == 1


def test_ohlc_tutarsiz_hata():
    t0 = ms(datetime(2026, 1, 1, tzinfo=UTC))
    df = _seri(np.arange(t0, t0 + 100 * SAAT, SAAT)).with_columns(
        pl.when(pl.col("acilis_ms") == t0 + 5 * SAAT).then(1.0).otherwise(pl.col("high")).alias("high"))
    durum, o = kalite.rapor(df, "1h", "kripto_7x24")
    assert durum == "HATA" and o["ohlc_tutarsiz"] == 1


def test_borsa_gunluk_tatil_eksik_sayilmaz():
    # BIST 2026-05-25..06-05: seans günleri; bayram günleri (27-29 Mayıs) eksik sayılmamalı
    gunler = [ms(datetime(2026, 5, d, tzinfo=UTC)) for d in (25, 26)]
    gunler += [ms(datetime(2026, 6, d, tzinfo=UTC)) for d in range(1, 6)]
    durum, o = kalite.rapor(_seri(gunler), "1d", "XIST")
    assert o["eksik"] == 0 and o["kapali_saatte_bar"] == 0


def test_evren_pit_listeleme_kaldirma_ve_likidite(tmp_path):
    d = BarDepo(tmp_path)
    t0 = ms(datetime(2024, 1, 1, tzinfo=UTC))
    d.yaz("X:ESKI", "1h", _seri(np.arange(t0, t0 + 10 * GUN, SAAT), qv=5000.0))         # 10. günde kaldırılıyor
    d.yaz("X:YENI", "1h", _seri(np.arange(t0 + 20 * GUN, t0 + 40 * GUN, SAAT), qv=100.0))  # 20. günde listeleniyor
    d.yaz("X:SUREKLI", "1h", _seri(np.arange(t0, t0 + 40 * GUN, SAAT), qv=1000.0))
    tb = ev.tablo_kur(d, ["X:ESKI", "X:YENI", "X:SUREKLI"], "1h", t0, t0 + 40 * GUN)
    assert ev.evren(tb, t0 + 5 * GUN) == ["X:ESKI", "X:SUREKLI"]          # ESKI daha likit
    assert ev.evren(tb, t0 + 15 * GUN) == ["X:SUREKLI"]                   # ESKI kaldırıldı, YENI henüz yok
    assert ev.evren(tb, t0 + 25 * GUN) == ["X:SUREKLI", "X:YENI"]
    assert ev.evren(tb, t0 + 25 * GUN, ilk_n=1) == ["X:SUREKLI"]


def test_evren_gelecegi_gormez(tmp_path):
    """t gününün likiditesi t'den sonraki barlar bozulsa da değişmez."""
    d = BarDepo(tmp_path)
    t0 = ms(datetime(2024, 1, 1, tzinfo=UTC))
    t = np.arange(t0, t0 + 30 * GUN, SAAT)
    d.yaz("X:A", "1h", _seri(t, qv=1000.0))
    once = ev.tablo_kur(d, ["X:A"], "1h", t0, t0 + 30 * GUN).filter(pl.col("gun") <= t0 + 15 * GUN)
    bozuk = _seri(t, qv=1000.0).with_columns(
        pl.when(pl.col("acilis_ms") > t0 + 16 * GUN).then(1e12).otherwise(pl.col("quote_volume")).alias("quote_volume"))
    d.yaz("X:A", "1h", bozuk, birlestir=False)
    sonra = ev.tablo_kur(d, ["X:A"], "1h", t0, t0 + 30 * GUN).filter(pl.col("gun") <= t0 + 15 * GUN)
    assert once.equals(sonra)


def test_sonraki_calisma():
    from tradebot.veri.is_akisi import sonraki_calisma
    assert sonraki_calisma(datetime(2026, 9, 25, 0, 10, tzinfo=UTC), 1, 30) == datetime(2026, 9, 25, 1, 30, tzinfo=UTC)
    assert sonraki_calisma(datetime(2026, 9, 25, 2, 0, tzinfo=UTC), 1, 30) == datetime(2026, 9, 26, 1, 30, tzinfo=UTC)


def test_borsanin_kendi_kaydinda_sicra_don_uyari_degil():
    t0 = ms(datetime(2026, 1, 1, tzinfo=UTC))
    t = np.arange(t0, t0 + 300 * SAAT, SAAT)
    fiyat = 100 * np.exp(np.cumsum(np.random.default_rng(1).normal(0, 0.003, 300)))
    fiyat[150] *= 1.3
    durum, o = kalite.rapor(_seri(t, fiyat), "1h", "kripto_7x24", sicrama_uyari=False)
    assert durum == "OK" and o["sicrama"] == 1  # sayılır, uyarı değil
