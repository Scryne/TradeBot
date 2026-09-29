"""Binance USDT-M perp (Dalga 6): günlük mum ve funding geçmişi, herkese açık `fapi` uçları (anahtarsız).

Kimlik `BINANCEF:<SEMBOL>` (spot `BINANCE:` ile karışmasın). Delist edilen perp'ler de sorgulanır (`exchangeInfo`
listesinde kalanlar): hayatta kalan yanlılığını azaltır. Ham yanıtlar ham depoya yazılır.
"""
from __future__ import annotations

import json

import polars as pl

FAPI = "https://fapi.binance.com/fapi/v1"
GUN_MS = 86_400_000


def usdt_perpler(http_al, ham=None) -> dict[str, dict]:
    """{sembol_tabani: {"sembol": "TIAUSDT", "durum": "TRADING", "liste_ms": ...}} (1000PEPE gibi çarpanlı adlar dahil)."""
    icerik = http_al(f"{FAPI}/exchangeInfo")
    if ham is not None:
        ham.kaydet("binancef", "exchangeInfo", icerik, "json")
    out = {}
    for x in json.loads(icerik)["symbols"]:
        if x.get("contractType") == "PERPETUAL" and x.get("quoteAsset") == "USDT":
            taban = x["baseAsset"]
            for on in ("1000000", "1000", "1M"):
                if taban.startswith(on) and len(taban) > len(on):
                    taban = taban[len(on):]
                    break
            filtre = {f.get("filterType"): f for f in x.get("filters") or []}
            out.setdefault(taban, {"sembol": x["symbol"], "durum": x["status"], "liste_ms": x.get("onboardDate"),
                                   "carpan": x["baseAsset"][: len(x["baseAsset"]) - len(taban)] or "1",
                                   "adim": float((filtre.get("MARKET_LOT_SIZE") or filtre.get("LOT_SIZE") or {})
                                                 .get("stepSize", 0) or 0),
                                   "asgari_notional": float((filtre.get("MIN_NOTIONAL") or {}).get("notional", 0) or 0)})
    return out


def gunluk(http_al, ham, sembol: str) -> pl.DataFrame:
    """Bütün günlük mumlar (1500'lük sayfalar)."""
    satir, bas = [], 0
    while True:
        icerik = http_al(f"{FAPI}/klines?symbol={sembol}&interval=1d&startTime={bas}&limit=1500")
        ham.kaydet("binancef", f"klines/1d/{sembol}/{bas}", icerik, "json")
        r = json.loads(icerik)
        if not r:
            break
        satir += [(int(k[0]), float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[7])) for k in r]
        if len(r) < 1500:
            break
        bas = int(r[-1][0]) + GUN_MS
    return pl.DataFrame(satir, schema=["acilis_ms", "open", "high", "low", "close", "volume"], orient="row").unique(
        "acilis_ms").sort("acilis_ms")


def funding(http_al, ham, sembol: str) -> pl.DataFrame:
    """Bütün funding geçmişi (8 saatte bir, oran: uzun öder / kısa alır pozitifse)."""
    satir, bas = [], 0
    while True:
        icerik = http_al(f"{FAPI}/fundingRate?symbol={sembol}&startTime={bas}&limit=1000")
        ham.kaydet("binancef", f"funding/{sembol}/{bas}", icerik, "json")
        r = json.loads(icerik)
        if not r:
            break
        satir += [(int(x["fundingTime"]), float(x["fundingRate"])) for x in r]
        if len(r) < 1000:
            break
        bas = int(r[-1]["fundingTime"]) + 1
    return pl.DataFrame(satir, schema=["zaman_ms", "oran"], orient="row").unique("zaman_ms").sort("zaman_ms")
