"""Mikro ivme skalpı: saf karar (giriş yönü, hedef/stop/süre, bekleme) ve düğüm (emir yolu, spread'li dolum, durdurma,
frende yeni işlem yok, dakikalık işaret, özet istatistiği)."""
from sqlalchemy import create_engine, select

from tradebot.canli import skalp as sk
from tradebot.canli.defter import PaperDefter
from tradebot.cekirdek import skalp as cs
from tradebot.db import metadata, paper_ozkaynak

T0 = 1_790_640_000_000 // 3_600_000 * 3_600_000 + 60_000   # saat başından 1 dk sonra


def test_saf_karar():
    k = dict(tp=0.3, sl=1.2, azami_ms=300_000, bekleme_ms=10_000)
    assert cs.karar(0, 0, 100.0, 100.6, 100.0, 0, 20_000, **k) == (1, "giris")       # orta 100,3 > 100
    assert cs.karar(0, 0, 100.0, 100.6, 100.5, 0, 20_000, **k) == (-1, "giris")
    assert cs.karar(0, 0, 100.0, 100.6, 100.3, 0, 20_000, **k) == (0, "hareket_yok")
    assert cs.karar(0, 0, 100.0, 100.6, 100.0, 0, 5_000, **k) == (0, "bekle")         # kapanıştan beri 10 sn olmadı
    assert cs.karar(0, 0, 100.0, 100.6, None, 0, 20_000, **k) == (0, "bekle")
    # uzun 100,6'dan: bid 100,9 → +0,3 (hedef); bid 99,3 → −1,3 (stop); süre
    assert cs.karar(1, 100.6, 100.9, 101.5, None, 1_000, 0, **k) == (0, "hedef")
    assert cs.karar(1, 100.6, 99.3, 99.9, None, 1_000, 0, **k) == (0, "stop")
    assert cs.karar(1, 100.6, 100.7, 101.3, None, 300_000, 0, **k) == (0, "sure")
    assert cs.karar(1, 100.6, 100.7, 101.3, None, 1_000, 0, **k) == (1, "tut")
    # kısa: kapanış ask ile
    assert cs.karar(-1, 100.0, 99.0, 99.6, None, 1_000, 0, **k) == (0, "hedef")


class Saat:
    def __init__(self, ms):
        self.ms = ms

    def __call__(self):
        return self.ms / 1000


class Kopru:
    """Elle sürülen fiyat; dolum spread'li (alış ask, satış bid)."""

    def __init__(self, saat):
        self.saat, self.bid, self.spread, self.poz, self.giris, self.emirler = saat, 4000.0, 0.7, 0.0, 0.0, []

    def kotasyon(self, s):
        return {"kotasyon": {"GOLD": {"bid": self.bid, "ask": self.bid + self.spread, "tik_ms": int(self.saat() * 1000)}}}

    def pozisyonlar(self, magic):
        return [{"sembol": "GOLD", "hacim": self.poz, "fiyat": self.giris, "zaman_ms": int(self.saat() * 1000)}] \
            if abs(self.poz) > 1e-9 else []

    def islemler(self, magic, bas_ms):
        return []

    def emir(self, sembol, hacim, yorum, magic, sapma=20, sl_mesafe=None):
        px = self.bid + self.spread if hacim > 0 else self.bid
        self.emirler.append((hacim, yorum, sl_mesafe))
        if abs(self.poz) < 1e-9:
            self.giris = px
        self.poz = round(self.poz + hacim, 8)
        return {"sonuc": [{"lot": hacim, "hacim": abs(hacim), "fiyat": px, "retcode": 10009, "islem": len(self.emirler)}]}


def _kur():
    m = create_engine("sqlite://")
    metadata.create_all(m)
    d = {"frenler": True, "skalp": {"ad": "sk:test@xau_tik@10s", "sembol": "GOLD", "strateji": "mikro_ivme",
                                    "parametre": {"bekleme_sn": 10, "tp_usd": 0.3, "sl_oran": 0.0003, "azami_sn": 300},
                                    "lot": 0.01, "ons_lot": 100, "maliyet": {"kayma_bps": 0.0, "finansman_yillik": 0.04},
                                    "risk": {"kaldirac": 1.0}, "magic": 912, "baslangic_ozkaynak": 10000}}
    ay, p = sk.ayarlar(d)
    saat = Saat(T0)
    kp = Kopru(saat)
    mesaj = []
    n = sk.SkalpDugumu(PaperDefter(m, "test"), ay, p, kp, saat, bildir=mesaj.append)
    n.ac()
    return m, n, kp, saat, mesaj


def _adim(n, saat, sn=3):
    saat.ms += sn * 1000
    return n.tur()


def test_dugum_giris_hedef_stop_ve_ozet():
    m, n, kp, saat, mesaj = _kur()
    n.tur()
    for _ in range(4):                       # 12 sn: bekleme doldu, fiyat yükseldi → uzun
        kp.bid += 0.1
        r = _adim(n, saat)
    assert kp.poz == 0.01 and kp.emirler[0][2] is not None             # acil stop gönderildi
    giris = kp.giris
    kp.bid = giris + 0.3                      # kapanış bid'i girişin 0,3 üstü → hedef
    r = _adim(n, saat)
    assert r["karar"]["neden"] == "hedef" and kp.poz == 0.0
    assert n.istatistik(0) == {"islem": 1, "kazanan": 1, "net": n.istatistik(0)["net"]}
    assert abs(n.istatistik(0)["net"] - 0.3) < 1e-6                     # 1 ons × 0,3 $
    for _ in range(4):                       # bekleme, sonra düşüş → kısa
        kp.bid -= 0.1
        _adim(n, saat)
    assert kp.poz == -0.01
    kp.bid = kp.giris + 1.3                   # ask = giriş + 2,0 → stop (0,03 % × 4000 = 1,2)
    r = _adim(n, saat)
    assert r["karar"]["neden"] == "stop" and kp.poz == 0.0
    with m.connect() as b:
        assert b.execute(select(paper_ozkaynak.c.zaman_ms).where(paper_ozkaynak.c.kol == n.kol.ad)).first() is not None
    saat.ms += sk.OZET_MS
    n.tur()
    assert mesaj and "işlem" in mesaj[-1]


def test_durdurulan_kol_kapatir_ve_acmaz():
    m, n, kp, saat, _ = _kur()
    n.tur()
    for _ in range(4):
        kp.bid += 0.1
        _adim(n, saat)
    assert kp.poz == 0.01
    n.defter.kol_olay_yaz(n.kol.ad, "durdur", {"neden": "telegram"})
    r = _adim(n, saat)
    assert r["karar"]["neden"] == "durdur" and kp.poz == 0.0
    for _ in range(6):
        kp.bid += 0.1
        _adim(n, saat)
    assert kp.poz == 0.0
