"""Spike 02 veri yardımcıları: Binance public kline + Yahoo grafik uç noktası. Önbellek: data/ (git dışı).

Zaman kuralı: tablolarda `acilis_ms` = barın açılış zamanı (UTC epoch ms). Nautilus'a verirken ts_event barın
KAPANIŞ zamanıdır — bar ancak kapandığında bilinir.
"""
from __future__ import annotations

import json
import time
import urllib.request
from pathlib import Path

import polars as pl

ONBELLEK = Path(__file__).parent / "data"
ONBELLEK.mkdir(exist_ok=True)
_UA = {"User-Agent": "Mozilla/5.0"}


def _json(url: str):
    with urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=30) as r:
        return json.load(r)


def binance_kline(sembol: str, aralik: str, baslangic_ms: int) -> pl.DataFrame:
    yol = ONBELLEK / f"binance_{sembol}_{aralik}_{baslangic_ms}.parquet"
    if yol.exists():
        return pl.read_parquet(yol)
    satirlar, t = [], baslangic_ms
    while True:
        p = _json(f"https://api.binance.com/api/v3/klines?symbol={sembol}&interval={aralik}&limit=1000&startTime={t}")
        if not p:
            break
        satirlar += p
        t = p[-1][0] + 1
        if len(p) < 1000:
            break
        time.sleep(0.1)
    df = pl.DataFrame(
        {
            "acilis_ms": [int(k[0]) for k in satirlar],
            "kapanis_ms": [int(k[6]) + 1 for k in satirlar],  # Binance kapanış = sonraki açılış - 1 ms
            "open": [float(k[1]) for k in satirlar],
            "high": [float(k[2]) for k in satirlar],
            "low": [float(k[3]) for k in satirlar],
            "close": [float(k[4]) for k in satirlar],
            "volume": [float(k[5]) for k in satirlar],
        }
    )
    # Henüz kapanmamış son bar atılır (gelecek bilgisi değil ama tamamlanmamış).
    df = df.filter(pl.col("kapanis_ms") <= int(time.time() * 1000))
    df.write_parquet(yol)
    return df


def yahoo_gunluk(sembol: str, aralik: str = "10y", seans_suresi_ms: int = int(6.5 * 3600 * 1000)) -> pl.DataFrame:
    """Yahoo günlük barları. Yahoo zaman damgası seans açılışıdır; kapanış = açılış + seans süresi (yaklaşık)."""
    yol = ONBELLEK / f"yahoo_{sembol}_{aralik}.parquet"
    if yol.exists():
        return pl.read_parquet(yol)
    r = _json(f"https://query1.finance.yahoo.com/v8/finance/chart/{sembol}?range={aralik}&interval=1d")["chart"]["result"][0]
    q = r["indicators"]["quote"][0]
    df = pl.DataFrame(
        {
            "acilis_ms": [int(t) * 1000 for t in r["timestamp"]],
            "open": q["open"], "high": q["high"], "low": q["low"], "close": q["close"],
            "volume": [float(v or 0) for v in q["volume"]],
        }
    ).drop_nulls()
    df = df.with_columns((pl.col("acilis_ms") + seans_suresi_ms).alias("kapanis_ms"))
    df.write_parquet(yol)
    return df
