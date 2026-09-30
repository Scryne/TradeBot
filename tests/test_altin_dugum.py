"""Altın M15 scalping gözlem kolu (canli/altin.py): turnuva fonksiyonuyla birebir pozisyon yolu, emir yolu, ters dönüş,
piyasa kapalıyken karar yok, durdurma, yeniden başlatmada kurtarma. Ayrıca döviz kolunun hesap değişimi kapanışı."""
import numpy as np
import polars as pl
import pytest
from sqlalchemy import create_engine, select

from tradebot.canli import altin as ad
from tradebot.canli import doviz as dv
from tradebot.canli.defter import PaperDefter
from tradebot.cekirdek import altin as ca
from tradebot.db import metadata, paper_emir_olay, paper_karar
from tradebot.mt5.istemci import SEMA

G = 86_400_000
S = 3_600_000
B = ad.BAR_MS
T0 = 1_790_640_000_000 // G * G            # Salı 00:00 UTC


class Saat:
    def __init__(self, ms):
        self.ms = ms

    def __call__(self):
        return self.ms / 1000


class SahteKopru:
    def __init__(self, saat, n_gun=45, tohum=7):
        self.saat = saat
        rng = np.random.default_rng(tohum)
        self.t = np.arange(T0 - 35 * G, T0 + (n_gun - 35) * G, B, dtype=np.int64)
        self.c = 4600 * np.exp(np.cumsum(rng.normal(0, 0.0015, len(self.t))))
        self.kapali: tuple[int, int] | None = None          # (bas, bit): bu aralıkta bar yok (hafta sonu)
        self.poz = 0.0
        self.emirler: list[tuple] = []
        self.gecmis: list[dict] = []
        self.mumlar_cagri = 0

    def _simdi(self):
        return int(self.saat() * 1000)

    def _var(self):
        m = self.t + B <= self._simdi()
        if self.kapali:
            m &= ~((self.t >= self.kapali[0]) & (self.t < self.kapali[1]))
        return m

    def mumlar(self, sembol, zd, bas_ms, bit_ms):
        assert sembol == "GOLD" and zd == "M15"
        self.mumlar_cagri += 1
        m = self._var() & (self.t >= bas_ms) & (self.t < bit_ms)
        c = self.c[m]
        return pl.DataFrame({"acilis_ms": self.t[m], "open": c, "high": c * 1.0008, "low": c * 0.9992, "close": c,
                             "tick_volume": np.full(len(c), 10, dtype=np.int64), "spread": np.full(len(c), 20),
                             "real_volume": np.zeros(len(c), dtype=np.int64)}, schema=SEMA)

    def fiyat(self):
        i = np.searchsorted(self.t, self._simdi(), side="right") - 1
        return float(self.c[i])

    def kotasyon(self, semboller):
        p = self.fiyat()
        return {"kotasyon": {"GOLD": {"bid": p - 0.1, "ask": p + 0.1, "tik_ms": self._simdi() - 1000}}}

    def pozisyonlar(self, magic):
        return [{"sembol": "GOLD", "hacim": self.poz}] if abs(self.poz) > 1e-9 else []

    def islemler(self, magic, bas_ms):
        return [x for x in self.gecmis if x["zaman_ms"] >= bas_ms]

    def emir(self, sembol, hacim, yorum, magic, sapma=20):
        px = self.fiyat() + (0.1 if hacim > 0 else -0.1)
        self.emirler.append((hacim, yorum))
        self.poz = round(self.poz + hacim, 8)
        self.gecmis.append({"bilet": len(self.emirler), "sembol": sembol, "hacim": hacim, "fiyat": px, "yorum": yorum,
                            "zaman_ms": self._simdi()})
        return {"sonuc": [{"lot": hacim, "hacim": abs(hacim), "fiyat": px, "retcode": 10009,
                           "islem": len(self.emirler)}]}


@pytest.fixture()
def kur(tmp_path):
    m = create_engine(f"sqlite:///{tmp_path / 'a.db'}")
    metadata.create_all(m)
    saat = Saat(T0 + 30_000)
    k = SahteKopru(saat)
    d = ad.AltinDugumu(PaperDefter(m, "test"), ad.ayarlar(), k, saat=saat)
    d.ac()
    return m, d, saat, k


def _net(m, kol):
    with m.connect() as b:
        return sum(q for (q,) in b.execute(select(paper_emir_olay.c.miktar).where(
            paper_emir_olay.c.kol == kol, paper_emir_olay.c.tur == "dolum")))


def test_ayarlar():
    ay = ad.ayarlar()
    assert ay.kol.grup["dugum"] == "altin" and ay.sembol == "GOLD" and ay.lot == 0.01 and ay.magic == 910
    assert ay.risk.kaldirac == 1.0 and ay.strateji == "kanal_kirilim"


def test_pozisyon_yolu_turnuva_fonksiyonuyla_birebir(kur):
    """Canlı düğüm iki günü bar bar yürür; her kararın pozisyonu, aynı çapadan turnuva fonksiyonunun yoluyla aynı ve
    defterdeki / MT5'teki lot o yolu izler (ters dönüşte önce kapat sonra aç)."""
    m, d, saat, k = kur
    ay = d.ay
    for i in range(1, 2 * 96 + 1):
        saat.ms = T0 + i * B + 30_000
        d.tur()
        assert abs(k.poz - d._d().lot) < 1e-9                          # MT5 = defter
    capa = d._capa()
    mask = (k.t >= capa) & (k.t + B <= saat.ms)
    c = k.c[mask]
    b = ca.Barlar(k.t[mask], c, c * 1.0008, c * 0.9992, c, np.full(len(c), 10.0))
    yol = ca.kanal_kirilim(b, **ay.parametre)
    with m.connect() as x:
        kararlar = {int(bm): a for bm, a in x.execute(select(paper_karar.c.bar_ms, paper_karar.c.ayrinti))}
    assert len(kararlar) == 2 * 96
    for j, t in enumerate(k.t[mask]):
        if t in kararlar:
            assert kararlar[t]["poz"] == yol[j]
    assert k.poz == pytest.approx(yol[-1] * 0.01)
    assert _net(m, d.kol.ad) == pytest.approx(yol[-1] * 1.0)             # 0,01 lot = 1 ons
    degisim = np.flatnonzero(np.diff(yol[-2 * 96 - 1:]) != 0)
    assert len(degisim) > 0 and len(k.emirler) >= len(degisim)          # işlem yaptı (sürekli al-sat)
    assert all(abs(h) <= 0.01 + 1e-9 for h, _ in k.emirler)             # yığma yok: tek emir en çok 0,01 lot
    assert all(len(y) <= 31 for _, y in k.emirler)


def test_piyasa_kapaliyken_karar_yok_ve_kopru_yorulmaz(kur):
    m, d, saat, k = kur
    k.kapali = (T0 + 2 * S, T0 + 50 * S)
    saat.ms = T0 + 5 * S + 30_000
    d.tur()
    n = k.mumlar_cagri
    for _ in range(10):
        saat.ms += 20_000
        d.tur()
    assert k.mumlar_cagri == n                                           # aynı bar için tekrar veri istemez
    with m.connect() as x:
        son = x.execute(select(paper_karar.c.bar_ms).order_by(paper_karar.c.bar_ms.desc()).limit(1)).scalar()
    assert son is None or son < T0 + 2 * S


def test_durdurma_saat_basi_kapatir(kur):
    m, d, saat, k = kur
    for i in range(1, 200):
        saat.ms = T0 + i * B + 30_000
        d.tur()
        if k.poz:
            break
    assert k.poz
    d.defter.kol_olay_yaz(d.kol.ad, "durdur", {"neden": "telegram"})
    saat.ms = (saat.ms // S + 1) * S + 1000
    r = d.tur()
    assert r["isaret"]["kapatilan"]["dolum"] == 1 and k.poz == 0 and d._d().lot == 0
    for _ in range(1, 50):                                               # durdurulmuş kol yeni işlem açmaz
        saat.ms += B
        d.tur()
    assert k.poz == 0


def test_yeniden_baslatmada_mt5_islemi_kurtarilir(kur):
    m, d, saat, k = kur
    gercek = d.defter.olay_yaz

    def ol(emir_id, kol, tur, *a, **kw):
        if tur == "dolum":
            raise RuntimeError("süreç öldü")
        return gercek(emir_id, kol, tur, *a, **kw)

    d.defter.olay_yaz = ol
    for i in range(1, 300):
        saat.ms = T0 + i * B + 30_000
        try:
            d.tur()
        except RuntimeError:
            break
    assert len(k.emirler) == 1 and d._d().lot == 0
    d.defter.olay_yaz = gercek
    d2 = ad.AltinDugumu(d.defter, d.ay, k, saat=saat)                   # yeni süreç
    saat.ms += 1000
    r = d2.tur()
    assert r["kurtarma"] == {"kurtarilan": 1, "bulunamayan": 0}
    assert d2._d().lot == pytest.approx(k.poz) and len(k.emirler) == 1


def test_doviz_hesap_degisimi_defteri_kapatir(tmp_path):
    from tests.test_doviz_dugum import D0, faiz_csv
    from tests.test_doviz_dugum import Saat as DSaat
    from tests.test_doviz_dugum import SahteKopru as DovizKopru

    m = create_engine(f"sqlite:///{tmp_path / 'd.db'}")
    metadata.create_all(m)
    saat = DSaat(D0 + 7 * S + 60_000)
    kop = DovizKopru(saat)
    d = dv.DovizDugumu(PaperDefter(m, "test"), dv.ayarlar(), dv.Kaynak(kop, faiz_csv), saat=saat)
    d.ac()
    d.tur()
    assert d._d().lot and len(kop.emirler) == 2
    r = d.hesap_degisimi("NCM eski demo hesabı kapattı")
    assert set(r["kapanan"]) == {"GBPUSD", "USDJPY"} and len(kop.emirler) == 2      # MT5'e emir gitmedi
    durum = d._d()
    assert durum.lot == {} and durum.adet == {}                                      # JPY bakiyesi de çevrildi
    assert [o.tur for o in d.defter.kol_olaylari(d.kol.ad)] == ["hesap_degisimi"]
