"""Nasdaq-100 point-in-time üyelik, dönem kapsamı ve dalga 19 hisse stratejileri."""
from datetime import UTC, datetime

import numpy as np
import polars as pl
import pytest

from tradebot.cekirdek import aileler as al
from tradebot.cekirdek import hisse as hs
from tradebot.veri import nasdaq as nqv
from tradebot.veri import nasdaq100 as nq

GUN = 86_400_000


def _ms(g: str) -> int:
    return int(datetime.fromisoformat(g).replace(tzinfo=UTC).timestamp() * 1000)


Y2020 = b"""---
year: 2020
tickers_on_Jan_1:
  - AAPL
  - FB
  - ON
changes:
  "2020-03-02":
    difference:
      - ON
    union:
      - ZM
"""
Y2021 = b"""---
year: 2021
tickers_on_Jan_1:
  - AAPL
  - FB
  - ZM
changes:
  "2021-06-09":
    difference:
      - FB
    union:
      - META
"""


def test_on_sembolu_bool_olmaz_ve_donemler():
    yil, ocak, _ = nq.yil_coz(Y2020)
    assert yil == 2020 and ocak == ["AAPL", "FB", "ON"]          # YAML 1.1'de ON → True olurdu
    ds = nq.donemler({2020: Y2020, 2021: Y2021})
    d = {(x.sembol, x.bas_ms, x.bit_ms) for x in ds}
    assert ("ON", _ms("2020-01-01"), _ms("2020-03-02")) in d
    assert ("ZM", _ms("2020-03-02"), None) in d
    assert ("FB", _ms("2020-01-01"), _ms("2021-06-09")) in d and ("META", _ms("2021-06-09"), None) in d


def test_yil_basi_tutarsizsa_hata():
    bozuk = Y2021.replace(b"  - ZM\n", b"  - ON\n", 1)
    with pytest.raises(ValueError, match="tutarsız"):
        nq.donemler({2020: Y2020, 2021: bozuk})


def test_esleme_ve_dislama_kimlik_donemleri():
    ds = nq.donemler({2020: Y2020, 2021: Y2021})
    k = nq.kimlik_donemleri(ds, {"sembol_esleme": {"FB": "META"}, "dislanan": {"ON": "test"}})
    assert k["NASDAQ:META"] == [(_ms("2020-01-01"), None)]       # FB ve META bitişik: tek dönem
    assert "NASDAQ:ON" not in k and "NASDAQ:FB" not in k


def test_uyelik_ve_kapsam_maskesi_yeniden_kullanilan_sembol():
    t = np.arange(_ms("2020-01-01"), _ms("2020-03-01"), GUN, dtype=np.int64)
    donem = {"A": [(_ms("2020-01-10"), _ms("2020-02-10"))], "B": [(_ms("2020-01-05"), None)]}
    um = nq.uyelik_maskesi(t, ["A", "B"], donem)
    assert um[:, 0].sum() == 31 and not um[8, 0] and um[9, 0]
    bar = np.zeros_like(um)
    bar[:, 0] = True                                   # A'nın verisi baştan var: dönem kapsanır
    bar[40:, 1] = True                                 # B'nin verisi dönem başından 36 gün sonra başlıyor: başka varlık
    km = nq.kapsam_maskesi(um, bar, tolerans_gun=10)
    assert (km[:, 0] == um[:, 0]).all() and not km[:, 1].any()
    rap = nq.kapsam_raporu(t, um, km)
    assert rap[2020]["kapsanan"] < 1.0


def _panel(n=600, k=12, tohum=3, sigma=0.015):
    rng = np.random.default_rng(tohum)
    t = _ms("2018-01-01") + np.arange(n, dtype=np.int64) * GUN
    mu = np.linspace(-0.0005, 0.001, k)                 # son hisseler daha güçlü trendli
    c = 100 * np.exp(np.cumsum(rng.normal(mu, sigma, (n, k)), axis=0))
    ev = np.ones((n, k), dtype=bool)
    ev[:200, 0] = False                                 # sonradan eklenen
    ev[400:, 1] = False                                 # sonradan çıkarılan
    return al.Panel(t, c, ev)


@pytest.mark.parametrize("fonk,p", [
    (hs.hisse_momentum, {"geriye": 126, "atla": 21, "ust_n": 4, "filtre": 100}),
    (hs.kisa_donus, {"geriye": 5, "alt_n": 3, "trend": 100, "filtre": 0}),
    (hs.dusuk_oynaklik, {"pencere": 60, "ust_n": 4, "filtre": 100}),
    (hs.esit_agirlik, {"filtre": 100}),
])
def test_hisse_stratejileri_nedensel_uzun_ve_evren_ici(fonk, p):
    pn = _panel()
    al.panel_nedensellik_testi(fonk, pn, deneme=5, **p)
    w = fonk(pn, **p)
    assert (w >= 0).all() and (w.sum(axis=1) <= 1 + 1e-9).all()
    assert (w[~pn.evrende] == 0).all()


def test_momentum_guclu_hisseleri_secer_ve_ayda_bir_degisir():
    pn = _panel(sigma=0.003)
    w = hs.hisse_momentum(pn, geriye=126, atla=21, ust_n=3, filtre=0)
    son = np.flatnonzero(w[-1])
    assert set(son) <= set(range(6, 12))               # güçlü trendli yarıdan
    degisim = np.flatnonzero((np.abs(np.diff(w, axis=0)) > 0).any(axis=1)) + 1
    ay_bas = np.flatnonzero(hs.ay_basi(pn.t))
    assert set(degisim) <= set(ay_bas) | {201, 400}    # yalnız ay başı ve evren değişimi


def test_piyasa_filtresi_dususte_nakit():
    n, k = 400, 5
    t = _ms("2019-01-01") + np.arange(n, dtype=np.int64) * GUN
    c = np.vstack([100 * 1.002 ** np.arange(250)[:, None] * np.ones((1, k)),
                   100 * 1.002 ** 249 * 0.99 ** np.arange(1, 151)[:, None] * np.ones((1, k))])
    pn = al.Panel(t, c, np.ones((n, k), dtype=bool))
    w = hs.esit_agirlik(pn, filtre=100)
    assert w[240].sum() == pytest.approx(1.0) and w[-1].sum() == 0.0
    assert hs.esit_agirlik(pn, filtre=0)[-1].sum() == pytest.approx(1.0)   # filtresiz: al-tut


def test_grup_hazirla_nasdaq_uyelik(tmp_path):
    from tradebot.arastirma import turnuva as tv
    from tradebot.veri.depo import BarDepo

    depo = BarDepo(tmp_path)
    t = np.arange(_ms("2020-01-01"), _ms("2020-06-01"), GUN, dtype=np.int64)
    for s in ("AAPL", "ZM"):
        c = np.linspace(10, 20, len(t))
        depo.yaz(f"NASDAQ:{s}", "1d", pl.DataFrame({"acilis_ms": t, "open": c, "high": c, "low": c, "close": c,
                                                     "volume": np.full(len(t), 1e6)}))
    uy = nqv.Uyelik({"NASDAQ:AAPL": [(_ms("2020-01-01"), None)], "NASDAQ:ZM": [(_ms("2020-03-02"), None)]}, "abc")
    nqv.uyelik_yaz(tmp_path, uy, "commit")
    kayit = {f"NASDAQ:{s}": {"piyasa": "NASDAQ", "sinif": "hisse", "takvim": "XNYS"} for s in ("AAPL", "ZM")}
    h = tv.grup_hazirla(depo, kayit, {"dinamik": "nasdaq", "uyelik": "nasdaq100", "asgari_gecmis_gun": 5}, "1d")
    j = h.g.kimlikler.index("NASDAQ:ZM")
    ilk = int(np.flatnonzero(h.evrende[:, j])[0])
    assert h.g.t[ilk] >= _ms("2020-03-02")             # üyelikten önce evrende değil
    assert h.modeller[0].ad == "nasdaq_hisse"


def test_dalga19_kol_kos_uctan_uca(ayar, monkeypatch):
    """Sentetik 12 hisse, 5 yıl, değişen üyelik: turnuva hunisi Nasdaq grubunda uçtan uca çalışır."""
    from tradebot.arastirma import defter as df
    from tradebot.arastirma import turnuva as tv
    from tradebot.db import metadata, motor
    from tradebot.veri.depo import BarDepo

    e = motor(ayar)
    metadata.create_all(e)
    monkeypatch.setattr(df, "kod_surumu", lambda: "abc1234")
    depo = BarDepo(ayar.veri_dizini)
    pn = _panel(n=5 * 252, k=12)
    t = _ms("2015-01-01") + np.arange(len(pn.t), dtype=np.int64) * GUN
    donem = {}
    for j in range(12):
        c = pn.close[:, j]
        depo.yaz(f"NASDAQ:S{j}", "1d", pl.DataFrame({"acilis_ms": t, "open": c, "high": c * 1.01, "low": c * 0.99,
                                                       "close": c, "volume": np.full(len(t), 1e6)}))
        donem[f"NASDAQ:S{j}"] = [(int(t[0]) if j else int(t[300]), None if j != 1 else int(t[900]))]
    nqv.uyelik_yaz(ayar.veri_dizini, nqv.Uyelik(donem, "sha"), "commit")
    kayit = {k: {"piyasa": "NASDAQ", "sinif": "hisse", "takvim": "XNYS"} for k in donem}
    d = tv.dalga_oku(__import__("pathlib").Path("config/turnuva/dalga19_nasdaq.yaml"))
    defter = df.Defter(e)
    grup = d["gruplar"]["nasdaq100"]
    h = tv.grup_hazirla(depo, kayit, grup, "1d")
    for k in tv.kollar(d):
        aile = tv.STRATEJILER[k["strateji"]][0]
        defter.plan_ac(k["plan"], aile, "sentetik", k["izgara"], ["kol:nasdaq100"], "ölçüt")
        r = tv.kol_kos(defter, h, k["plan"], k["strateji"], "nasdaq100", k["izgara"], "long", d["_ayar"],
                       en_fazla=k["en_fazla"])
        assert r["karar"] in {"B", "KALDI"}               # grup en fazla B
        assert r["en_iyi"]["maruziyet"] <= 1.0 + 1e-9     # nakit hesap: brüt ≤ 1x
    assert defter.deneme_sayisi("kesitsel_momentum") == 8


def test_cevir_sifir_kapali_kalir():
    from tradebot.arastirma.turnuva import cevir

    assert cevir({"filtre_gun": 0, "geriye_gun": 0.2, "ust_n": 5}, 1.0) == {"filtre": 0, "geriye": 1, "ust_n": 5}
