"""Faz 7 paper motoru: canlı karar, turnuva backtest'iyle birebir (kural 3, parity)."""
import numpy as np
import polars as pl
import pytest

from tradebot.arastirma import turnuva as tv
from tradebot.canli import karar as kr
from tradebot.canli.kollar import PaperKol, kollar
from tradebot.veri.depo import BarDepo

SAAT = 3_600_000
KAYIT = {k: {"piyasa": "BINANCE", "sinif": "kripto", "takvim": "kripto_7x24"} for k in ("BINANCE:AAAUSDT", "BINANCE:BBBUSDT")}
GRUP = {"kimlikler": list(KAYIT), "asgari_gecmis_gun": 2, "yon": "long"}


def sentetik_depo(yol, n=24 * 60, tohum=3):
    """Açılış = önceki kapanış (7/24 piyasa); trendli ve oynak, frenleri tetikleyecek kadar."""
    depo = BarDepo(yol)
    rng = np.random.default_rng(tohum)
    t = 1_700_000_000_000 - 1_700_000_000_000 % 86_400_000 + np.arange(n) * SAAT
    for j, k in enumerate(KAYIT):
        g = rng.normal(0.0004 * (1 - 2 * j), 0.012, n)
        g[n // 2:n // 2 + 8] = -0.02   # çöküş: günlük fren tetiklensin
        g[n // 2 - 24 * 5:n // 2] = 0.003  # öncesinde yükseliş: trend kolu uzun olsun
        c = 100 * np.exp(np.cumsum(g))
        o = np.concatenate([[100.0], c[:-1]])
        depo.yaz(k, "1h", pl.DataFrame({"acilis_ms": t, "open": o, "high": np.maximum(o, c) * 1.002,
                                         "low": np.minimum(o, c) * 0.998, "close": c, "volume": np.full(n, 5e6)}))
    return depo, t


def kol_yap(bant=0.25, frenler=True):
    ayar = tv.Ayar(hedef_vol=0.2, kaldirac=3.0, vol_pencere_gun=5, frenler=frenler, bant=bant)
    return PaperKol("ma_yon@test@1h", "ma_yon", "test", GRUP, "1h", ayar, {"hizli_gun": 1, "yavas_gun": 4}, "B", 1.0)


@pytest.mark.parametrize("bant,frenler", [(0.25, True), (0.0, False)])
def test_canli_karar_backtest_ile_birebir(tmp_path, bant, frenler):
    depo, t = sentetik_depo(tmp_path)
    kol = kol_yap(bant, frenler)
    h = tv.grup_hazirla(depo, KAYIT, GRUP, "1h")
    hedef = tv.hedef_uret(h, kol.strateji, tv.cevir(kol.parametre, 24.0), "long", kol.ayar, nedensellik=False)
    s = tv.kos(h, hedef, kol.ayar)
    taraf = h.taraf

    # canlı döngü: her kapanmış bar j'de karar, dolum j+1'in açılışında (= j'nin kapanışı), maliyet taraf[j+1]
    d = kr.KolDurum(ozkaynak=1.0, nakit=1.0, izleyici=kr.izleyici_kur(kol, [(int(t[0]), 1.0)]))
    poz = {}
    for j in range(2, len(t) - 1):
        hj = kr.hazirla(depo, KAYIT, kol, bit_ms=int(t[j]) + 1)
        assert np.allclose(np.nan_to_num(kr.hedef_son(hj, kol)), np.nan_to_num(hedef[j]))  # nedensel, kesikte aynı
        k = kr.karar_ver(kol, hj, d, set())
        oz_once = d.ozkaynak
        for i, kim in enumerate(k.kimlikler):
            q = k.miktar.get(kim, 0.0)
            if q:
                p = h.g.acilis[j + 1, i]
                d.adet[kim] = d.adet.get(kim, 0.0) + q
                d.nakit -= q * p + abs(q) * p * taraf[j + 1, i]
        d.onceki_h = dict(zip(k.kimlikler, k.etkin_hedef, strict=True))
        d.ilk = False
        poz[j + 1] = sum(abs(d.adet.get(kim, 0.0)) * h.g.acilis[j + 1, i] for i, kim in enumerate(k.kimlikler)) / oz_once
    ortak = sorted(i for i in poz if i < len(s.pozisyon))
    canli = np.array([poz[i] for i in ortak])
    bt = s.pozisyon[ortak]
    assert bt.max() > 0.1 and (np.diff(bt) != 0).sum() > 20  # gerçekten işlem var
    assert np.allclose(canli, bt, atol=1e-9)
    if frenler:
        assert (s.durum != 0).any()                         # frenler de sınandı


def test_paper_kollari_config():
    ks = kollar()
    assert len(ks) == 12 and sum(k.jev for k in ks) == 6
    ag, pf = ks[-2], ks[-1]
    assert pf.strateji == "portfoy" and pf.jev and all(x.endswith("+jev") for x in pf.parametre["kaynaklar"])
    assert ag.strateji == "agresif" and ag.sinif == "gozlem" and len(ag.parametre["kaynaklar"]) == 5
    assert {k.zd for k in ks} == {"1h", "4h", "1d"}
    assert all(k.ayar.kaldirac <= 3 for k in ks)
    ad = {k.ad: k for k in ks}
    assert ad["d2:donchian_ls@kripto_btc_eth@4h"].parametre == {"giris_gun": 55, "cikis_gun": 20}
    assert ad["tsmom@kripto_btc_eth@4h+jev"].ayar.vol_pencere_gun == 30


def test_defter_durumu_kayitlardan_kurar(ayar):
    import dataclasses

    from sqlalchemy.exc import IntegrityError

    from tradebot.canli.defter import PaperDefter
    from tradebot.db import metadata, motor

    m = motor(ayar)
    metadata.create_all(m)
    df = PaperDefter(m, "test")
    kol = dataclasses.replace(kol_yap(), baslangic_ozkaynak=1000.0)
    assert df.kol_ac(kol, 0) and not df.kol_ac(kol, 0)
    d0 = df.durum(kol)
    assert d0.nakit == 1000.0 and d0.adet == {} and d0.ilk
    k = kr.Karar(kol.ad, 3600_000, ("BINANCE:AAAUSDT",), np.array([0.5]), np.array([0.5]), np.array([0.0]),
                 np.array([0.5]), np.array([True]), np.array([100.0]), "normal", (), {"BINANCE:AAAUSDT": 5.0})
    kid = df.karar_yaz(k, "h")
    assert df.karar_var(kol.ad, 3600_000) == kid
    with pytest.raises(IntegrityError):
        df.karar_yaz(k, "h")                                  # aynı bar için ikinci karar yok
    eid = df.emir_yaz(kol.ad, kid, "e1", "BINANCE:AAAUSDT", 5.0, 5.0, 100.0, "karar", {"onay": True})
    df.olay_yaz(eid, kol.ad, "dolum", "BINANCE:AAAUSDT", 5.0, 101.0, 0.5, 7200_000)
    d = df.durum(kol)
    assert d.adet == {"BINANCE:AAAUSDT": 5.0} and d.nakit == pytest.approx(1000 - 505 - 0.5)
    assert d.onceki_h == {"BINANCE:AAAUSDT": 0.5} and not d.ilk
    d.isaretle({"BINANCE:AAAUSDT": 110.0})
    df.ozkaynak_yaz(kol.ad, 7200_000, d, {"BINANCE:AAAUSDT": 110.0})
    assert df.durum(kol).ozkaynak == pytest.approx(494.5 + 550)
    degismis = dataclasses.replace(kol, parametre={"hizli_gun": 2, "yavas_gun": 4})
    with pytest.raises(ValueError, match="tanım değişti"):
        df.kol_ac(degismis)


def test_canli_barlar_kopyalar_tamamlar_yalniz_kapanmis(tmp_path, ayar):
    import json as _json

    from tradebot.canli.bar_akisi import CanliBarlar
    from tradebot.db import metadata, motor
    from tradebot.veri.depo import HamDepo

    m = motor(ayar)
    metadata.create_all(m)
    ana, _ = sentetik_depo(tmp_path / "ana", n=48)
    son_ana = int(ana.oku("BINANCE:AAAUSDT", "1h")["acilis_ms"].max())

    class Http:
        def __init__(self):
            self.istek = []

        def al(self, url, params=None):
            self.istek.append(params)
            bas = params["startTime"]
            return _json.dumps([[bas + i * SAAT, "1", "2", "0.5", "1.5", "10", bas + (i + 1) * SAAT - 1, "15", 3]
                                for i in range(5)]).encode()

    http = Http()
    cb = CanliBarlar(ana, BarDepo(tmp_path / "canli"), HamDepo(tmp_path / "ham", m), http)
    simdi = son_ana + 4 * SAAT + SAAT // 2          # 3 yeni bar kapanmış, 4.'sü açık
    son = cb.hazirla(["BINANCE:AAAUSDT"], simdi)
    assert son["BINANCE:AAAUSDT"] == son_ana + 3 * SAAT
    df = cb.canli.oku("BINANCE:AAAUSDT", "1h")
    assert len(df) == 48 + 3 and df["quote_volume"][-1] == 15.0
    assert cb.guncelle(["BINANCE:AAAUSDT"], simdi)["BINANCE:AAAUSDT"] == son_ana + 3 * SAAT and len(http.istek) == 1


class SahteBarlar:
    """CanliBarlar yerine: depo hazır, guncelle son bar açılışlarını döndürür."""

    def __init__(self, depo):
        self.canli = depo

    def guncelle(self, kimlikler, simdi_ms):
        return {k: int(self.canli.oku(k, "1h")["acilis_ms"].max()) for k in kimlikler}


class SahteStrateji:
    def __init__(self, beyin, kol):
        self.beyin, self.kol, self.poz, self.gonderilen = beyin, kol, {}, []

    def adim(self, kim):
        return 1e-6

    def yuvarla(self, kim, q):
        return round(q, 6)

    def pozisyon(self, kim):
        return self.poz.get(kim, 0.0)

    def gonder(self, karar_id, kim, istenen, q, fiyat, tur, risk):
        eid = self.beyin.defter.emir_yaz(self.kol.ad, karar_id, f"c{len(self.gonderilen)}-{self.kol.ad}", kim, q, q,
                                         fiyat, tur, risk)
        self.gonderilen.append((kim, q, tur))
        px = fiyat * 1.0005
        self.beyin.defter.olay_yaz(eid, self.kol.ad, "dolum" if tur != "toparlanma" else "toparlanma", kim, q, px,
                                   abs(q) * px * 0.001, 0)
        self.poz[kim] = self.poz.get(kim, 0.0) + q
        self.beyin.dolum(self.kol.ad, kim, q, px, abs(q) * px * 0.001, tur)


def test_beyin_karar_emir_defter_ve_mutabakat(tmp_path, ayar, monkeypatch):
    import dataclasses

    from tradebot.canli import dugum
    from tradebot.canli.defter import PaperDefter
    from tradebot.db import metadata, motor

    monkeypatch.setattr(dugum, "aktif_vetolar", lambda m, t: set())
    m = motor(ayar)
    metadata.create_all(m)
    depo, t = sentetik_depo(tmp_path, n=24 * 40)
    k1 = dataclasses.replace(kol_yap(frenler=False), baslangic_ozkaynak=100_000.0)
    k4 = dataclasses.replace(k1, ad="ma_yon@test@4h", zd="4h")
    df = PaperDefter(m, "test")
    for k in (k1, k4):
        df.kol_ac(k, int(t[0]))
    b = dugum.Beyin(m, [k1, k4], df, SahteBarlar(depo), KAYIT)
    for k in (k1, k4):
        b.stratejiler[k.ad] = SahteStrateji(b, k)
    kapanis = int(t[-1]) + SAAT                                  # son barın kapanışı
    monkeypatch.setattr(dugum.time, "time", lambda: (kapanis + 5_000) / 1000)  # saat: kapanıştan 5 sn sonra
    assert b.saat_kapandi(kapanis)
    from sqlalchemy import func, select

    from tradebot.db import paper_karar, paper_ozkaynak
    with m.connect() as c:
        kararlar = dict(c.execute(select(paper_karar.c.kol, func.count()).group_by(paper_karar.c.kol)).all())
        assert c.execute(select(func.count()).select_from(paper_ozkaynak)).scalar() == 2
    assert kararlar.get(k1.ad) == 1
    assert kararlar.get(k4.ad, 0) == (1 if dugum.sinir_doldu("4h", kapanis) else 0)
    assert b.saat_kapandi(kapanis)                               # aynı kapanış: ikinci karar yok
    with m.connect() as c:
        assert c.execute(select(func.count()).select_from(paper_karar).where(paper_karar.c.kol == k1.ad)).scalar() == 1
    s1 = b.stratejiler[k1.ad]
    assert s1.gonderilen and all(tur == "karar" for _, _, tur in s1.gonderilen)
    assert df.durum(k1).adet == pytest.approx(b.durum[k1.ad].adet)  # bellek = defter
    assert b.mutabakat() == {}
    kim = next(iter(s1.poz))
    s1.poz[kim] += 1.0                                           # Nautilus'ta sapma
    assert k1.ad in b.mutabakat() and k1.ad in b.durdurulan
    s1.poz = {}                                                  # yeniden başlatma: sandbox boş
    b.toparla()
    assert s1.gonderilen[-1][2] == "toparlanma" and df.durum(k1).adet == pytest.approx(b.durum[k1.ad].adet)


def test_kacan_kapanis():
    from tradebot.canli.dugum import kacan_kapanis
    h = 1_790_604_000_000                               # saat başı
    assert kacan_kapanis(h + 60_000, h - SAAT, None) is None          # 1 dk: bar olayı bekleniyor
    assert kacan_kapanis(h + 3 * 60_000, h - SAAT, None) == h         # 3 dk: kaçtı, REST'ten işle
    assert kacan_kapanis(h + 3 * 60_000, h, None) is None             # işlendi
    assert kacan_kapanis(h + 3 * 60_000, h - SAAT, h) is None         # deneniyor (bar REST'te yok, yeniden)
    assert kacan_kapanis(h + SAAT + 5 * 60_000, h - SAAT, None) == h + SAAT   # uzun donma: son kapanış


def test_sinir_doldu():
    from tradebot.canli.dugum import sinir_doldu
    gun = 1_700_000_000_000 - 1_700_000_000_000 % 86_400_000
    assert sinir_doldu("1h", gun + 5 * SAAT) and not sinir_doldu("4h", gun + 5 * SAAT)
    assert sinir_doldu("4h", gun + 8 * SAAT) and sinir_doldu("1d", gun) and not sinir_doldu("1d", gun + 4 * SAAT)


def test_agresif_hedef_ortalama_kelly_tavan(tmp_path):
    import dataclasses

    depo, t = sentetik_depo(tmp_path)
    a = kol_yap()
    b = dataclasses.replace(a, ad="b", parametre={"hizli_gun": 2, "yavas_gun": 8})
    ag = dataclasses.replace(a, ad="agresif", strateji="agresif", parametre={"kaynaklar": ["x", "b"], "kelly_carpani": 5.0})
    kapanis = int(t[-1]) + SAAT
    ha, hb = (kr.hazirla(depo, KAYIT, k, bit_ms=kapanis) for k in (a, b))
    beklenen = np.clip((np.nan_to_num(kr.hedef_son(ha, a)) + np.nan_to_num(kr.hedef_son(hb, b))) / 2 * 5.0, 0.0, 0.5)
    h = kr.agresif_hedef(depo, KAYIT, ag, [a, b], kapanis)
    assert np.allclose(h, beklenen) and h.max() <= 0.5 and h.min() >= 0.0
    d = kr.KolDurum(ozkaynak=1.0, nakit=1.0)
    k = kr.karar_ver(ag, ha, d, set(), h)                      # dengeleme zinciri aynı
    assert np.allclose(k.hedef, h)


def test_beyin_portfoy_kaynak_hedefi_ve_olaylar(tmp_path, ayar, monkeypatch):
    """Portföy kolu: aynı kapanışta kaynak kolun etkin hedefi × katsayı (enstrüman tavanında kırpılır); hafta dağıtımı
    yoksa hesaplanıp yazılır; mutabakat durdurması olay olarak yazılır."""
    import dataclasses

    from sqlalchemy import func, select

    from tradebot.canli import dagitici as dg
    from tradebot.canli import dugum
    from tradebot.canli.defter import PaperDefter
    from tradebot.db import metadata, motor, paper_dagitim, paper_karar

    monkeypatch.setattr(dugum, "aktif_vetolar", lambda m, t: set())
    m = motor(ayar)
    metadata.create_all(m)
    depo, t = sentetik_depo(tmp_path, n=24 * 40)
    k1 = dataclasses.replace(kol_yap(frenler=False), baslangic_ozkaynak=100_000.0)
    pf = dataclasses.replace(k1, ad="portfoy@test", strateji="portfoy", sinif="portfoy",
                             parametre={"kaynaklar": [k1.ad], "onsel_sharpe": {k1.ad: 0.8}, "dagitici": {}})
    df = PaperDefter(m, "test")
    for k in (k1, pf):
        df.kol_ac(k, int(t[0]))
    b = dugum.Beyin(m, [k1, pf], df, SahteBarlar(depo), KAYIT)
    for k in (k1, pf):
        b.stratejiler[k.ad] = SahteStrateji(b, k)
    kapanis = int(t[-1]) + SAAT
    monkeypatch.setattr(dugum.time, "time", lambda: (kapanis + 5_000) / 1000)

    b.dagitim = {"hafta_ms": dg.hafta_basi(kapanis), "kollar": {k1.ad: {"katsayi": 1.6}}, "kaldirac": 1.6}
    assert b.saat_kapandi(kapanis)
    with m.connect() as c:
        ayr = dict(c.execute(select(paper_karar.c.kol, paper_karar.c.ayrinti)).all())
    beklenen = np.clip(1.6 * np.array(ayr[k1.ad]["etkin"]), 0.0, 0.5)
    assert np.allclose(ayr[pf.ad]["hedef"], beklenen) and max(ayr[k1.ad]["etkin"]) > 0  # gerçekten pozisyonlu
    assert ayr[pf.ad]["gecikmeli"] is False

    b.dagitim = None                                             # açılış: hafta dağıtımı defterden hesaplanır
    b._dagitim_guncelle(kapanis)
    with m.connect() as c:
        assert c.execute(select(func.count()).select_from(paper_dagitim)).scalar() == 1
    assert b.dagitim["kaldirac"] == 0.0                          # geçmiş yok, sınıf B

    s1 = b.stratejiler[k1.ad]
    s1.poz[next(iter(s1.poz))] += 1.0
    b.mutabakat()
    assert [o.tur for o in df.kol_olaylari(k1.ad)] == ["durdur"]


def test_portfoy_acil_kalici_ve_onayli_kaldirma():
    import dataclasses

    from tradebot.risk.motor import Durum

    k = dataclasses.replace(kol_yap(), baslangic_ozkaynak=100.0)
    pf = dataclasses.replace(k, ad="portfoy", strateji="portfoy")
    gun = 86_400_000
    t0 = 1_790_000_000_000 - 1_790_000_000_000 % gun
    yol = [(t0 + i * gun, v) for i, v in enumerate([100, 97, 94, 91, 88, 85, 82, 79, 76, 73, 72, 72, 72])]
    assert kr.izleyici_kur(k, yol).durum != Durum.ACIL_DURDURMA          # gözlem kolu: kalıcı değil
    assert kr.izleyici_kur(pf, yol).durum == Durum.ACIL_DURDURMA         # portföy: kalıcı
    iz = kr.izleyici_kur(pf, yol, [(yol[11][0] + 1, "Scryne", "inceleme tamam")])
    assert iz.durum == Durum.NORMAL
    son = kr.izleyici_kur(pf, yol, [(yol[-1][0] + 5, "Scryne", "geç onay")])  # son işaretten sonra da uygulanır
    assert son.durum == Durum.NORMAL


def test_terfi_olayi_sinifi_degistirir(ayar):
    from tradebot.canli.defter import PaperDefter
    from tradebot.db import metadata, motor

    m = motor(ayar)
    metadata.create_all(m)
    df = PaperDefter(m, "test")
    k = kol_yap()
    assert df.sinif(k) == "B"
    df.kol_olay_yaz(k.ad, "terfi", {"eski": "B", "yeni": "A", "gerekce": "test"}, zaman_ms=1_000)
    assert df.sinif(k, bit_ms=500) == "B" and df.sinif(k, bit_ms=2_000) == "A" and df.sinif(k) == "A"


def test_ardisik_ret_kolu_durdurur(tmp_path, ayar):
    import dataclasses

    from tradebot.canli import dugum
    from tradebot.canli.defter import PaperDefter
    from tradebot.db import metadata, motor

    m = motor(ayar)
    metadata.create_all(m)
    depo, t = sentetik_depo(tmp_path, n=24 * 5)
    k = dataclasses.replace(kol_yap(), baslangic_ozkaynak=100_000.0)
    df = PaperDefter(m, "test")
    df.kol_ac(k, int(t[0]))
    b = dugum.Beyin(m, [k], df, SahteBarlar(depo), KAYIT)
    kim = "BINANCE:AAAUSDT"
    b.ret(k.ad, kim, "yetersiz bakiye")
    b.ret(k.ad, kim, "yetersiz bakiye")
    b.dolum(k.ad, kim, 0.0, 100.0, 0.0, "karar")               # araya giren dolum sayacı sıfırlar
    b.ret(k.ad, kim, "yetersiz bakiye")
    assert k.ad not in b.durdurulan
    for _ in range(2):
        b.ret(k.ad, kim, "yetersiz bakiye")
    assert k.ad in b.durdurulan
    o = df.kol_olaylari(k.ad)
    assert [x.tur for x in o] == ["durdur"] and o[0].ayrinti["neden"] == "ardisik_ret" and o[0].ayrinti["sayi"] == 3
