"""Dalga 4 opsiyon motoru: fiyatlama, deltadan kullanım fiyatı, tanımlı risk, aleyhte maliyet, yüzey kovaları."""
from datetime import UTC, datetime

import pytest

from tradebot.arastirma import opsiyon as op
from tradebot.veri import deribit as db

S, T = 50_000.0, 7 / 365


def test_put_call_paritesi_ve_delta_tersi():
    K = 52_000.0
    assert op.bs(S, K, T, 0.6, "C") - op.bs(S, K, T, 0.6, "P") == pytest.approx(S - K, rel=1e-9)
    for tur, h in (("P", 0.25), ("P", 0.10), ("C", 0.25), ("C", 0.10)):
        K = op.deltadan_kullanim(S, T, 0.6, tur, h)
        assert abs(db.delta(S, K, T, 0.6, tur)) == pytest.approx(h, abs=1e-9)
        assert (K < S) if tur == "P" else (K > S)


def _yuzey(iv=60.0):
    g = int(datetime(2024, 3, 1, 8, 5, tzinfo=UTC).timestamp() * 1000)
    return {"giris_ms": g, "vade_ms": g - 5 * 60_000 + 7 * 86_400_000, "endeks": S, "atm": iv, "p25": iv, "p10": iv,
            "c25": iv, "c10": iv}


def test_condor_yerinde_kazanir_cokuste_risk_kadar_kaybeder():
    m = op.Maliyet()
    yer = op.hafta(_yuzey(), S, "iron_condor", 0.02, m)
    cokus = op.hafta(_yuzey(), S * 0.7, "iron_condor", 0.02, m)
    patlama = op.hafta(_yuzey(), S * 1.3, "iron_condor", 0.02, m)
    assert yer.kurulmadi is None and 0 < yer.getiri < 0.02
    # tanımlı risk: kayıp hiçbir zaman riski aşmaz; geniş kanat tarafında (lognormal: call kanadı) riske yaklaşır
    assert -0.0202 <= cokus.getiri < 0 and -0.0202 <= patlama.getiri < 0   # teslim ücreti vadedeki fiyattan: ≤ %1 pay
    assert min(cokus.getiri, patlama.getiri) == pytest.approx(-0.02, abs=0.002)
    assert op.hafta(_yuzey(), S * 0.7, "call_spread", 0.02, m).getiri > 0   # call spread düşüşte kazanır
    assert 0 < yer.nominal < 3


def test_maliyet_aleyhte_ve_eksik_veride_kurulmaz():
    ucuz = op.hafta(_yuzey(), S, "put_spread", 0.02, op.Maliyet(0, 0, 0, 0))
    pahali = op.hafta(_yuzey(), S, "put_spread", 0.02, op.Maliyet().kat(2))
    assert ucuz.getiri > op.hafta(_yuzey(), S, "put_spread", 0.02, op.Maliyet()).getiri > pahali.getiri
    y = _yuzey() | {"p10": None}
    assert op.hafta(y, S, "put_spread", 0.02, op.Maliyet()).kurulmadi == "eksik veri"
    assert op.hafta(_yuzey(), None, "put_spread", 0.02, op.Maliyet()).kurulmadi == "eksik veri"


def test_yuzey_kovalari_ve_enstruman_adi():
    vade = datetime(2022, 3, 11, 8, tzinfo=UTC)
    assert db.enstruman_coz("BTC-11MAR22-42000-P") == (vade, 42000.0, "P")
    t0 = int(datetime(2022, 3, 4, 8, 10, tzinfo=UTC).timestamp() * 1000)
    T_ = (vade.timestamp() * 1000 - t0) / 1000 / db.YIL_SN

    def islem(K, tur, iv):
        return {"instrument_name": f"BTC-11MAR22-{int(K)}-{tur}", "iv": iv, "index_price": S, "timestamp": t0}
    kp25 = op.deltadan_kullanim(S, T_, 0.70, "P", 0.25)
    kc10 = op.deltadan_kullanim(S, T_, 0.55, "C", 0.10)
    x = [islem(S, "C", 60)] * 3 + [islem(kp25, "P", 70)] * 3 + [islem(kc10, "C", 55)] * 3 + [islem(S, "P", 61)] * 2
    x += [{"instrument_name": "BTC-18MAR22-50000-C", "iv": 99, "index_price": S, "timestamp": t0}] * 5   # başka vade
    y = db.yuzey(x, vade)
    assert y["atm"] == pytest.approx(60.0) and y["p25"] == pytest.approx(70) and y["c10"] == pytest.approx(55)
    assert y["p10"] is None and y["c25"] is None and y["endeks"] == S
    assert len(db.cumalar(datetime(2024, 1, 1, tzinfo=UTC), datetime(2024, 2, 1, tzinfo=UTC))) == 4
