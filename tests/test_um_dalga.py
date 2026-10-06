import numpy as np
import pytest

from tradebot.arastirma import um_dalga as um
from tradebot.cekirdek import funding_kesit as fk
from tradebot.cekirdek import oi_donus as od

H = um.SAAT_MS
G = um.GUN_MS
PZT = 1_704_067_200_000          # 2024-01-01 Pazartesi 00:00 UTC
MAL0 = {"ucret": 0.0, "kayma_token": 0.0, "kayma_btc": 0.0}


def test_ozellik_bozma_gelecegi_gormez():
    rng = np.random.default_rng(1)
    n = od.PENCERE + 50
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, n)))
    o = np.r_[c[0], c[:-1]]
    q = np.full(n, 1e6)
    oi = 1000 + np.arange(n, dtype=float)
    t = od.PENCERE + 20
    a = od.ozellik(o, c, q, oi)
    c2, o2, oi2 = c.copy(), o.copy(), oi.copy()
    c2[t + 1:] *= 3
    o2[t + 1:] *= 0.2
    oi2[t + 1:] = 1.0
    b = od.ozellik(o2, c2, q, oi2)
    for k in ("z", "doi", "hacim"):
        assert np.allclose(a[k][: t + 1], b[k][: t + 1], equal_nan=True)


def test_olay_kosullari():
    k = od.DonusKural(k=4, oi_esik=-0.05, tut=4, asgari_hacim=1e6)
    assert od.olay_mu(-5, -0.06, 2e6, k)
    assert not od.olay_mu(-5, -0.04, 2e6, k)          # OI yeterince düşmedi
    assert not od.olay_mu(-3, -0.10, 2e6, k)          # fiyat yeterince düşmedi
    assert not od.olay_mu(-5, -0.10, 5e5, k)          # hacim yetersiz
    assert od.olay_mu(-5, np.nan, 2e6, od.DonusKural(k=4, oi_esik=None, asgari_hacim=1e6))


def _aday(t, s, acilis, funding=()):
    a = np.r_[acilis, np.full(um.AZAMI_TUT + 1 - len(acilis), np.nan)]
    return um.Aday(t, s, -6.0, -0.2, a, tuple(funding))


def _btc(t0, n, fiyat=100.0):
    return {"t0": t0, "open": np.full(n, fiyat), "fz": np.array([], dtype=np.int64), "fo": np.array([])}


def test_donus_tek_olay_getirisi_ve_maliyet():
    bas = PZT
    e = _aday(bas, "X", [100.0, 102.0, 103.0], funding=[(bas + 2 * H, 0.001)])   # giriş bas+1h, çıkış bas+3h
    kural = od.DonusKural(k=4, oi_esik=-0.05, tut=2, asgari_hacim=0)
    mal = {"ucret": 0.0005, "kayma_token": 0.0005, "kayma_btc": 0.0}
    t, r, birim, km = um.donus_kos([e], _btc(bas, 100), kural, False, 0.1, 1.0, mal, bas, bas + 10 * H)
    # birim: +2% − funding 0,1% (uzun öder) − 2 × 0,1% maliyet, +1% ikinci saat
    assert birim == [pytest.approx(0.02 - 0.001 - 0.001 + 0.01 - 0.001)]
    assert r[1] == pytest.approx(0.1 * (0.02 - 0.001 - 0.001))
    assert r[2] * (1 + r[1]) == pytest.approx(0.1 * (0.01 - 0.001))     # nominal girişteki özkaynakla sabit
    assert r[0] == 0 and r[3:].sum() == 0 and km == {}


def test_donus_hedge_btc_cikarir_ve_tavan():
    bas = PZT
    btc = _btc(bas, 100)
    btc["open"][1:] = np.r_[100.0, 101.0, np.full(97, 101.0)]
    e1 = _aday(bas, "X", [100.0, 102.0])
    e2 = um.Aday(bas, "Y", -5.0, -0.2, e1.acilis, ())
    kural = od.DonusKural(k=4, oi_esik=-0.05, tut=1, asgari_hacim=0)
    _, r, birim, km = um.donus_kos([e1, e2], btc, kural, True, 0.3, 0.6, MAL0, bas, bas + 10 * H)
    assert birim == [pytest.approx(0.02 - 0.01)]
    assert km == {"tavan": 1}                         # ikinci olay 2 × 0,3 brüt daha ister, tavan 0,6


def test_donus_ayni_sembol_acikken_yeni_olay_yok():
    bas = PZT
    e1 = _aday(bas, "X", [100.0, 101.0, 102.0, 103.0])
    e2 = _aday(bas + H, "X", [101.0, 102.0, 103.0])
    kural = od.DonusKural(k=4, oi_esik=-0.05, tut=3, asgari_hacim=0)
    _, _, birim, km = um.donus_kos([e1, e2], _btc(bas, 100), kural, False, 0.1, 1.0, MAL0, bas, bas + 10 * H)
    assert len(birim) == 1 and km == {"sembol_acik": 1}


def test_agirliklar_secim_ve_sabit_haric():
    hacim = {s: float(100 - i) for i, s in enumerate("ABCDEFGH")} | {"USDC": 1e9}
    fon = {"A": 0.01, "B": -0.02, "C": 0.03, "D": 0.0, "E": -0.01, "F": 0.02, "G": 0.5, "H": -0.5, "USDC": 9.0}
    w = fk.agirliklar(hacim, fon, fk.KesitKural(pencere=7, n=2, evren=6, brut=1.0))
    # evren: hacimce ilk 6 (A–F, USDC hariç); uzun en düşük funding B, E; kısa en yüksek C, F
    assert w == {"B": 0.25, "E": 0.25, "C": -0.25, "F": -0.25}
    assert fk.agirliklar({"A": 1.0}, {"A": 0.0}, fk.KesitKural(n=1, evren=2)) == {}
    with pytest.raises(ValueError):
        fk.KesitKural(brut=3.5)


def test_kesit_kos_funding_ve_fiyat():
    gun = [PZT + i * G for i in range(-40, 3)]
    fiyat, fund = {}, {}
    for s, f in (("L", -0.001), ("K", 0.002)):
        fiyat[s] = {d: (100.0, 100.0, 1e6) for d in gun}
        fund[s] = {d: f for d in gun}
    fiyat["L"][PZT + G] = (110.0, 110.0, 1e6)     # L ikinci gün açılışı +%10
    kural = fk.KesitKural(pencere=7, n=1, evren=2, brut=1.0)
    t, r, devir, km = um.kesit_kos(fiyat, fund, kural, MAL0, PZT, PZT + 2 * G)
    # uzun L 0,5 (funding −0,001 → uzun alır), kısa K 0,5 (funding +0,002 → kısa alır)
    assert r[0] == pytest.approx(0.5 * 0.10 + 0.5 * 0.001 + 0.5 * 0.002)
    assert devir == [pytest.approx(1.0)] and km == {}


def test_kesit_kos_dengeleme_maliyeti_getiriye_yazilir():
    gun = [PZT + i * G for i in range(-40, 3)]
    fiyat = {s: {d: (100.0, 100.0, 1e6) for d in gun} for s in ("L", "K")}
    fund = {"L": {d: -0.001 for d in gun}, "K": {d: 0.002 for d in gun}}
    kural = fk.KesitKural(pencere=7, n=1, evren=2, brut=1.0)
    _, r0, _, _ = um.kesit_kos(fiyat, fund, kural, MAL0, PZT, PZT + 2 * G)
    _, r1, _, _ = um.kesit_kos(fiyat, fund, kural, {"ucret": 0.0005, "kayma_token": 0.001}, PZT, PZT + 2 * G)
    assert r0[0] - r1[0] == pytest.approx(1.0 * 0.0015)     # devir 1x × (ücret + kayma)
