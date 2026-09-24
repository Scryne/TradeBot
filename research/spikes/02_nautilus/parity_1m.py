"""Spike 02 (b'): günlük karar + 1 dakikalık yürütme verisi.

Nautilus'ta "sonraki bar açılışında dolum" modu yok (docs: bar-execution). Kurumsal çözüm: strateji günlük barı
Nautilus'un 1 dakikalık veriden İÇ olarak topladığı barla görür; emir 1 ms gecikmeyle borsaya ulaşır ve sinyalden
sonraki İLK DAKİKA barında dolar. Vektörel referans: aynı günlük barlar (1 dk'dan UTC günü), dolum = ertesi günün
ilk dakika barının kapanışı. İki yol birebir aynı olmalı. Ayrıca "ertesi gün açılışı" ile fark raporlanır.
"""
from __future__ import annotations

import io
import math
import time
import zipfile
from pathlib import Path

import numpy as np
import polars as pl

from karar import hedef_agirlik
from parity import TAMPON, Sarmalayici, SarmalayiciConfig, btcusdt

from nautilus_trader.backtest import BacktestEngine
from nautilus_trader.common import LogLevel
from nautilus_trader.config import BacktestEngineConfig, LoggerConfig
from nautilus_trader.execution import StaticLatencyModel
from nautilus_trader.model import AccountType, Bar, BarType, Currency, Money, OmsType, Price, Quantity, TraderId

GUN_MS = 86_400_000


def dakikalar() -> pl.DataFrame:
    parcalar = []
    for z in sorted((Path(__file__).parent / "data" / "bv").glob("BTCUSDT-1m-*.zip")):
        with zipfile.ZipFile(z) as zf:
            ham = zf.read(zf.namelist()[0])
        df = pl.read_csv(io.BytesIO(ham), has_header=False, new_columns=[
            "acilis", "open", "high", "low", "close", "volume", "kapanis", "qv", "n", "tbb", "tbq", "x"])
        # 2025'ten itibaren Binance arşivi mikrosaniye; öncesi milisaniye.
        birim = 1000 if df["acilis"][0] > 10**14 else 1
        parcalar.append(df.select(
            (pl.col("acilis") // birim).alias("acilis_ms"),
            "open", "high", "low", "close", "volume"))
    return pl.concat(parcalar).sort("acilis_ms").with_columns((pl.col("acilis_ms") + 60_000).alias("kapanis_ms"))


def gunluk(dk: pl.DataFrame) -> pl.DataFrame:
    return (dk.with_columns((pl.col("acilis_ms") // GUN_MS * GUN_MS).alias("gun"))
              .group_by("gun", maintain_order=True)
              .agg(pl.col("open").first(), pl.col("high").max(), pl.col("low").min(), pl.col("close").last(),
                   pl.col("volume").sum(), pl.len().alias("dk_sayisi"),
                   pl.col("close").first().alias("ilk_dk_kapanis"))
              .rename({"gun": "acilis_ms"})
              .with_columns((pl.col("acilis_ms") + GUN_MS).alias("kapanis_ms")))


def vektorel(g: pl.DataFrame, nakit0: float, ucret: float, adim: float, dolum_kolonu: str) -> dict:
    kap, dolum = g["close"].to_numpy(), g[dolum_kolonu].to_numpy()
    w = hedef_agirlik(kap)
    nakit, adet, islemler = nakit0, 0.0, []
    for t in range(len(kap) - 1):
        onceki = w[t - 1] if t > 0 else 0.0
        if w[t] == onceki:
            continue
        f = dolum[t + 1]
        if w[t] == 1.0 and adet == 0.0:
            q = round(math.floor(nakit * TAMPON / kap[t] / adim) * adim, 8)
            nakit -= q * f * (1 + ucret); adet = q
            islemler.append(("BUY", t + 1, f))
        elif w[t] == 0.0 and adet > 0.0:
            nakit += adet * f * (1 - ucret); adet = 0.0
            islemler.append(("SELL", t + 1, f))
    return {"w": w, "islemler": islemler, "ozkaynak": nakit + adet * kap[-1]}


def nautilus(dk: pl.DataFrame, nakit0: float) -> dict:
    ins = btcusdt()
    motor = BacktestEngine(BacktestEngineConfig(trader_id=TraderId("SPIKE-002"), logging=LoggerConfig(stdout_level=LogLevel.ERROR)))
    motor.add_venue(venue=ins.id.venue, oms_type=OmsType.NETTING, account_type=AccountType.CASH,
                    starting_balances=[Money(nakit0, Currency.from_str("USDT"))], base_currency=None,
                    latency_model=StaticLatencyModel(base_latency_nanos=1_000_000))
    motor.add_instrument(ins)
    dk_tipi = BarType.from_str("BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL")
    t0 = time.perf_counter()
    barlar = [Bar(dk_tipi, Price(o, 2), Price(h, 2), Price(l, 2), Price(c, 2), Quantity(v, 5), k * 1_000_000, k * 1_000_000)
              for o, h, l, c, v, k in dk.select("open", "high", "low", "close", "volume", "kapanis_ms").iter_rows()]
    motor.add_data(barlar)
    yukleme = time.perf_counter() - t0
    gun_tipi = BarType.from_str("BTCUSDT.BINANCE-1-DAY-LAST-INTERNAL@1-MINUTE-EXTERNAL")
    s = Sarmalayici(SarmalayiciConfig(instrument_id=ins.id, bar_type=gun_tipi, para="USDT"))
    motor.add_strategy(s)
    t0 = time.perf_counter()
    motor.run()
    kosu = time.perf_counter() - t0
    d = motor.generate_order_fills_report().sort_values("ts_last")
    nakit = float(motor.cache.account_for_venue(ins.id.venue).balance_total(Currency.from_str("USDT")))
    net = float(motor.portfolio.net_position(ins.id))
    out = {"w": np.asarray(s.kararlar), "dolumlar": d, "nakit": nakit, "net": net,
           "yukleme": yukleme, "kosu": kosu, "bar": len(barlar)}
    motor.dispose()
    return out


if __name__ == "__main__":
    dk = dakikalar()
    g = gunluk(dk)
    print(f"1 dk bar: {len(dk):,} · gün: {len(g)} · eksik dakikalı gün: {(g['dk_sayisi'] < 1440).sum()}")
    n = nautilus(dk, 100_000)
    print(f"Nautilus: {n['bar']:,} bar yükleme {n['yukleme']:.1f} sn, koşu {n['kosu']:.1f} sn")
    # Nautilus iç günlük barı son (eksik) günü de kapatmayabilir; karşılaştırma ortak uzunlukta.
    L = min(len(n["w"]), len(g))
    print(f"karar sayısı — Nautilus {len(n['w'])}, vektörel gün {len(g)}")
    for kolon, ad in (("ilk_dk_kapanis", "ertesi günün ilk dakikası"), ("open", "ertesi gün açılışı")):
        v = vektorel(g.head(L), 100_000, 0.001, 0.00001, kolon)
        esit_karar = np.array_equal(v["w"][:L], n["w"][:L])
        d = n["dolumlar"]
        fark = [abs(float(r["avg_px"]) - f) / f for (_, _, f), (_, r) in zip(v["islemler"], d.iterrows())]
        oz_n = n["nakit"] + n["net"] * g["close"][L - 1]
        print(f"\n[referans dolum: {ad}] karar aynı: {esit_karar} · işlem: vektörel {len(v['islemler'])} / Nautilus {len(d)}")
        print(f"  dolum fiyatı farkı: azami %{max(fark) * 100:.4f}, ortalama %{np.mean(fark) * 100:.4f}")
        print(f"  son özkaynak — vektörel {v['ozkaynak']:,.2f} · Nautilus {oz_n:,.2f} · fark %{abs(v['ozkaynak'] - oz_n) / v['ozkaynak'] * 100:.4f}")
