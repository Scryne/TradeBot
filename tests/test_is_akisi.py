"""Gece işi: kalite ve evren uzun Dukascopy adımından önce koşar; iki ayrı denetim kaydı."""
from sqlalchemy import create_engine, select

from tradebot.db import denetim_izi, metadata
from tradebot.veri import is_akisi


def test_gece_sirasi_ve_denetim(ayar, monkeypatch):
    m = create_engine(ayar.veritabani_url.get_secret_value())
    metadata.create_all(m)
    sira = []
    for ad in ("binance", "yahoo", "dukascopy", "kalite_hepsi", "evren_kur"):
        monkeypatch.setattr(is_akisi, ad, lambda *_a, _ad=ad, **_k: sira.append(_ad) or {})
    monkeypatch.setattr(is_akisi, "yahoo", lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError("yahoo düştü")))
    sonuc = is_akisi.gece(ayar, m, 1.0)
    assert sira == ["binance", "kalite_hepsi", "evren_kur", "dukascopy"]  # hata diğerlerini durdurmaz
    assert "hata" in sonuc["yahoo"]
    with m.connect() as b:
        olaylar = [r.olay for r in b.execute(select(denetim_izi).order_by(denetim_izi.c.id))]
    assert olaylar == ["gece_isi", "gece_isi_dukascopy"]
