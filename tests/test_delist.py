"""Dalga 12 (arastirma/delist.py): başlık kuralı, perp kaldırma ayrıştırma, olay günü, Jev eleme, mum kırpma."""
import polars as pl
import pytest
from sqlalchemy import create_engine

from tradebot.arastirma import delist as dl
from tradebot.arastirma import kilit as kl
from tradebot.db import metadata
from tradebot.zeka import olay

G = 86_400_000
T0 = 1_700_006_400_000 // G * G


def test_spot_delist_basligi():
    assert dl.spot_delist("Binance Will Delist BCD, CND, MTH, NCASH and YOYO on 2022-03-08") == \
        ["BCD", "CND", "MTH", "NCASH", "YOYO"]
    assert dl.spot_delist("Binance Will Delist A2Z, FORTH, HOOK on 2026-04-01") == ["A2Z", "FORTH", "HOOK"]
    assert dl.spot_delist("Binance Announced the First Batch of Vote to Delist Results and Will Delist BADGER, BAL and "
                          "UFT on 2025-04-16") == ["BADGER", "BAL", "UFT"]
    assert dl.spot_delist("Binance Margin Will Delist WAN on 2026-04-10") == []
    assert dl.spot_delist("Binance Margin And Binance Loans Will Delist AEUR and AI on 2026-05-22") == []
    assert dl.spot_delist("Binance Will Delist All American-Style Daily Options") == []
    assert dl.spot_delist("Notice of Removal of Spot Trading Pairs - 2026-05-15") == []


def test_perp_kaldirma_basligi_ve_govdesi():
    assert dl.perp_delist("Binance Futures Will Delist USDⓈ-M MYROUSDT and 1000XUSDT Perpetual Contracts (2025-11-14)",
                          "") == ["MYRO", "X"]
    assert dl.perp_delist("Binance Futures Will Delist USDT-Margined ANC Perpetual Contract", "ANCUSDT kapanır") == ["ANC"]
    assert dl.perp_delist("Binance Futures Will Delist Multiple USDⓈ-M Perpetual Contracts (2026-10-05)",
                          "contracts: AAAUSDT, BBBUSDT") == ["AAA", "BBB"]
    assert dl.perp_delist("Binance Futures Will Delist COIN-M GMTUSD and DOGSUSD Perpetual Contracts", "GMTUSDT") == []
    assert dl.perp_delist("Binance Will Delist SNM, SRM and YFII on 2023-08-22", "SNMUSDT") == []


def test_olay_gunu_jev_eleme_ve_ilk_duyuru():
    spot = pl.DataFrame({"sembol": ["AAA", "BBB", "AAA"], "yayin_ms": [T0 + 23 * 3_600_000 + 59 * 60_000, T0 + 3_600_000,
                                                                       T0 + 40 * G], "metin_id": [1, 2, 3]})
    ev = dl.olaylar(spot)
    # AAA 23:59'da: 60 sn gecikme ertesi günün 00:00'ını geçer → T0 + 2G; ikinci AAA duyurusu sayılmaz
    assert ev.rows() == [("BBB", T0 + G, 1.0), ("AAA", T0 + 2 * G, 1.0)]
    jev = pl.DataFrame({"sembol": ["AAA", "BBB"], "gecerli_ms": [T0 + G, T0 + 3 * G]})
    assert dl.olaylar(spot, jev).rows() == [("AAA", T0 + 2 * G, 1.0)]       # BBB'nin vetosu pencere dışında


def test_jev_onaylari_kaldirilan_vetoyu_saymaz(tmp_path):
    m = create_engine(f"sqlite:///{tmp_path / 'j.db'}")
    metadata.create_all(m)
    olay.yaz(m, "veto", "BINANCE:AAAUSDT", T0, "A1 jev:token_delist (0.99): x", "A1_binance")
    v = olay.yaz(m, "veto", "BINANCE:BBBUSDT", T0, "A1 jev:token_delist (0.60): y", "A1_binance")
    olay.yaz(m, "veto", "BINANCE:CCCUSDT", T0, "A1 jev:usdt_pair_removed (0.9): z", "A1_binance")
    olay.kaldir(m, v, T0 + G, "yanlış", "test")
    assert dl.jev_onaylari(m).rows() == [("AAA", T0)]


def test_kirp_sifir_hacim_ve_perp_kaldirma():
    bar = pl.DataFrame({"acilis_ms": [T0 + i * G for i in range(6)], "open": [1.0] * 6, "high": [1.0] * 6,
                        "low": [1.0] * 6, "close": [1.0] * 6, "volume": [5.0, 5.0, 5.0, 5.0, 0.0, 0.0]})
    assert dl.kirp(bar, [])["acilis_ms"].to_list() == [T0 + i * G for i in range(4)]
    # duyuru 1. gün 10:00 → ilk açılış 2. gün: 2. günün mumu kalır (1→2 getirisi), sonrası kesilir
    assert dl.kirp(bar, [T0 + G + 10 * 3_600_000])["acilis_ms"].to_list() == [T0, T0 + G, T0 + 2 * G]


def test_motor_perp_kaldirilinca_kapanir():
    """Uçtan uca: olay T'de açılır, perp kaldırma duyurusuyla kırpılan mumlarda çıkıştan önce kapanır."""
    n = 12
    gun = [T0 + i * G for i in range(n)]
    tok = pl.DataFrame({"acilis_ms": gun, "open": [100.0 * 0.95 ** i for i in range(n)], "volume": [1.0] * n})
    btc = pl.DataFrame({"acilis_ms": gun, "open": [100.0] * n, "volume": [1.0] * n})
    ev = pl.DataFrame({"sembol": ["AAA"], "gun_ms": [T0 + 2 * G], "oran": [1.0]})
    a = kl.KilitAyar(giris=0, cikis=7, notional=0.1, ucret=0.0, kayma_token=0.0, kayma_btc=0.0)
    _, tam = kl.kos(ev, {"AAA": tok}, {}, btc, pl.DataFrame(), a, T0, T0 + n * G)
    _, kisa = kl.kos(ev, {"AAA": dl.kirp(tok, [T0 + 4 * G + 1])}, {}, btc, pl.DataFrame(), a, T0, T0 + n * G)
    g_tam, g_kisa = tam["getiri"][0], kisa["getiri"][0]
    assert g_tam == pytest.approx(7 * 0.05) and g_kisa == pytest.approx(3 * 0.05)   # günlük +%5 (kısa), toplamsal
