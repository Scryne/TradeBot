"""Döviz taşıma kolu MT5 demo düğümü (canli/doviz.py): karar, emir yolu, para uzayı defteri, tahakkuk, durdurma,
yeniden başlatma. MT5 köprüsü sahte (davranışı tests/test_mt5.py'deki köprüyle aynı sözleşme)."""
from datetime import UTC, datetime

import numpy as np
import polars as pl
import pytest
from sqlalchemy import create_engine, select

from tradebot.canli import doviz as dv
from tradebot.canli.defter import PaperDefter
from tradebot.db import metadata, paper_emir, paper_emir_olay, paper_karar
from tradebot.mt5.istemci import SEMA
from tradebot.veri import faiz as fz

G = 86_400_000
S = 3_600_000
FARK = 3 * S
D0 = 1_790_640_000_000 // G * G            # Salı 00:00 UTC
FAIZ = {"USA": 4.5, "EA20": 2.0, "GBR": 6.0, "JPN": 0.1, "AUS": 3.5, "CAN": 3.0, "CHE": 0.5}
BAS_FIYAT = {"EURUSD": 1.10, "GBPUSD": 1.30, "USDJPY": 150.0, "AUDUSD": 0.66, "USDCAD": 1.36, "USDCHF": 0.80}


class Saat:
    def __init__(self, ms):
        self.ms = ms

    def __call__(self):
        return self.ms / 1000


def faiz_csv() -> bytes:
    satir = ["REF_AREA,MEASURE,TIME_PERIOD,OBS_VALUE"]
    for y in range(2023, 2027):
        for a in range(1, 13):
            satir += [f"{u},IR3TIB,{y}-{a:02d},{v}" for u, v in FAIZ.items()]
    return "\n".join(satir).encode()


class SahteKopru:
    """Mt5Istemci sözleşmesi: saglik, semboller, mumlar (D1, kapanmış, sunucu gece yarısı = 21:00 UTC), kotasyon,
    pozisyonlar, islemler, emir (hedging yok: net)."""

    def __init__(self, saat):
        self.saat = saat
        rng = np.random.default_rng(4)
        self.gunler = [d for d in range(D0 - 700 * G, D0 + 30 * G, G) if ((d // G) + 3) % 7 < 5]
        self.kapanis = {s: p * np.exp(np.cumsum(rng.normal(0, 0.004, len(self.gunler))))
                        for s, p in BAS_FIYAT.items()}
        self.poz: dict[str, float] = {}
        self.islem_gecmisi: list[dict] = []
        self.emirler: list[tuple] = []
        self.bilet = 0

    def _simdi(self):
        return int(self.saat() * 1000)

    def fiyat(self, s):
        i = max(j for j, d in enumerate(self.gunler) if d - FARK <= self._simdi())
        return float(self.kapanis[s][i])

    def saglik(self):
        return {"fark_sn": FARK // 1000}

    def semboller(self, adlar):
        return {a: {"point": 0.001 if "JPY" in a else 0.00001} for a in adlar}

    def mumlar(self, sembol, zd, bas_ms, bit_ms):
        assert zd == "D1"
        satir = []
        for i, d in enumerate(self.gunler):
            acilis = d - FARK
            if bas_ms <= acilis < bit_ms and acilis + G <= self._simdi():
                c = float(self.kapanis[sembol][i])
                satir.append([acilis, c, c * 1.002, c * 0.998, c, 100, 10, 0])
        return pl.DataFrame(satir, schema=SEMA, orient="row")

    def kotasyon(self, semboller):
        return {"kotasyon": {s: {"bid": self.fiyat(s) * 0.99995, "ask": self.fiyat(s) * 1.00005,
                                 "tik_ms": self._simdi() - 1000} for s in semboller}}

    def pozisyonlar(self, magic):
        return [{"sembol": s, "hacim": v} for s, v in self.poz.items() if abs(v) > 1e-9]

    def islemler(self, magic, bas_ms):
        return [x for x in self.islem_gecmisi if x["zaman_ms"] >= bas_ms]

    def emir(self, sembol, hacim, yorum, magic, sapma=20, sl_mesafe=None):
        self.sl = getattr(self, "sl", []) + [sl_mesafe]
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
    m = create_engine(f"sqlite:///{tmp_path / 'd.db'}")
    metadata.create_all(m)
    saat = Saat(D0 + 6 * S + 30 * 60_000)           # Salı 06:30: karar saati gelmedi
    kopru = SahteKopru(saat)
    d = dv.DovizDugumu(PaperDefter(m, "test"), dv.ayarlar(), dv.Kaynak(kopru, faiz_csv), saat=saat)
    d.ac()
    return m, d, saat, kopru


def _net(m, kol):
    with m.connect() as b:
        rows = b.execute(select(paper_emir_olay.c.enstruman, paper_emir_olay.c.miktar)
                         .where(paper_emir_olay.c.kol == kol, paper_emir_olay.c.tur == "dolum")).all()
    out: dict[str, float] = {}
    for k, q in rows:
        out[k] = out.get(k, 0.0) + q
    return {k: v for k, v in out.items() if abs(v) > 1e-6}


def test_ayarlar_ve_para_donusumu():
    ay = dv.ayarlar()
    assert ay.kol.ad == "d9:doviz_tasima@g10_doviz@1d" and ay.kol.grup["dugum"] == "doviz"
    assert ay.risk.kaldirac == 1.0 and ay.parametre == {"n": 1}
    jpy = next(p for p in ay.paralar if p.para == "JPY")
    assert jpy.sembol == "USDJPY" and jpy.yon == -1.0 and jpy.usd(150.0) == pytest.approx(1 / 150)
    assert jpy.lot_para(0.10, 150.0) == pytest.approx(-1_500_000)          # 10.000 USD uzun = 1,5 mn JPY kısa
    assert jpy.para_lot(-1_500_000, 150.0) == pytest.approx(0.10)
    assert dv._adima(0.0449, 0.01) == 0.04 and dv._adima(-0.0451, 0.01) == -0.05
    assert dv._adima(0.0499, 0.01, asagi=True) == 0.04


def test_karar_backtest_fonksiyonuyla_ayni():
    """Canlı hedef, backtest'in panel yoluyla (turnuva.hedef_uret) aynı: taşıma n=1 → en yüksek faizli para (GBP)
    uzun, en düşük (JPY) kısa; enstrüman tavanı 0,5."""
    ay = dv.ayarlar()
    k = SahteKopru(Saat(D0 + 8 * S))
    barlar = dv.Kaynak(k, faiz_csv).gunluk(ay.paralar, D0 + 8 * S)
    assert all(df["acilis_ms"].max() == D0 - G for df in barlar.values())      # son kapanmış seans: Pazartesi
    t, close, tas, ev = dv.seriler(barlar, ay.paralar, fz.coz(faiz_csv()))
    h = dv.hedef_agirlik(ay, t, close, tas, ev)
    para = dict(zip([p.para for p in ay.paralar], h * np.array([p.yon for p in ay.paralar]), strict=True))
    assert para["GBP"] > 0 and para["JPY"] < 0
    assert all(abs(v) < 1e-12 for c, v in para.items() if c not in ("GBP", "JPY"))
    assert np.all(np.abs(h) <= 0.5 + 1e-12) and np.abs(h).sum() <= 1.0 + 1e-9
    np.testing.assert_allclose(tas[-1], [0.02 - 0.045, 0.06 - 0.045, 0.045 - 0.001, 0.035 - 0.045, 0.045 - 0.03,
                                         0.045 - 0.005])


def test_gunluk_karar_emir_dolum_ve_tekillik(kur):
    m, d, saat, kopru = kur
    r = d.tur()
    assert "karar" not in r and "isaret" in r                               # 06:30: yalnız işaret
    saat.ms = D0 + 7 * S + 60_000
    r = d.tur()
    assert r["karar"]["dolum"] == 2 and not r["karar"]["ret"]
    semboller = sorted(e[0] for e in kopru.emirler)
    assert semboller == ["GBPUSD", "USDJPY"]
    assert kopru.poz["GBPUSD"] > 0 and kopru.poz["USDJPY"] > 0              # GBP uzun, JPY kısa (USDJPY alış)
    net = _net(m, d.kol.ad)
    assert set(net) == {"PARA:GBP", "PARA:JPY"} and net["PARA:GBP"] > 0 and net["PARA:JPY"] < 0
    fiyat, _ = d._fiyatlar()
    oz = d._d().ozkaynak(fiyat)
    for kim in net:                                                         # her bacak ~ özkaynağın yarısı
        assert 0.35 < abs(net[kim] * fiyat[kim]) / oz <= 0.5 + 0.02
    with m.connect() as b:
        k = b.execute(select(paper_karar.c.bar_ms, paper_karar.c.ayrinti)).one()
        e = b.execute(select(paper_emir.c.istemci_emir_id, paper_emir.c.risk)).all()
        dol = b.execute(select(paper_emir_olay.c.fiyat, paper_emir_olay.c.ayrinti)
                        .where(paper_emir_olay.c.tur == "dolum")).all()
    assert k.bar_ms == D0 and k.ayrinti["son_bar_ms"] == D0 - G
    assert all(x.risk["onay"] for x in e) and all(len(x.istemci_emir_id) <= 31 for x in e)
    for f, ay in dol:                                                       # 1 bps aleyhe
        u = ay["usd_fiyat_mt5"]
        assert f == pytest.approx(u * (1.0001 if ay["mt5"][0]["lot"] > 0 and ay["sembol"] == "GBPUSD" else 0.9999))
    n = len(kopru.emirler)
    saat.ms += 10 * 60_000
    assert "karar" not in d.tur() and len(kopru.emirler) == n              # aynı gün ikinci karar yok
    saat.ms = D0 + 4 * G + 8 * S                                             # Cumartesi
    assert "karar" not in d.tur()


def test_saatlik_isaret_tahakkuk_ve_mutabakat(kur):
    m, d, saat, kopru = kur
    saat.ms = D0 + 7 * S + 60_000
    d.tur()
    saat.ms = D0 + 8 * S + 1000
    r = d.tur()["isaret"]
    assert r["mutabakat"] == {"tamam": True}
    assert r["fonlama"] > 0                        # GBP (+%1,5) uzun, JPY (−%4,4) kısa: taşıma > kurum payı
    with m.connect() as b:
        fon = b.execute(select(paper_emir_olay.c.enstruman, paper_emir_olay.c.ucret, paper_emir_olay.c.ayrinti)
                        .where(paper_emir_olay.c.tur == "fonlama")).all()
    assert {f.enstruman for f in fon} == {"PARA:GBP", "PARA:JPY"}
    for f in fon:
        ay = f.ayrinti
        dt = (ay["bit_ms"] - ay["bas_ms"]) / dv.YIL_MS
        beklenen = ay["deger_usd"] * (ay["r_para"] - ay["r_usd"]) * dt - abs(ay["deger_usd"]) * 0.01 * dt
        assert -f.ucret == pytest.approx(beklenen)
    kopru.poz["EURUSD"] = 0.02                     # elle açılmış (defterde yok): fark raporlanır, dokunulmaz
    saat.ms = D0 + 9 * S + 1000
    assert d.tur()["isaret"]["mutabakat"]["fark"] == {"EURUSD": {"defter": 0.0, "mt5": 0.02}}
    assert kopru.poz["EURUSD"] == 0.02


def test_durdurma_kapatir_ve_jpy_bakiyesi_cevrilir(kur):
    m, d, saat, kopru = kur
    saat.ms = D0 + 7 * S + 60_000
    d.tur()
    d.defter.kol_olay_yaz(d.kol.ad, "durdur", {"neden": "telegram"})
    saat.ms = D0 + 8 * S + 1000
    r = d.tur()["isaret"]
    assert r["kapatilan"]["dolum"] == 2
    assert all(abs(v) < 1e-9 for v in kopru.poz.values())
    assert _net(m, d.kol.ad) == {}                  # USDJPY kapanınca JPY bakiyesi USD'ye çevrildi
    assert d._d().lot == {}
    saat.ms = D0 + G + 7 * S + 60_000               # ertesi gün: durdurulmuş kol pozisyon açmaz
    r = d.tur()
    assert r["karar"]["dolum"] == 0 and all(abs(v) < 1e-9 for v in kopru.poz.values())


def test_yeniden_baslatmada_mt5_islemi_kurtarilir(kur):
    m, d, saat, kopru = kur
    saat.ms = D0 + 7 * S + 60_000
    gercek = d._dolum_yaz
    d._dolum_yaz = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("süreç öldü"))
    with pytest.raises(RuntimeError):
        d.tur()
    assert len(kopru.emirler) == 1 and _net(m, d.kol.ad) == {}             # emir gitti, dolum yazılamadı
    d._dolum_yaz = gercek
    saat.ms += 60_000
    r = d.tur()
    assert r["devam"] == {"kurtarilan": 1, "bulunamayan": 0}
    assert len(kopru.emirler) == 1                                          # çift emir yok
    net = _net(m, d.kol.ad)
    assert len(net) == 1 and d._d().lot == {kopru.emirler[0][0]: kopru.emirler[0][1]}


def test_sabitler():
    assert datetime.fromtimestamp(D0 / 1000, UTC).weekday() == 1           # D0 Salı


def test_elle_kapatma_benimsenir_ve_jpy_bakiyesi_cevrilir(kur):
    m, d, saat, kopru = kur
    saat.ms = D0 + 7 * S + 60_000
    d.tur()
    assert kopru.sl and all(x and x > 0 for x in kopru.sl)             # her yeni pozisyona acil stop
    lot = kopru.poz["USDJPY"]
    kopru.poz["USDJPY"] = 0.0                                           # telefondan elle kapatıldı (sihirli sayı 0)
    kopru.bilet += 1
    kopru.islem_gecmisi.append({"bilet": kopru.bilet, "sembol": "USDJPY", "hacim": -lot, "fiyat": kopru.fiyat("USDJPY"),
                                "yorum": "", "zaman_ms": saat.ms, "neden": 1, "magic": 0})
    saat.ms = D0 + 8 * S + 1000
    r = d.tur()["isaret"]
    assert r["benimsenen"] == 1 and r["mutabakat"] == {"tamam": True}
    durum = d._d()
    assert "USDJPY" not in durum.lot and "PARA:JPY" not in durum.adet   # JPY bakiyesi USD'ye çevrildi
