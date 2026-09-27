"""B → A terfi değerlendirmesi: dört ölçüt (süre/kesinti, kapılar, uygulama uyumu, çelişki yok)."""
import math

import numpy as np

from tradebot.canli import dagitici as dg
from tradebot.canli import terfi

G0 = dg.hafta_basi(1_790_000_000_000)


def _gunluk(r):
    return {G0 + i * dg.GUN_MS: float(x) for i, x in enumerate(r)}


def test_haftalik_ve_kesinti():
    h = terfi.haftalik(_gunluk([0.01] * 14))
    assert list(h) == [G0, G0 + dg.HAFTA_MS] and all(abs(v - 0.07) < 1e-12 for v in h.values())
    saat = 3_600_000
    isaret = [(G0 + i * saat + 5_000, 1.0) for i in range(1, 101) if i not in (10, 11)]
    assert abs(terfi.kesinti_payi(isaret, G0, G0 + 101 * saat) - 0.02) < 1e-12
    assert terfi.en_kotu_dusus([(0, 100.0), (1, 120.0), (2, 90.0), (3, 130.0)], 100.0) == 90 / 120 - 1


def test_degerlendir_gecer_ve_kalir():
    rng = np.random.default_rng(3)
    bt = rng.normal(0.0005, 0.01, 60)
    paper = bt + rng.normal(0, 0.001, 60)                  # takip hatası ~%2
    bt_h = list(np.expm1(rng.normal(0.003, 0.03, 300)))
    r = terfi.degerlendir(_gunluk(paper), _gunluk(bt), bt_h, -0.12, 0.005, 60, 11.0, 13.0)
    assert r["gecti"], r["olcutler"]
    assert r["olcutler"]["takip_hatasi"]["deger"] < 0.05 and r["olcutler"]["takip_hatasi"]["ortak_gun"] == 60

    kotu = terfi.degerlendir(_gunluk(paper), _gunluk(bt), bt_h, -0.12, 0.005, 40, 25.0, 13.0)
    o = kotu["olcutler"]
    assert not kotu["gecti"] and not o["sure_gun"]["gecti"] and not o["yurutme_maliyeti_bps"]["gecti"]

    sapma = terfi.degerlendir(_gunluk(bt + rng.normal(0, 0.01, 60)), _gunluk(bt), bt_h, -0.12, 0.0, 60, 11.0, 13.0)
    assert not sapma["olcutler"]["takip_hatasi"]["gecti"]          # yıllık ~%19 takip hatası

    cokus = terfi.degerlendir(_gunluk(np.full(60, -0.004)), _gunluk(bt), bt_h, -0.21, 0.0, 60, 11.0, 13.0)
    assert not cokus["olcutler"]["celiski_t"]["gecti"] and cokus["olcutler"]["celiski_t"]["deger"] < -2

    maliyetsiz = terfi.degerlendir(_gunluk(paper), _gunluk(bt), bt_h, -0.12, 0.0, 60, None, 13.0)
    assert not maliyetsiz["olcutler"]["yurutme_maliyeti_bps"]["gecti"]   # ölçülemeyen maliyet geçmez
    assert math.isfinite(maliyetsiz["olcutler"]["celiski_t"]["deger"])


def test_kol_degerlendir_backtesti_birebir_izleyen_paper(tmp_path, ayar):
    import dataclasses

    from tests.test_canli import GRUP, KAYIT, kol_yap, sentetik_depo
    from tradebot.arastirma import turnuva as tv
    from tradebot.canli.defter import PaperDefter
    from tradebot.canli.karar import KolDurum
    from tradebot.db import metadata, motor

    depo, t = sentetik_depo(tmp_path, n=24 * 90)
    k = dataclasses.replace(kol_yap(), baslangic_ozkaynak=100_000.0)
    bit = int(t[-1]) + 3_600_000
    h = tv.grup_hazirla(depo, KAYIT, GRUP, "1h", bit_ms=bit)
    s = tv.kos(h, tv.hedef_uret(h, k.strateji, tv.cevir(k.parametre, 24.0), "long", k.ayar), k.ayar)
    m = motor(ayar)
    metadata.create_all(m)
    df = PaperDefter(m, "t")
    bas_i = len(s.t) - 24 * 60
    df.kol_ac(k, int(s.t[bas_i]))
    oz = s.ozkaynak / s.ozkaynak[bas_i - 1] * 100_000.0
    for i in range(bas_i, len(s.t)):                     # paper gibi: bar i'nin sonucu kapanışında işaretlenir
        df.ozkaynak_yaz(k.ad, int(s.t[i]) + 3_600_000, KolDurum(ozkaynak=float(oz[i]), nakit=float(oz[i])), {})
    r = terfi.kol_degerlendir(m, depo, KAYIT, k, bit - bit % dg.GUN_MS)  # gün sınırında değerlendir
    o = r["olcutler"]
    assert o["takip_hatasi"]["ortak_gun"] >= 55 and o["takip_hatasi"]["deger"] < 1e-9, o["takip_hatasi"]
    assert o["sure_gun"]["deger"] >= 59 and o["kesinti"]["deger"] < 0.02
