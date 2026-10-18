"""Gece işi: kalite ve evren uzun Dukascopy adımından önce koşar; iki ayrı denetim kaydı."""
from sqlalchemy import create_engine, select

from tradebot.db import denetim_izi, metadata
from tradebot.veri import is_akisi


def test_gece_sirasi_ve_denetim(ayar, monkeypatch):
    m = create_engine(ayar.veritabani_url.get_secret_value())
    metadata.create_all(m)
    sira = []
    for ad in ("nasdaq", "alpaca", "binance", "yahoo", "mt5", "dukascopy", "kalite_hepsi", "evren_kur"):
        monkeypatch.setattr(is_akisi, ad, lambda *_a, _ad=ad, **_k: sira.append(_ad) or {})
    monkeypatch.setattr(is_akisi, "yahoo", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("yahoo düştü")))
    sonuc = is_akisi.gece(ayar, m, 1.0)
    assert sira == ["nasdaq", "alpaca", "binance", "mt5", "kalite_hepsi", "evren_kur", "dukascopy"]  # hata diğerlerini durdurmaz
    assert "hata" in sonuc["yahoo"]
    with m.connect() as b:
        olaylar = [r.olay for r in b.execute(select(denetim_izi).order_by(denetim_izi.c.id))]
    assert olaylar == ["gece_isi", "gece_isi_dukascopy"]


def test_telafi_yalniz_eski_gece_isinde(tmp_path):
    from datetime import UTC, datetime, timedelta

    from sqlalchemy import create_engine

    from tradebot import denetim
    from tradebot.db import metadata
    from tradebot.veri.is_akisi import telafi_gerekli
    m = create_engine(f"sqlite:///{tmp_path / 't.db'}")
    metadata.create_all(m)
    simdi = datetime(2026, 9, 28, 12, tzinfo=UTC)
    assert telafi_gerekli(m, simdi)                                            # hiç yok
    denetim.kaydet(m, "veri", "gece_isi", {}, zaman=simdi - timedelta(hours=3))
    assert not telafi_gerekli(m, simdi)                                        # dağıtım sonrası: koşma
    assert telafi_gerekli(m, simdi + timedelta(hours=21))                      # kesinti sonrası: telafi


def test_gece_adimlari_ayarla_kisilir(ayar, monkeypatch):
    m = create_engine(ayar.veritabani_url.get_secret_value())
    metadata.create_all(m)
    sira = []
    for ad in ("nasdaq", "alpaca", "binance", "yahoo", "mt5", "dukascopy", "kalite_hepsi", "evren_kur"):
        monkeypatch.setattr(is_akisi, ad, lambda *_a, _ad=ad, **_k: sira.append(_ad) or {})
    a = ayar.model_copy(update={"gece_adimlari": ("nasdaq", "kalite", "evren")})
    sonuc = is_akisi.gece(a, m, 1.0)
    assert sira == ["nasdaq", "kalite_hepsi", "evren_kur"] and "dukascopy" not in sonuc
