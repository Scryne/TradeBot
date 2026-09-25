"""Kalıcı parity testi (Final Doküman §7, Spike 02): aynı saf çekirdek, vektörel motor ↔ NautilusTrader.

Sentetik 1 dk veri (90 gün, rastgele yürüyüş). Karar günlük; dolum sinyalden sonraki ilk dakikanın kapanışında.
Kararlar, işlem sayısı ve dolum fiyatları BİREBİR aynı olmalı; son özkaynak (nakit tamponu ve miktar yuvarlaması
dışında) aynı olmalı.
"""
import numpy as np
import polars as pl
import pytest

from tradebot.arastirma.backtest import calistir as vektorel
from tradebot.arastirma.maliyet import MaliyetModeli
from tradebot.arastirma.nautilus_kopru import NAKIT_TAMPONU, calistir
from tradebot.cekirdek import Barlar, StratejiTanimi
from tradebot.cekirdek.ornek import sma_kesisim
from tradebot.veri.depo import turet

GUN = 86_400_000


@pytest.fixture(scope="module")
def dakika():
    rng = np.random.default_rng(42)
    n = 90 * 1440
    t0 = 1_704_067_200_000  # 2024-01-01
    lr = rng.normal(0, 0.0008, n) + np.sin(np.arange(n) / 15000) * 0.00005  # rejimli: kesişim üretsin
    c = 40_000 * np.exp(np.cumsum(lr))
    o = np.r_[c[0], c[:-1]]
    return pl.DataFrame({"acilis_ms": t0 + np.arange(n, dtype=np.int64) * 60_000, "open": np.round(o, 2),
                         "high": np.round(np.maximum(o, c) * 1.0002, 2), "low": np.round(np.minimum(o, c) * 0.9998, 2),
                         # hacim büyük: emir barın tek fiyat noktasında dolsun
                         "close": np.round(c, 2), "volume": np.round(rng.uniform(500, 2000, n), 5)})


def test_parity_gunluk_karar_dakikalik_yurutme(dakika):
    tanim = StratejiTanimi("sma", "trend", sma_kesisim, {"hizli": 3, "yavas": 10})
    gunluk = turet(dakika, GUN).sort("acilis_ms")
    ilk_dk = dakika.group_by((pl.col("acilis_ms") // GUN * GUN).alias("g")).agg(pl.col("close").first()).sort("g")
    b = Barlar.sozlukten({"t": gunluk["acilis_ms"], "open": gunluk["open"], "high": gunluk["high"],
                          "low": gunluk["low"], "close": gunluk["close"], "volume": gunluk["volume"]})
    sinyal = tanim.sinyal(b)

    n = calistir(dakika, tanim)
    L = min(len(n["kararlar"]), len(sinyal))
    assert L >= 88
    np.testing.assert_array_equal(n["kararlar"][:L], sinyal[:L])  # 1) kararlar birebir

    degisim = np.flatnonzero(np.diff(np.r_[0.0, sinyal[:L - 1]]) != 0)  # dolum: sinyal değişiminin ertesi günü
    beklenen = ilk_dk["close"].to_numpy()[degisim + 1]
    assert len(n["dolum_fiyat"]) == len(beklenen) >= 2                  # 2) işlem sayısı
    np.testing.assert_allclose(n["dolum_fiyat"], beklenen, rtol=0, atol=1e-9)  # 3) dolum fiyatları

    # 4) özkaynak: vektörel motor, yürütme fiyatı = ertesi günün ilk dakika kapanışı; bant büyük = adedi tut
    #    (Nautilus stratejisi yalnız sinyal değişince işlem yapar). Nautilus adedi karar kapanışıyla nakdin %98'i
    #    olarak hesaplayıp ertesi dakikadan alır → etkin giriş ağırlığı = 0,98 × dolum / karar kapanışı.
    fiyat = ilk_dk["close"].to_numpy()[:L]
    kapanis = gunluk["close"].to_numpy()[:L]
    sonraki = np.r_[fiyat[1:], fiyat[-1]]
    etkin = np.zeros(L)
    for i in range(L):  # giriş ağırlığı yalnız girişte belirlenir, pozisyon boyunca sabit (hedef değişmesin)
        if sinyal[i] > 0:
            etkin[i] = etkin[i - 1] if i > 0 and sinyal[i - 1] > 0 else NAKIT_TAMPONU * sonraki[i] / kapanis[i]
    v = vektorel(gunluk["acilis_ms"].to_numpy()[:L], fiyat, etkin, MaliyetModeli("t", 10, 0, 0), bant=1.0)
    son_kapanis = float(kapanis[-1])
    r_son = fiyat[-1] / fiyat[-2] - 1
    w_son = v.pozisyon[-1] * (1 + r_son) / (1 + v.pozisyon[-1] * r_son)  # son bardan sonra kaymış ağırlık
    oz_n = (n["nakit"] + n["adet"] * son_kapanis) / 100_000
    oz_v = float(v.ozkaynak[-1]) * (1 + w_son * (son_kapanis / fiyat[-1] - 1))
    assert oz_n == pytest.approx(oz_v, rel=1e-5)  # kalan: 0,00001 BTC adet yuvarlaması
