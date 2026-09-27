"""Canlı bar deposu: paper kararının verisi (Faz 7).

- Başlangıçta ana depodaki 1h barlar (veri servisinin gece indirdiği arşiv) canlı depoya kopyalanır, aradaki eksik
  barlar Binance REST'ten (`/api/v3/klines`) tamamlanır.
- Her saat kapanışında kapanan bar REST'ten alınıp eklenir. Şema arşivle aynıdır (açılış ms, OHLC, hacim, kote hacim,
  işlem sayısı), 4h/1d barlar backtest'teki gibi 1h'den türetilir (`panel.bar_yukle`).
- Yalnız KAPANMIŞ barlar yazılır (kapanış ≤ şimdi). Ham yanıtlar HamDepo'ya yazılır (kural 9).
"""
from __future__ import annotations

import json
import shutil

import polars as pl

from tradebot.veri.depo import BarDepo, HamDepo
from tradebot.veri.http import NazikIstemci

REST = "https://api.binance.com/api/v3/klines"
SAAT_MS = 3_600_000


def rest_sembol(kimlik: str) -> str:
    return kimlik.removeprefix("BINANCE:")


def klines_coz(ham: bytes) -> pl.DataFrame:
    """REST kline dizisi → bar tablosu (arşiv şeması)."""
    satirlar = json.loads(ham)
    if not satirlar:
        return pl.DataFrame(schema={"acilis_ms": pl.Int64, "open": pl.Float64, "high": pl.Float64, "low": pl.Float64,
                                    "close": pl.Float64, "volume": pl.Float64, "quote_volume": pl.Float64,
                                    "trades": pl.Float64, "kapanis_ms": pl.Int64})
    return pl.DataFrame({
        "acilis_ms": [int(r[0]) for r in satirlar], "open": [float(r[1]) for r in satirlar],
        "high": [float(r[2]) for r in satirlar], "low": [float(r[3]) for r in satirlar],
        "close": [float(r[4]) for r in satirlar], "volume": [float(r[5]) for r in satirlar],
        "quote_volume": [float(r[7]) for r in satirlar], "trades": [float(r[8]) for r in satirlar],
        "kapanis_ms": [int(r[6]) for r in satirlar]})


class CanliBarlar:
    def __init__(self, ana: BarDepo, canli: BarDepo, ham: HamDepo, http: NazikIstemci | None = None) -> None:
        self.ana, self.canli, self.ham = ana, canli, ham
        self.http = http or NazikIstemci("binance_rest", aralik_sn=0.3, deneme=5, geri_cekilme_sn=2.0)

    def son_ms(self, kimlik: str) -> int | None:
        y = self.canli.yol(kimlik, "1h")
        if not y.exists():
            return None
        return int(pl.read_parquet(y, columns=["acilis_ms"])["acilis_ms"].max())

    def hazirla(self, kimlikler: list[str], simdi_ms: int) -> dict[str, int]:
        """Canlı depo yoksa ana depodan kopyalar, sonra şimdiye kadar tamamlar. Döndürür: kimlik → son bar açılışı."""
        for k in kimlikler:
            hedef = self.canli.yol(k, "1h")
            if not hedef.exists():
                kaynak = self.ana.yol(k, "1h")
                if not kaynak.exists():
                    raise FileNotFoundError(f"ana depoda 1h yok: {k}")
                hedef.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(kaynak, hedef)
        return self.guncelle(kimlikler, simdi_ms)

    def guncelle(self, kimlikler: list[str], simdi_ms: int) -> dict[str, int]:
        """Son bardan şimdiye kadar KAPANMIŞ barları ekler (1000'lik sayfalarla)."""
        out = {}
        for k in kimlikler:
            son = self.son_ms(k) or simdi_ms - 1000 * SAAT_MS
            while True:
                bas = son + SAAT_MS
                if bas + SAAT_MS > simdi_ms:  # henüz kapanmış yeni bar yok
                    break
                ham = self.http.al(REST, {"symbol": rest_sembol(k), "interval": "1h", "startTime": bas, "limit": 1000})
                df = klines_coz(ham)
                df = df.filter(pl.col("kapanis_ms") < simdi_ms).drop("kapanis_ms")
                if df.is_empty():
                    break
                self.ham.kaydet("binance_rest", f"{rest_sembol(k)}/1h/{int(df['acilis_ms'][0])}-{int(df['acilis_ms'][-1])}",
                                ham, "json")
                self.canli.yaz(k, "1h", df)
                son = int(df["acilis_ms"].max())
                if len(df) < 1000:
                    break
            out[k] = self.son_ms(k) or 0
        return out
