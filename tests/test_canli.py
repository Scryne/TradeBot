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
    assert len(ks) == 10 and sum(k.jev for k in ks) == 5
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
