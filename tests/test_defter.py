import pytest

from tradebot.arastirma import defter as df
from tradebot.db import metadata, motor


@pytest.fixture
def d(ayar, monkeypatch):
    e = motor(ayar)
    metadata.create_all(e)
    monkeypatch.setattr(df, "kod_surumu", lambda: "abc1234")
    return df.Defter(e)


def _kaydet(d, plan="p1", aile="trend", **k):
    return d.kaydet(plan=plan, tur="tarama", strateji="trend/sma(h=10)", aile=aile, parametreler={"h": 10},
                    enstruman="BINANCE:BTCUSDT", zaman_dilimi="1d", veri_hash="0" * 64, metrik={"sharpe": 0.5},
                    sure_sn=0.1, **k)


def test_plansiz_kosu_reddedilir(d):
    with pytest.raises(ValueError, match="test planı yok"):
        _kaydet(d)


def test_plan_ve_sayim(d):
    d.plan_ac("p1", "trend", "trend kriptoda maliyet sonrası pozitif", {"h": [10, 20]}, ["BINANCE:BTCUSDT"], "puan > 0")
    _kaydet(d)
    _kaydet(d)
    assert d.deneme_sayisi("trend") == 2 and d.deneme_sayisi("donus") == 0
    assert d.aile_puanlari("trend") == [0.5, 0.5]
    with pytest.raises(ValueError, match="zaten var"):
        d.plan_ac("p1", "trend", "x", {}, [], "x")


def test_kapali_plana_kayit_yok(d):
    d.plan_ac("p2", "trend", "h", {}, [], "o")
    d.plan_kapat("p2", "FAIL")
    with pytest.raises(ValueError, match="kapalı"):
        _kaydet(d, plan="p2")


def test_kirli_kod_reddedilir(ayar, monkeypatch):
    e = motor(ayar)
    metadata.create_all(e)
    monkeypatch.setattr(df, "kod_surumu", lambda: "abc1234-kirli")
    d = df.Defter(e)
    with pytest.raises(RuntimeError, match="commit"):
        d.plan_ac("p3", "trend", "h", {}, [], "o")
    d.plan_ac("p3", "trend", "h", {}, [], "o", izin_kirli=True)
    with pytest.raises(RuntimeError, match="commit"):
        _kaydet(d, plan="p3")
    assert _kaydet(d, plan="p3", izin_kirli=True) > 0


def test_kod_surumu_gercek_repo():
    s = df.kod_surumu.__wrapped__() if hasattr(df.kod_surumu, "__wrapped__") else df.kod_surumu()
    assert len(s.split("-")[0]) >= 7
