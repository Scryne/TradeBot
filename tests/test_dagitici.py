"""Sermaye dağıtıcı (Faz 7): ERC, küçültülmüş üstünlük, yarım Kelly ≤ 3x, kademe, B = 0, haftalık kayıt."""
import math

import numpy as np
import pytest
from sqlalchemy import create_engine

from tradebot.canli import dagitici as dg
from tradebot.canli.defter import PaperDefter
from tradebot.canli.kollar import kollar
from tradebot.db import metadata

GUN = dg.GUN_MS
T0 = dg.hafta_basi(1_790_000_000_000)


def seri(r: np.ndarray, t0: int = T0) -> dict[int, float]:
    return {t0 + i * GUN: float(x) for i, x in enumerate(r)}


def test_hafta_basi_pazartesi():
    import datetime as dt
    for ms in (1_790_510_475_000, T0, T0 + 6 * GUN + 1):
        h = dg.hafta_basi(ms)
        assert dt.datetime.fromtimestamp(h / 1000, dt.UTC).weekday() == 0 and h <= ms < h + dg.HAFTA_MS


def test_gunluk_getiri_gun_sonu_ve_kesik():
    # işaret barın kapanışında: h. saatin barı T0 + (h+1) saatte işaretlenir; 00:00 işareti biten günündür
    isaret = [(T0 + (h + 1) * 3_600_000, 100.0 * (1.01 ** (h // 24)) + (h % 24) * 0.001) for h in range(24 * 5)]
    g = dg.gunluk_getiri(isaret, T0 + 3 * GUN)  # 3. gün ve sonrası görülmez; 2. günün 00:00 işareti de (hariç)
    assert list(g) == [T0 + GUN, T0 + 2 * GUN]
    assert all(abs(v - math.log(1.01)) < 1e-4 for v in g.values())
    g = dg.gunluk_getiri(isaret, T0 + 3 * GUN, dahil=True)
    assert list(g) == [T0 + GUN, T0 + 2 * GUN] and abs(g[T0 + 2 * GUN] - math.log(1.01)) < 1e-5


def test_kademe():
    a = dg.DagiticiAyar()
    assert [dg.kademe_orani(x, a) for x in (0, 27.9, 28, 55, 56, 84, 400)] == [0, 0, .25, .25, .5, 1, 1]


def test_yarim_kelly_ustu_yok():
    with pytest.raises(ValueError):
        dg.DagiticiAyar(kelly_kesri=1.0)


def test_erc_bagimsizda_ters_oynaklik_korelede_ceza():
    sd = np.array([0.1, 0.2, 0.4])
    w = dg.erc(np.diag(sd ** 2))
    assert np.allclose(w, (1 / sd) / (1 / sd).sum(), atol=1e-6)
    kor = np.array([[1, .95, 0], [.95, 1, 0], [0, 0, 1]])
    w = dg.erc(kor * 0.04)  # eşit oynaklık: korelasyonsuz üçüncü kol en büyük payı alır
    assert w[2] > w[0] and abs(w[0] - w[1]) < 1e-9 and abs(w.sum() - 1) < 1e-12


def _kollar(n=120, tohum=1, kor=0.8):
    rng = np.random.default_rng(tohum)
    ortak = rng.normal(0, 0.01, n)
    return {f"k{i}": seri(0.0006 + kor ** 0.5 * ortak + (1 - kor) ** 0.5 * rng.normal(0, 0.01, n)) for i in range(3)}


def test_dagit_b_sinifi_golge_var_katsayi_sifir():
    g = _kollar()
    s = dg.dagit(g, {k: 120 for k in g}, {k: "B" for k in g}, {k: 0.9 for k in g}, dg.DagiticiAyar())
    assert s["kaldirac"] == 0.0 and 0 < s["kaldirac_golge"] <= 3
    assert abs(sum(v["agirlik"] for v in s["kollar"].values()) - 1) < 1e-9
    assert all(v["katsayi"] == 0 for v in s["kollar"].values())
    assert 0.5 < s["korelasyon_ort"] < 1


def test_dagit_a_kademe_ve_tavan():
    g = _kollar()
    gun = {"k0": 30, "k1": 60, "k2": 90}
    s = dg.dagit(g, gun, {k: "A" for k in g}, {k: 5.0 for k in g}, dg.DagiticiAyar())  # aşırı önsel: tavana takılır
    L = s["kaldirac_golge"]
    assert L == 3.0
    for k, oran in (("k0", .25), ("k1", .5), ("k2", 1.0)):
        v = s["kollar"][k]
        assert v["kademe"] == oran and abs(v["katsayi"] - L * v["agirlik"] * oran) < 1e-12
    assert s["kaldirac"] <= 3.0


def test_dagit_negatif_tahmin_pay_almaz_ve_az_gecmis_girmez():
    g = _kollar()
    g["kotu"] = seri(np.full(120, -0.004) + np.random.default_rng(5).normal(0, 0.01, 120))
    g["yeni"] = seri(np.random.default_rng(6).normal(0, 0.01, 10))
    s = dg.dagit(g, {k: 120 for k in g}, {k: "A" for k in g}, {k: 0.0 for k in g}, dg.DagiticiAyar())
    assert s["kollar"]["kotu"]["agirlik"] == 0 and "yeni" not in s["uygun"] and s["kollar"]["yeni"]["katsayi"] == 0


def test_dagit_ortak_gecmis_yoksa_korelasyon_bir():
    rng = np.random.default_rng(2)
    g = {"a": seri(rng.normal(0.001, 0.01, 40)), "b": seri(rng.normal(0.001, 0.01, 40), T0 + 60 * GUN)}
    s = dg.dagit(g, {"a": 40, "b": 40}, {"a": "A", "b": "A"}, {"a": 1, "b": 1}, dg.DagiticiAyar())
    assert s["ortak_gun"] == 0 and s["korelasyon_ort"] == 1.0


def test_portfoy_hedef_toplam_ve_kirpma():
    h = dg.portfoy_hedef({"a": 1.0, "b": 0.5, "c": 0.0}, {"a": {"X": 0.3, "Y": 0.2}, "b": {"X": 0.4}}, ["X", "Y"],
                         0.45, long_short=False)
    assert np.allclose(h, [0.45, 0.2])


def test_defter_dagitim_haftada_bir_ve_kesik(tmp_path):
    m = create_engine(f"sqlite:///{tmp_path / 'd.db'}")
    metadata.create_all(m)
    defter = PaperDefter(m, "test")
    ks = kollar()
    pf = ks[-1]
    kaynak = [k for k in ks if k.ad in pf.parametre["kaynaklar"]]
    bas = T0 - 60 * GUN
    for k in kaynak:
        defter.kol_ac(k, bas)
    rng = np.random.default_rng(4)
    ortak = rng.normal(0.0005, 0.0015, 24 * 70)
    for k in kaynak:
        oz = 100_000 * np.exp(np.cumsum(ortak + rng.normal(0, 0.0007, len(ortak))))
        from tradebot.canli.karar import KolDurum
        for i, o in enumerate(oz):
            defter.ozkaynak_yaz(k.ad, bas + i * 3_600_000, KolDurum(ozkaynak=float(o), nakit=float(o)), {})
    s = defter.dagitim_getir(pf, kaynak, T0)
    assert s["hafta_ms"] == T0 and len(s["uygun"]) == 5
    assert all(v["gozlem"] == 60 for v in s["kollar"].values())  # hafta başından sonraki işaretler görülmez
    assert s["kaldirac"] == 0.0 and s["kaldirac_golge"] > 0     # hepsi B
    assert defter.dagitim_getir(pf, kaynak, T0) == s             # ikinci çağrı kayıttan okur
