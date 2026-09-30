"""Dalga 10: döviz akış ve olay primleri (cekirdek/doviz_akis.py)."""
from datetime import UTC, datetime

import numpy as np
import pytest

from tradebot.arastirma import turnuva as tv
from tradebot.cekirdek import aileler as al
from tradebot.cekirdek import doviz_akis as da

SAAT, GUN = 3_600_000, 86_400_000
PARALAR = ("EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD")
YON = np.array([1.0, 1.0, -1.0, 1.0, -1.0, -1.0, 1.0])


def ms(s: str) -> int:
    return int(datetime.fromisoformat(s).replace(tzinfo=UTC).timestamp() * 1000)


def saatlik_panel(bas: str, gun: int, tohum: int = 0) -> al.Panel:
    t = ms(bas) + np.arange(gun * 24, dtype=np.int64) * SAAT
    rng = np.random.default_rng(tohum)
    c = np.exp(np.cumsum(rng.normal(0, 0.001, (len(t), 7)), axis=0))
    return al.Panel(t, c, np.ones((len(t), 7), dtype=bool), None, YON, PARALAR)


@pytest.fixture(autouse=True)
def _dis_veri():
    da.fomc_ayarla([ms("2024-01-31"), ms("2024-03-20")])
    gun = ms("2023-12-01") + np.arange(150, dtype=np.int64) * GUN
    usd = np.exp(np.linspace(0, 0.3, 150))        # ABD endeksi sürekli yükseliyor
    yabanci = np.exp(np.linspace(0, -0.3, 150))   # yabancı endeksler düşüyor
    da.endeks_ayarla({"USD": (gun, usd), "EUR": (gun, yabanci), "GBP": (gun, yabanci), "JPY": (gun, usd * 1.0)})
    yield
    da.fomc_ayarla([])
    da.endeks_ayarla({})


def tutulan(p: al.Panel, w: np.ndarray) -> np.ndarray:
    """Pozisyonun TUTULDUĞU barların açılışları (out[t] bar t+1'de tutulur)."""
    aktif = np.abs(w).sum(axis=1) > 0
    return p.t[np.flatnonzero(aktif)] + SAAT


@pytest.mark.parametrize("fonk,param", [
    (da.fomc_dolar, {"pencere": "gun"}), (da.fomc_dolar, {"pencere": "iki"}), (da.fomc_dolar, {"pencere": "on"}),
    (da.ay_sonu_hedge, {"gun": 1, "olcut": "sepet"}), (da.ay_sonu_hedge, {"gun": 2, "olcut": "kendi"}),
    (da.seans_para, {"tur": "abd"}), (da.seans_para, {"tur": "tam"}),
])
def test_nedensel(fonk, param):
    p = saatlik_panel("2024-01-02", 100)
    al.panel_nedensellik_testi(fonk, p, deneme=10, **param)
    assert np.abs(fonk(p, **param)).sum() > 0


def test_fomc_penceresi_saatleri():
    p = saatlik_panel("2024-01-25", 10)
    w = da.fomc_dolar(p, pencere="gun")
    t = tutulan(p, w)
    assert t[0] == ms("2024-01-30T21:00") and t[-1] == ms("2024-01-31T20:00") and len(t) == 24
    np.testing.assert_allclose(w[np.flatnonzero(np.abs(w).sum(axis=1))[0]] * YON, np.full(7, 1 / 7))  # USD kısa
    t = tutulan(p, da.fomc_dolar(p, pencere="on"))
    assert t[0] == ms("2024-01-30T21:00") and t[-1] == ms("2024-01-31T15:00")
    t = tutulan(p, da.fomc_dolar(p, pencere="iki"))
    assert t[-1] == ms("2024-02-01T20:00") and len(t) == 48


def test_fixing_yaz_saati():
    g = np.array(["2024-03-29", "2024-04-30", "2024-10-31", "2024-12-31"], dtype="datetime64[D]")
    saat = (da.fixing_ms(g) % GUN) // SAAT
    # 2024: yaz saati 31 Mart – 27 Ekim → Mart 29 kış (16), Nisan yaz (15), 31 Ekim kış (16)
    np.testing.assert_array_equal(saat, [16, 15, 16, 16])


def test_ay_sonu_penceresi_ve_yon():
    p = saatlik_panel("2024-01-20", 20)
    w = da.ay_sonu_hedge(p, gun=1, olcut="sepet")
    t = tutulan(p, w)
    # Ocak 2024'ün son iş günü 31 Ocak Çarşamba; kış: fixing 16:00 UTC
    assert t[0] == ms("2024-01-31T00:00") and t[-1] == ms("2024-01-31T15:00")
    # ABD endeksi, EUR/GBP/JPY ortalamasından iyi → yabancı paralar uzun
    i = np.flatnonzero(np.abs(w).sum(axis=1))[0]
    np.testing.assert_allclose(w[i] * YON, np.full(7, 1 / 7))
    t2 = tutulan(p, da.ay_sonu_hedge(p, gun=2))
    assert t2[0] == ms("2024-01-30T00:00")
    # Şubat 2024: son iş günü 29 Şubat Perşembe
    p = saatlik_panel("2024-02-20", 15)
    t = tutulan(p, da.ay_sonu_hedge(p, gun=2))
    assert t[0] == ms("2024-02-28T00:00") and t[-1] == ms("2024-02-29T15:00")


def test_ay_sonu_kendi_olcut():
    p = saatlik_panel("2024-01-25", 10)
    w = da.ay_sonu_hedge(p, gun=1, olcut="kendi")
    i = np.flatnonzero(np.abs(w).sum(axis=1))[0]
    para = w[i] * YON
    # EUR, GBP: ABD daha iyi → uzun; JPY endeksi ABD ile aynı → fark 0 → pozisyon yok; diğerleri kapsam dışı
    np.testing.assert_allclose(para, [1 / 3, 1 / 3, 0, 0, 0, 0, 0])


def test_ay_sonu_hafta_sonu_ay_sonu():
    # Mart 2024 31'i Pazar → son iş günü 29 Mart Cuma; ikinci son 28 Mart
    g = np.array(["2024-03-31", "2024-06-30", "2024-08-31"], dtype="datetime64[D]")
    assert list(da._son_is_gunu(g, 1).astype(str)) == ["2024-03-29", "2024-06-28", "2024-08-30"]
    assert list(da._son_is_gunu(g, 2).astype(str)) == ["2024-03-28", "2024-06-27", "2024-08-29"]


def test_seans_saatleri():
    p = saatlik_panel("2024-01-02", 2)
    w = da.seans_para(p, tur="tam") * YON[None, :]
    saat = ((p.t + SAAT) % GUN) // SAAT
    eur, jpy, cad = w[:, 0], w[:, 2], w[:, 4]
    assert np.all(eur[(saat >= 13) & (saat < 21)] > 0) and np.all(eur[(saat >= 7) & (saat < 13)] < 0)
    assert np.all(jpy[saat < 7] < 0) and np.all(jpy[(saat >= 7) & (saat < 13)] == 0)
    assert np.all(cad == 0)
    assert np.all(eur[(saat >= 21) | (saat < 7)] == 0)
    w = da.seans_para(p, tur="abd") * YON[None, :]
    assert np.all(w[(saat >= 7) & (saat < 13)] == 0)
    np.testing.assert_allclose(w[np.flatnonzero(saat == 14)[0]], [1 / 6, 1 / 6, 1 / 6, 1 / 6, 0, 1 / 6, 1 / 6])


def test_para_bilgisi_ve_fomc_takvimi():
    yon, ad = tv.para_bilgisi(["DUKASCOPY:EURUSD", "DUKASCOPY:USDJPY", "DUKASCOPY:NZDUSD"])
    np.testing.assert_array_equal(yon, [1, -1, 1])
    assert ad == ("EUR", "JPY", "NZD")
    with pytest.raises(ValueError):
        tv.para_bilgisi(["DUKASCOPY:EURGBP"])
    g = tv.fomc_gunleri(tv.Path("config/fomc_planli.yaml"))
    assert len(g) == len(set(g)) and g == sorted(g)
    assert ms("2020-03-18") not in g and ms("2020-03-15") not in g   # iptal edilen planlı ve olağanüstü toplantı
    assert ms("2024-01-31") in g
    yillar = [datetime.fromtimestamp(x / 1000, UTC).year for x in g]
    assert all(yillar.count(y) == 8 for y in range(2010, 2026) if y != 2020)
