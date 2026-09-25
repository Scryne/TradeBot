import math

import numpy as np
import pytest

from tradebot.arastirma import dogrulama as dg


def test_psr_normal_ve_esik():
    assert dg.psr(0.0, 0.0, 100) == pytest.approx(0.5)
    assert dg.psr(0.1, 0.0, 1000) > 0.99
    assert dg.psr(0.1, 0.0, 1000, carpiklik=-3, basiklik=10) < dg.psr(0.1, 0.0, 1000)  # sol kuyruk güveni düşürür


def test_dsr_makale_ornegi():
    """Bailey & López de Prado (2014) sayısal örneği: yıllık SR 2,5, T=1250 gün, N=100 deneme,
    yıllık SR varyansı 0,5, çarpıklık −3, basıklık 10 → DSR ≈ 0,90."""
    gun = 250
    d = dg.dsr(sr=2.5 / math.sqrt(gun), t=1250, deneme=100, sr_varyansi=0.5 / gun, carpiklik=-3, basiklik=10)
    assert d == pytest.approx(0.90, abs=0.01)


def test_beklenen_max_sr_denemeyle_artar():
    a, b = dg.beklenen_max_sr(10, 0.01), dg.beklenen_max_sr(1000, 0.01)
    assert 0 < a < b and dg.beklenen_max_sr(1, 0.01) == 0.0


def test_dsr_sans_eseri_kazanani_eler():
    """1000 rastgele (sıfır beklentili) stratejinin en iyisi, deneme sayısı hesaba katılınca anlamsız çıkmalı."""
    rng = np.random.default_rng(7)
    getiri = rng.normal(0, 0.02, (1000, 260))
    sr = getiri.mean(axis=1) / getiri.std(axis=1, ddof=1)
    en_iyi = int(np.argmax(sr))
    ham = dg.psr(sr[en_iyi], 0.0, 260)
    duzeltilmis = dg.dsr(sr[en_iyi], 260, 1000, float(np.var(sr, ddof=1)))
    assert ham > 0.99 and duzeltilmis < 0.8


def test_walk_forward_is_secimi_ve_oos():
    t = np.arange(400, dtype=np.int64) * 86_400_000
    iyi_sonra = np.r_[np.full(200, -0.001), np.full(200, 0.002)]  # IS'te kötü, OOS'ta iyi
    iyi_once = np.r_[np.full(200, 0.002), np.full(200, -0.001)]
    kosular = {"A": {"net": iyi_once, "pozisyon": np.ones(400)}, "B": {"net": iyi_sonra, "pozisyon": np.zeros(400)}}
    r = dg.walk_forward(t, kosular, is_ms=100 * 86_400_000, oos_ms=100 * 86_400_000,
                        puan=lambda tt, n: float(np.mean(n)), taraf_maliyet=0.001)
    assert r["pencere"] == 3 and [s["secilen"] for s in r["secimler"]] == ["A", "A", "B"]
    assert len(r["net"]) == 300 and r["net"][0] == pytest.approx(0.002)  # OOS [100,200): A
    assert r["net"][200] == pytest.approx(0.002 - 0.001)  # A → B geçişi: |0 − 1| × maliyet


def test_plato():
    uzay = {"a": [1, 2, 3], "b": [10, 20]}
    k = lambda p: f"{p['a']}-{p['b']}"  # noqa: E731
    genis = {k(p): 1.0 for p in dg.izgara(uzay)} | {"2-10": 1.2}
    sivri = {k(p): 0.0 for p in dg.izgara(uzay)} | {"2-10": 1.2}
    assert dg.plato(uzay, genis, k)["plato_var"] and not dg.plato(uzay, sivri, k)["plato_var"]
    assert dg.plato(uzay, genis, k)["komsu_sayisi"] == 3


def test_yillik_kirilim():
    t = np.array(["2023-06-01", "2023-07-01", "2024-01-02"], dtype="datetime64[ms]").astype(np.int64)
    r = dg.yillik_kirilim(t, np.array([0.1, 0.1, -0.5]))
    assert r[2023] == pytest.approx(0.21) and r[2024] == pytest.approx(-0.5)
