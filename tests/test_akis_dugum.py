"""FOMC günü dolar kolu MT5 demo düğümü (canli/akis.py): takvim penceresi, bir bar gecikme, emir yolu, kapanış,
spread bekleme, finansman. MT5 köprüsü sahte (tests/test_doviz_dugum.py ile aynı sözleşme, H1)."""
from datetime import UTC, datetime

import numpy as np
import polars as pl
import pytest
from sqlalchemy import create_engine, select

from tradebot.arastirma.turnuva import Ayar, hedef_uret
from tradebot.canli import akis as ak
from tradebot.canli.defter import PaperDefter
from tradebot.db import metadata, paper_emir_olay, paper_karar
from tradebot.mt5.istemci import SEMA

S = 3_600_000
G = 86_400_000
FARK = 3 * S
FOMC = int(datetime(2026, 10, 28, tzinfo=UTC).timestamp() * 1000)       # Çarşamba (config/fomc_planli.yaml)
BAS = {"EURUSD": 1.10, "GBPUSD": 1.30, "USDJPY": 150.0, "AUDUSD": 0.66, "USDCAD": 1.36, "USDCHF": 0.80,
       "NZDUSD": 0.60}


class Saat:
    def __init__(self, ms):
        self.ms = ms

    def __call__(self):
        return self.ms / 1000


class SahteKopru:
    def __init__(self, saat):
        self.saat = saat
        rng = np.random.default_rng(7)
        self.t = np.array([x for x in range(FOMC - 260 * G, FOMC + 10 * G, S) if ((x // G) + 3) % 7 < 5],
                          dtype=np.int64)
        self.kapanis = {s: p * np.exp(np.cumsum(rng.normal(0, 0.001, len(self.t)))) for s, p in BAS.items()}
        self.poz: dict[str, float] = {}
        self.islem_gecmisi: list[dict] = []
        self.emirler: list[tuple] = []
        self.bilet = 0
        self.spread_bps = 1.0

    def _simdi(self):
        return int(self.saat() * 1000)

    def fiyat(self, s):
        i = int(np.searchsorted(self.t, self._simdi(), side="right")) - 1
        return float(self.kapanis[s][i])

    def saglik(self):
        return {"fark_sn": FARK // 1000}

    def semboller(self, adlar):
        return {a: {"point": 0.001 if "JPY" in a else 0.00001} for a in adlar}

    def mumlar(self, sembol, zd, bas_ms, bit_ms):
        assert zd == "H1"
        m = (self.t >= bas_ms) & (self.t < bit_ms) & (self.t + S <= self._simdi())
        c = self.kapanis[sembol][m]
        satir = [[int(t), float(x), float(x) * 1.0005, float(x) * 0.9995, float(x), 100, 10, 0]
                 for t, x in zip(self.t[m], c, strict=True)]
        return pl.DataFrame(satir, schema=SEMA, orient="row")

    def kotasyon(self, semboller):
        y = self.spread_bps / 2e4
        return {"kotasyon": {s: {"bid": self.fiyat(s) * (1 - y), "ask": self.fiyat(s) * (1 + y),
                                 "tik_ms": self._simdi() - 1000} for s in semboller}}

    def pozisyonlar(self, magic):
        assert magic == 911
        return [{"sembol": s, "hacim": v} for s, v in self.poz.items() if abs(v) > 1e-9]

    def islemler(self, magic, bas_ms):
        return [x for x in self.islem_gecmisi if x["zaman_ms"] >= bas_ms]

    def emir(self, sembol, hacim, yorum, magic, sapma=20, sl_mesafe=None):
        assert magic == 911 and yorum.startswith("AK") and sl_mesafe and sl_mesafe > 0
        self.emirler.append((sembol, hacim, yorum))
        self.bilet += 1
        px = self.fiyat(sembol) * (1.00005 if hacim > 0 else 0.99995)
        self.poz[sembol] = round(self.poz.get(sembol, 0.0) + hacim, 8)
        self.islem_gecmisi.append({"bilet": self.bilet, "sembol": sembol, "hacim": hacim, "fiyat": px, "yorum": yorum,
                                   "zaman_ms": self._simdi()})
        return {"sonuc": [{"lot": hacim, "hacim": abs(hacim), "fiyat": px, "retcode": 10009, "islem": self.bilet,
                           "yorum_mt5": "Request executed"}], "hedging": False}


@pytest.fixture()
def kur(tmp_path):
    m = create_engine(f"sqlite:///{tmp_path / 'a.db'}")
    metadata.create_all(m)
    saat = Saat(FOMC - 5 * G + 10 * S + 60_000)         # önceki Cuma 10:01: pencere dışı
    kopru = SahteKopru(saat)
    d = ak.AkisDugumu(PaperDefter(m, "test"), ak.ayarlar(), ak.Kaynak(kopru), saat=saat)
    d.ac()
    return m, d, saat, kopru


def _kararlar(m):
    with m.connect() as b:
        return b.execute(select(paper_karar.c.bar_ms, paper_karar.c.ayrinti).order_by(paper_karar.c.id)).all()


def test_ayarlar():
    ay = ak.ayarlar()
    assert ay.kol.ad == "d10:fomc_dolar@g10_saatlik@1h" and ay.kol.grup["dugum"] == "akis"
    assert ay.magic == 911 and ay.gecikme_bar == 1 and ay.kurum_payi_yillik == 0.02 and ay.risk.kaldirac == 1.0
    assert [p.para for p in ay.paralar] == ["EUR", "GBP", "JPY", "AUD", "CAD", "CHF", "NZD"]
    assert FOMC in set(int(x) for x in ak.da._FOMC)
    assert not ak.sinyal_var(ay, FOMC - 3 * S)           # 21:00 başlayan bar: gecikmeyle henüz yok
    assert ak.sinyal_var(ay, FOMC - 2 * S)               # 22:00: pencere (bir bar geç)
    assert ak.sinyal_var(ay, FOMC + 21 * S) and not ak.sinyal_var(ay, FOMC + 22 * S)


def test_hedef_backtest_yoluyla_ayni():
    """Canlı hedef dizisi, turnuva.hedef_uret'in panel yoluyla birebir aynı (kural 3)."""
    ay = ak.ayarlar()
    k = SahteKopru(Saat(FOMC + 2 * S))
    barlar = ak.Kaynak(k).saatlik(ay.paralar, FOMC + 2 * S)
    t, close, ev = ak.izgara(barlar, ay.paralar, FOMC + S)
    canli = ak.hedefler(ay, t, close, ev)
    h = type("H", (), {})()
    g = type("G", (), {"t": t, "kapanis": close, "bar_ms": S, "barlar": []})()
    h.g, h.evrende, h.takvim, h.bar_yil_olcu = g, ev, "fx_24x5", None
    h.tasima, h.para_yon, h.paralar, h.yalniz_long = None, np.array([p.yon for p in ay.paralar]), \
        tuple(p.para for p in ay.paralar), None
    bt = hedef_uret(h, "fomc_dolar", {"pencere": "gun"}, "long_short",
                    Ayar(hedef_vol=0.10, kaldirac=1.0, vol_pencere_gun=90, bant=0.25), nedensellik=False)
    np.testing.assert_allclose(canli, bt)
    son = canli[-2] * np.array([p.yon for p in ay.paralar])          # pencere içinde: USD kısa, eşit sepet, brüt 1x
    np.testing.assert_allclose(son, np.full(7, 1 / 7), rtol=1e-9)


def test_pencere_emir_ve_kapanis(kur):
    m, d, saat, kopru = kur
    assert "karar" not in d.tur() and not _kararlar(m)                   # pencere dışında karar yazılmaz
    saat.ms = FOMC - 3 * S + 60_000                                      # Salı 21:01: gecikme, henüz yok
    assert "karar" not in d.tur() and not kopru.emirler
    saat.ms = FOMC - 2 * S + 60_000                                      # Salı 22:01: giriş
    r = d.tur()
    assert r["karar"]["dolum"] == 7 and not r["karar"]["ret"]
    for s, lot in kopru.poz.items():                                     # USD kısa: XXXUSD alış, USDXXX satış
        assert (lot > 0) == s.endswith("USD")
    fiyat, _ = d._fiyatlar()
    durum = d._d()
    oz = durum.ozkaynak(fiyat)
    brut = sum(abs(a * fiyat[k]) for k, a in durum.adet.items()) / oz
    assert 0.6 < brut <= 1.0 + 0.15           # 10.000 USD'de 0,01 lot ≈ 600–1.500 USD: yuvarlama kaba
    n = len(kopru.emirler)
    saat.ms = FOMC + 12 * S + 60_000                                     # pencere içi: bant içinde, yeni emir yok
    r = d.tur()
    assert r["karar"]["dolum"] == 0 and len(kopru.emirler) == n
    saat.ms = FOMC + 22 * S + 60_000                                     # Çarşamba 22:01: çıkış
    r = d.tur()
    assert r["karar"]["dolum"] == 7
    assert all(abs(v) < 1e-9 for v in kopru.poz.values())
    assert d._d().lot == {}
    saat.ms = FOMC + 23 * S + 60_000                                     # pozisyon ve sinyal yok: karar yazılmaz
    k = len(_kararlar(m))
    assert "karar" not in d.tur() and len(_kararlar(m)) == k


def test_genis_spreadde_bekler(kur):
    m, d, saat, kopru = kur
    kopru.spread_bps = 12.0
    saat.ms = FOMC - 2 * S + 60_000
    assert "karar" not in d.tur() and not kopru.emirler                  # devir spread'i: bekle
    saat.ms = FOMC - 2 * S + 31 * 60_000                                 # 30 dk sonra yine de yürüt
    r = d.tur()
    assert r["karar"]["dolum"] == 7
    assert _kararlar(m)[-1].ayrinti["genis_spread"]


def test_finansman_tasima_yok(kur):
    m, d, saat, kopru = kur
    saat.ms = FOMC - 2 * S + 60_000
    d.tur()
    saat.ms = FOMC - S + 1000
    r = d.tur()["isaret"]
    assert r["fonlama"] < 0 and r["mutabakat"] == {"tamam": True}
    with m.connect() as b:
        fon = b.execute(select(paper_emir_olay.c.ucret, paper_emir_olay.c.ayrinti)
                        .where(paper_emir_olay.c.tur == "fonlama")).all()
    assert len(fon) == 7
    for f in fon:
        ay = f.ayrinti
        dt = (ay["bit_ms"] - ay["bas_ms"]) / ak.dv.YIL_MS
        assert f.ucret == pytest.approx(abs(ay["deger_usd"]) * 0.02 * dt)


def test_durdurma_kapatir(kur):
    m, d, saat, kopru = kur
    saat.ms = FOMC - 2 * S + 60_000
    d.tur()
    d.defter.kol_olay_yaz(d.kol.ad, "durdur", {"neden": "telegram"})
    saat.ms = FOMC - S + 1000
    r = d.tur()
    assert r["isaret"]["kapatilan"]["dolum"] == 7
    assert all(abs(v) < 1e-9 for v in kopru.poz.values())
