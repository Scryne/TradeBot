"""Dalga 6 kilit açılımı: olay seçimi, piyasa nötr kısa backtest'i, funding, tavan, sayfa ve sembol ayrıştırma."""
import json

import numpy as np
import polars as pl
import pytest

from tradebot.arastirma import kilit as kl
from tradebot.veri import binance_vadeli as bv
from tradebot.veri import kilit as vk

G = 86_400_000
T0 = 1_700_006_400_000 // G * G


def test_olaylar_toplanir_ve_suzulur():
    t = pl.DataFrame({"sembol": ["A", "A", "A", "B", "C"], "zaman_ms": [T0 + 3600_000, T0 + 7200_000, T0, T0, T0],
                      "kategori": ["insiders", "privateSale", "airdrop", "insiders", "insiders"],
                      "oran": [0.006, 0.006, 0.5, 0.004, 0.02]})
    e = kl.olaylar(t, ["insiders", "privateSale"], 0.01)
    assert e["sembol"].to_list() == ["A", "C"] and e["oran"][0] == pytest.approx(0.012)
    assert e["kategori"][0] == "insiders+privateSale"


def _bar(fiyat):
    return pl.DataFrame({"acilis_ms": [T0 + i * G for i in range(len(fiyat))], "open": fiyat, "high": fiyat,
                         "low": fiyat, "close": fiyat, "volume": [1.0] * len(fiyat)})


def test_kisa_bacak_dususten_kazanir_funding_alir_btc_notr():
    n = 40
    token = _bar(list(100 * 0.99 ** np.arange(n)))          # her gün −%1
    btc = _bar([50_000.0] * n)
    fund = pl.DataFrame({"zaman_ms": [T0 + i * G for i in range(n)], "oran": [0.0001] * n})
    ev = pl.DataFrame({"sembol": ["TKN"], "gun_ms": [T0 + 20 * G], "oran": [0.05], "kategori": ["insiders"]})
    a = kl.KilitAyar(giris=-7, cikis=0, notional=0.10)
    seri, o = kl.kos(ev, {"TKN": token}, {"TKN": fund}, btc, pl.DataFrame(), a, T0, T0 + n * G)
    birim = 7 * 0.01 + 7 * 0.0001 - 2 * (a.ucret + a.kayma_token) - 2 * (a.ucret + a.kayma_btc)
    assert o["getiri"][0] == pytest.approx(birim, rel=1e-3)
    assert seri["getiri"].sum() == pytest.approx(0.10 * birim, rel=1e-3)   # portföy: notional × birim
    assert len(seri) == 7 and seri["brut"].max() == pytest.approx(0.2)


def test_eksik_perp_fiyat_ve_tavan():
    btc = _bar([1.0] * 60)
    ev = pl.DataFrame({"sembol": ["YOK", "EKS"] + [f"T{i}" for i in range(20)],
                       "gun_ms": [T0 + 30 * G] * 22, "oran": [0.05] * 22, "kategori": ["insiders"] * 22})
    barlar = {"EKS": _bar([1.0] * 10)} | {f"T{i}": _bar([1.0] * 60) for i in range(20)}
    seri, o = kl.kos(ev, barlar, {}, btc, pl.DataFrame(), kl.KilitAyar(notional=0.10), T0, T0 + 60 * G)
    neden = dict(zip(o["sembol"].to_list(), o["kurulmadi"].to_list(), strict=True))
    assert neden["YOK"] == "perp yok" and neden["EKS"] == "fiyat eksik"
    assert seri["brut"].max() <= 3.0 + 1e-9 and "tavan" in neden.values()   # 20 olay × 0,2 brüt = 4 > 3


def test_defillama_sayfasi_ve_carpanli_sembol():
    veri = {"props": {"pageProps": {"data": [{"tSymbol": "tia", "gecko_id": "celestia", "name": "Celestia",
                                              "maxSupply": 1000.0, "events": [
                                                  {"unlockType": "cliff", "timestamp": 1700000000, "category": "insiders",
                                                   "noOfTokens": [30]},
                                                  {"unlockType": "linear", "timestamp": 1700000000, "noOfTokens": [0, 5]}]}]}}}
    html = f'<html><script id="__NEXT_DATA__" type="application/json">{json.dumps(veri)}</script></html>'.encode()
    t = vk.coz(html)
    assert t.height == 1 and t["sembol"][0] == "TIA" and t["oran"][0] == pytest.approx(0.03)
    info = {"symbols": [{"contractType": "PERPETUAL", "quoteAsset": "USDT", "baseAsset": "1000PEPE", "symbol": "1000PEPEUSDT",
                         "status": "TRADING"},
                        {"contractType": "PERPETUAL", "quoteAsset": "USDT", "baseAsset": "TIA", "symbol": "TIAUSDT",
                         "status": "TRADING"}]}
    p = bv.usdt_perpler(lambda u: json.dumps(info).encode())
    assert p["PEPE"]["sembol"] == "1000PEPEUSDT" and p["TIA"]["sembol"] == "TIAUSDT"
