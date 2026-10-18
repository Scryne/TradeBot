"""Nasdaq paper düğümü: karar → risk → bekleyen emir → açılışta dolum (iç ve Alpaca), işaret, durdurma, mutabakat."""
from datetime import UTC, datetime

import numpy as np
import polars as pl
import pytest

from tradebot.canli import nasdaq as nd
from tradebot.canli.alpaca import Dolum
from tradebot.canli.defter import PaperDefter
from tradebot.db import metadata, motor, paper_emir_olay, paper_karar
from tradebot.veri import nasdaq as nqv
from tradebot.veri.depo import BarDepo
from tradebot.veri.takvim import takvim

GUN = 86_400_000


def _ms(s: str) -> int:
    return int(datetime.fromisoformat(s).replace(tzinfo=UTC).timestamp() * 1000)


CUMA_KARAR = _ms("2026-10-16T20:50:00")        # kapanış 20:00 UTC (EDT) + 50 dk (karar gecikmesi 45 dk)
PZT_ACILIS = _ms("2026-10-19T13:30:00")


def _yapi(d: dict, yurutme: str = "ic") -> dict:
    return {"frenler": True, "nasdaq": {
        "yurutme": yurutme, "baslangic_ozkaynak": 100_000,
        "boyut": {"hedef_vol": 0.20, "kaldirac": 1.0, "vol_pencere_gun": 60, "bant": 0.25},
        "grup": {"dinamik": "nasdaq", "uyelik": "nasdaq100", "kapsam_tolerans_gun": 10, "asgari_gecmis_gun": 60,
                 "yon": "long"},
        "kollar": [{"ad": "d19:hisse_momentum@nasdaq100@1d", "strateji": "hisse_momentum", "sinif": "B",
                    "parametre": {"geriye_gun": 126, "atla_gun": 21, "ust_n": 4, "filtre_gun": 0, "aylik": True}}]}} | d


class SahteKaynak:
    def __init__(self, depo: BarDepo) -> None:
        self.depo, self.son = depo, {}

    def guncelle(self) -> dict:
        return {"sahte": True}

    def fiyatlar(self, kimlikler):
        return {k: float(self.depo.oku(k, "1d")["close"][-1]) for k in kimlikler}

    def acilis(self, kimlikler, acilis_ms):
        return {k: float(self.depo.oku(k, "1d")["close"][-1]) * 1.001 for k in kimlikler}


class SahteAlpaca:
    def __init__(self) -> None:
        self.emirler: dict[str, dict] = {}
        self.poz: dict[str, float] = {}

    def emir_gonder(self, sembol, adet, istemci, zaman):
        self.emirler[istemci] = {"sembol": sembol, "adet": adet, "zaman": zaman}
        self.poz[sembol] = self.poz.get(sembol, 0.0) + adet
        return {"id": f"A-{istemci}"}

    def emir(self, istemci):
        e = self.emirler.get(istemci)
        return None if e is None else Dolum(istemci, f"A-{istemci}", "filled", e["adet"], 100.0)

    def pozisyonlar(self):
        return {s: q for s, q in self.poz.items() if abs(q) > 1e-9}

    def son_fiyatlar(self, semboller):
        return {}


@pytest.fixture
def ortam(ayar):
    m = motor(ayar)
    metadata.create_all(m)
    depo = BarDepo(ayar.veri_dizini)
    gunler = takvim("XNYS").gunluk_barlar(_ms("2025-06-02"), _ms("2026-10-17"))
    rng = np.random.default_rng(5)
    donem, kayit = {}, {}
    for j in range(10):
        c = 100 * np.exp(np.cumsum(rng.normal(0.0004 * (j - 3), 0.01, len(gunler))))
        k = f"NASDAQ:S{j}"
        depo.yaz(k, "1d", pl.DataFrame({"acilis_ms": gunler, "open": c, "high": c * 1.01, "low": c * 0.99, "close": c,
                                         "volume": np.full(len(gunler), 1e6)}))
        donem[k] = [(int(gunler[0]), None)]
        kayit[k] = {"kimlik": k, "piyasa": "NASDAQ", "sinif": "hisse", "takvim": "XNYS"}
    nqv.uyelik_yaz(ayar.veri_dizini, nqv.Uyelik(donem, "sha"), "commit")
    return m, depo, kayit


def _dugum(ortam, yurutme="ic", alpaca=None, saat=None):
    m, depo, kayit = ortam
    ay = nd.ayarlar(_yapi({}, yurutme))
    s = {"t": CUMA_KARAR}
    d = nd.NasdaqDugumu(PaperDefter(m, "test"), ay, SahteKaynak(depo), depo, lambda: kayit, alpaca,
                        saat=saat or (lambda: s["t"] / 1000))
    d.ac()
    return d, s


def test_karar_kapanistan_sonra_bir_kez_ve_bekleyen_emirler(ortam):
    d, s = _dugum(ortam)
    s["t"] = _ms("2026-10-16T19:00:00")                # seans açık: karar yok
    assert "karar" not in d.tur()
    s["t"] = CUMA_KARAR
    r = d.tur()
    kol = "d19:hisse_momentum@nasdaq100@1d"
    assert r["karar"][kol]["onay"] >= 1
    bek = d.bekleyenler()
    assert bek and all(b.adet > 0 for b in bek) and len(bek) <= 4
    s["t"] += 120_000
    assert "karar" not in d.tur()                       # aynı gün ikinci karar yok
    with ortam[0].connect() as b:
        assert b.execute(paper_karar.select()).fetchall()[0].bar_ms == _ms("2026-10-16")


def test_ic_yurutme_acilista_dolar_ve_isaret_yazar(ortam):
    d, s = _dugum(ortam)
    d.tur()
    s["t"] = _ms("2026-10-17T12:00:00")                 # Cumartesi: dolum yok
    assert "yurutme" not in d.tur()
    s["t"] = PZT_ACILIS + 4 * 60_000
    r = d.tur()
    assert r["yurutme"]["ic_dolum"] >= 1 and not d.bekleyenler()
    kol = d.ay.kollar[0]
    durum = d.defter.durum(kol)
    brut = sum(abs(q) * float(ortam[1].oku(k, "1d")["close"][-1]) for k, q in durum.adet.items())
    assert 0 < brut <= 100_000 * 1.001                    # nakit hesap: brüt ≤ 1x
    with ortam[0].connect() as b:
        dol = b.execute(paper_emir_olay.select().where(paper_emir_olay.c.tur == "dolum")).fetchall()
    assert all(o.ayrinti["kaynak"] == "acilis" for o in dol)


def test_elle_durdurma_seans_icinde_hemen_kapatir(ortam):
    d, s = _dugum(ortam)
    d.tur()
    s["t"] = PZT_ACILIS + 4 * 60_000
    d.tur()
    kol = d.ay.kollar[0]
    assert d.defter.durum(kol).adet
    d.defter.kol_olay_yaz(kol.ad, "durdur", {"neden": "telegram"})
    s["t"] = _ms("2026-10-19T15:00:30")                  # sonraki saat işareti: kapatma emri + hemen dolum
    d.tur()
    s["t"] += 60_000
    d.tur()
    assert not d.defter.durum(kol).adet


def test_alpaca_acilistan_sonra_gonderir_dolumu_yazar_mutabakat_tamam(ortam):
    alp = SahteAlpaca()
    d, s = _dugum(ortam, "alpaca", alp)
    d.tur()
    s["t"] = PZT_ACILIS - 10 * 60_000                    # açılış öncesi: gönderim yok
    d.tur()
    assert not alp.emirler
    s["t"] = PZT_ACILIS + 90_000
    r = d.tur()
    assert r["yurutme"]["alpaca_gonderilen"] >= 1 and all(e["zaman"] == "day" for e in alp.emirler.values())
    s["t"] += 60_000
    r = d.tur()
    assert r["yurutme"]["alpaca_dolum"] >= 1 and not d.bekleyenler()
    s["t"] = _ms("2026-10-19T15:00:10")
    r = d.tur()
    assert r["isaret"]["mutabakat"] == {"tamam": True}
    alp.poz["S9"] = alp.poz.get("S9", 0.0) + 5           # defterin bilmediği pozisyon: fark → kol durur (yeni risk yok)
    s["t"] = _ms("2026-10-19T16:00:10")
    r = d.tur()
    assert "fark" in r["isaret"]["mutabakat"] and d._durduruldu(d.ay.kollar[0].ad) == (True, False)


def test_kacan_karar_ertesi_acilistan_once_telafi_sonra_atlanir(ortam):
    d, s = _dugum(ortam)
    s["t"] = _ms("2026-10-18T10:00:00")                  # Pazar: Cuma'nın kararı telafi edilir (emirler bayat sayılmaz)
    r = d.tur()
    assert r["karar"]["d19:hisse_momentum@nasdaq100@1d"]["onay"] >= 1
    d2, s2 = _dugum(ortam)
    s2["t"] = PZT_ACILIS + 3_600_000                     # açılış geçti: Cuma kararı yine yazılmaz (zaten var) …
    assert "karar" not in d2.tur()


def test_nakit_kolu_kaldirac_bir_ustu_reddedilir():
    with pytest.raises(ValueError):
        nd.ayarlar(_yapi({"nasdaq": _yapi({})["nasdaq"] | {"boyut": {"hedef_vol": 0.2, "kaldirac": 2.0,
                                                                         "vol_pencere_gun": 60, "bant": 0.25}}}))


def test_duzenleyici_ucret_yalniz_satista():
    assert nd.duzenleyici_ucret(10, 100.0) == 0.0
    assert nd.duzenleyici_ucret(-10, 100.0) == pytest.approx(10 * 100 * 20.6e-6 + 10 * 0.000166)


def test_emekli_dugum_alarm_uretmez_gozetmen_kapatmasi_emeklilik_degil(ortam):
    from tradebot.canli.gozetmen import NEDEN, aktif_kollar

    d, s = _dugum(ortam)
    m = ortam[0]
    kol = d.ay.kollar[0].ad
    assert aktif_kollar(m, "nasdaq") == [kol]
    d.defter.kol_olay_yaz(kol, "durdur", {"neden": "scryne_projeyi_dondur"})
    assert aktif_kollar(m, "nasdaq") == []                      # durdurulmuş + düz: emekli
    d.defter.kol_olay_yaz(kol, "durdur", {"neden": NEDEN})
    assert aktif_kollar(m, "nasdaq") == [kol]                   # donma kapatması: motor hâlâ izlenir


def test_gozetmen_nasdaq_donmasinda_yalniz_kendi_sembollerini_kapatir(ortam):
    from tradebot.canli.gozetmen import Gozetmen, net_pozisyonlar

    d, s = _dugum(ortam)
    d.tur()
    s["t"] = PZT_ACILIS + 4 * 60_000
    d.tur()                                                   # iç yürütme: pozisyonlar açıldı, işaret yazıldı
    kol = d.ay.kollar[0].ad
    acik = net_pozisyonlar(ortam[0])[kol]

    class Kapatan:
        def __init__(self):
            self.kapanan = []

        def kapat(self, sembol):
            self.kapanan.append(sembol)

    alp = Kapatan()
    t = {"ms": PZT_ACILIS + 4 * 3_600_000}
    g = Gozetmen(ortam[0], lambda ks: {k: (100.0, 100.0) for k in ks}, "test", dugum="nasdaq", alpaca=alp,
                 onay_tur=1, isinma_sn=0, saat=lambda: t["ms"] / 1000)
    r = g.kontrol()
    assert r["durum"] == "donma" and sorted(alp.kapanan) == sorted(k.split(":")[1] for k in acik)
    assert not net_pozisyonlar(ortam[0]).get(kol)


def test_jev_ikizi_ic_simulasyonda_vetolu_hisseyi_almaz_mutabakata_girmez(ortam):
    from tradebot.zeka import olay

    m, depo, kayit = ortam
    y = _yapi({}, "alpaca")
    y["nasdaq"]["kollar"].append({**y["nasdaq"]["kollar"][0], "ad": "d19:hisse_momentum@nasdaq100@1d+jev", "jev": True,
                                  "yurutme": "ic"})
    ay = nd.ayarlar(y)
    alp = SahteAlpaca()
    s = {"t": CUMA_KARAR}
    d = nd.NasdaqDugumu(PaperDefter(m, "test"), ay, SahteKaynak(depo), depo, lambda: kayit, alp,
                        saat=lambda: s["t"] / 1000)
    d.ac()
    assert d.kol_modu(ay.kollar[0].ad) == "alpaca" and d.kol_modu(ay.kollar[1].ad) == "ic"
    for j in range(10):                                   # her hisseye veto: Jev'li ikiz hiç almamalı
        olay.yaz(m, "veto", f"NASDAQ:S{j}", CUMA_KARAR - 3_600_000, "test", "A3_sec")
    r = d.tur()["karar"]
    assert r[ay.kollar[0].ad]["onay"] >= 1 and r[ay.kollar[1].ad]["onay"] == 0
    s["t"] = PZT_ACILIS + 90_000
    d.tur()
    s["t"] += 60_000
    d.tur()
    s["t"] = _ms("2026-10-19T15:00:10")
    assert d.tur()["isaret"]["mutabakat"] == {"tamam": True}


def test_yuz_hisselik_dengeleme_emir_hizina_takilmaz(ayar):
    """2026-10-18: varsayılan 30 emir/dk sınırı eşit ağırlık kolunun 100 emrinin 70'ini reddetti."""
    m = motor(ayar)
    metadata.create_all(m)
    depo = BarDepo(ayar.veri_dizini)
    gunler = takvim("XNYS").gunluk_barlar(_ms("2025-06-02"), _ms("2026-10-17"))
    donem, kayit = {}, {}
    for j in range(100):
        c = 100 * np.exp(np.cumsum(np.full(len(gunler), 0.001)) + 0.01 * np.sin(np.arange(len(gunler)) + j))
        k = f"NASDAQ:S{j}"
        depo.yaz(k, "1d", pl.DataFrame({"acilis_ms": gunler, "open": c, "high": c, "low": c, "close": c,
                                         "volume": np.full(len(gunler), 1e6)}))
        donem[k] = [(int(gunler[0]), None)]
        kayit[k] = {"kimlik": k, "piyasa": "NASDAQ", "sinif": "hisse", "takvim": "XNYS"}
    nqv.uyelik_yaz(ayar.veri_dizini, nqv.Uyelik(donem, "sha"), "commit")
    y = _yapi({})
    y["nasdaq"]["kollar"] = [{"ad": "d:esit", "strateji": "esit_agirlik", "parametre": {"filtre_gun": 200, "aylik": True}}]
    d = nd.NasdaqDugumu(PaperDefter(m, "test"), nd.ayarlar(y), SahteKaynak(depo), depo, lambda: kayit,
                        saat=lambda: CUMA_KARAR / 1000)
    d.ac()
    r = d.tur()["karar"]["d:esit"]
    assert r["emir"] == 100 and r["onay"] == 100 and not r["ret"]
