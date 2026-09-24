"""Spike 02 (a)+(b): aynı saf karar fonksiyonu ile vektörel yol ↔ NautilusTrader v2 backtest parity.

Kural (her iki yolda aynı): karar bar kapanışında, dolum SONRAKİ barın açılışında, piyasa emri (taker ücret).
Ağırlık 0→1: nakdin %98'i ile al (dolum fiyatı bilinmediği için tampon). 1→0: hepsini sat. Miktar enstrümanın
adımına aşağı yuvarlanır. Son özkaynak = nakit + adet × son kapanış.
"""
from __future__ import annotations

import math
import sys
import time
from decimal import Decimal

import numpy as np
import polars as pl

from karar import hedef_agirlik
from veri import binance_kline, yahoo_gunluk

from nautilus_trader.backtest import BacktestEngine
from nautilus_trader.common import LogLevel
from nautilus_trader.config import BacktestEngineConfig, LoggerConfig, StrategyConfig
from nautilus_trader.execution import StaticLatencyModel
from nautilus_trader.model import (
    AccountType, Bar, BarType, Currency, CurrencyPair, Equity, InstrumentId, Money, OmsType, OrderSide,
    Price, Quantity, Symbol, TraderId, Venue,
)
from nautilus_trader.trading import Strategy

TAMPON = 0.98
GECIKME = True  # False: Nautilus varsayılanı (sinyal barı kapanışında dolum)


# ----------------------------------------------------------------------------- enstrümanlar
def btcusdt() -> CurrencyPair:
    return CurrencyPair(
        instrument_id=InstrumentId(Symbol("BTCUSDT"), Venue("BINANCE")), raw_symbol=Symbol("BTCUSDT"),
        base_currency=Currency.from_str("BTC"), quote_currency=Currency.from_str("USDT"),
        price_precision=2, size_precision=5, price_increment=Price(0.01, 2), size_increment=Quantity(0.00001, 5),
        ts_event=0, ts_init=0, min_quantity=Quantity(0.00001, 5), maker_fee=Decimal("0.001"), taker_fee=Decimal("0.001"),
        margin_init=Decimal(0), margin_maint=Decimal(0),
    )


def spy() -> Equity:
    return Equity(
        instrument_id=InstrumentId(Symbol("SPY"), Venue("ARCA")), raw_symbol=Symbol("SPY"),
        currency=Currency.from_str("USD"), price_precision=2, price_increment=Price(0.01, 2), ts_event=0, ts_init=0,
        lot_size=Quantity(1, 0), maker_fee=Decimal("0.0005"), taker_fee=Decimal("0.0005"),
    )


def barlar(df: pl.DataFrame, bar_type: BarType, pp: int, sp: int) -> list[Bar]:
    return [
        Bar(bar_type, Price(o, pp), Price(h, pp), Price(l, pp), Price(c, pp), Quantity(v, sp), k * 1_000_000, k * 1_000_000)
        for o, h, l, c, v, k in df.select("open", "high", "low", "close", "volume", "kapanis_ms").iter_rows()
    ]


# ----------------------------------------------------------------------------- vektörel yol
def vektorel(df: pl.DataFrame, nakit0: float, ucret: float, adim: float) -> dict:
    kap = df["close"].to_numpy()
    acl = df["open"].to_numpy()
    w = hedef_agirlik(kap)  # tek çağrı, tüm dizi
    nakit, adet, islemler = nakit0, 0.0, []
    for t in range(len(kap) - 1):
        onceki = w[t - 1] if t > 0 else 0.0
        if w[t] == onceki:
            continue
        fiyat = acl[t + 1]  # sonraki barın açılışı
        if w[t] == 1.0 and adet == 0.0:
            q = math.floor(nakit * TAMPON / kap[t] / adim) * adim
            q = round(q, 8)
            nakit -= q * fiyat * (1 + ucret)
            adet = q
            islemler.append(("BUY", t + 1, fiyat, q))
        elif w[t] == 0.0 and adet > 0.0:
            nakit += adet * fiyat * (1 - ucret)
            islemler.append(("SELL", t + 1, fiyat, adet))
            adet = 0.0
    return {"w": w, "islemler": islemler, "ozkaynak": nakit + adet * kap[-1]}


# ----------------------------------------------------------------------------- Nautilus yolu
class SarmalayiciConfig(StrategyConfig):
    def __init__(self, *, instrument_id: InstrumentId, bar_type: BarType, para: str, **_kw) -> None:
        super().__init__()
        self.instrument_id = instrument_id
        self.bar_type = bar_type
        self.para = para


class Sarmalayici(Strategy):
    """Saf karar çekirdeğini çağıran ince Nautilus sarmalayıcısı."""

    def __init__(self, config: SarmalayiciConfig) -> None:
        super().__init__(config)
        self.kapanislar: list[float] = []
        self.kararlar: list[float] = []

    def on_start(self) -> None:
        self.subscribe_bars(self.config.bar_type)

    def on_bar(self, bar: Bar) -> None:
        self.kapanislar.append(float(bar.close))
        w = float(hedef_agirlik(np.asarray(self.kapanislar))[-1])  # aynı fonksiyon, o ana kadarki geçmiş
        onceki = self.kararlar[-1] if self.kararlar else 0.0
        self.kararlar.append(w)
        if w == onceki:
            return
        iid = self.config.instrument_id
        ins = self.cache.instrument(iid)
        net = float(self.portfolio.net_position(iid))
        if w == 1.0 and net == 0.0:
            hesap = self.portfolio.account(venue=iid.venue)
            nakit = float(hesap.balance_free(Currency.from_str(self.config.para)))
            adim = float(ins.size_increment)
            q = math.floor(nakit * TAMPON / float(bar.close) / adim) * adim
            if q > 0:
                self.submit_order(self.order_factory.market(iid, OrderSide.BUY, ins.make_qty(q)))
        elif w == 0.0 and net > 0.0:
            self.submit_order(self.order_factory.market(iid, OrderSide.SELL, ins.make_qty(net)))


def nautilus(df: pl.DataFrame, ins, para: str, nakit0: float, bar_str: str, sp: int) -> dict:
    motor = BacktestEngine(BacktestEngineConfig(trader_id=TraderId("SPIKE-001"), logging=LoggerConfig(stdout_level=LogLevel.ERROR)))
    motor.add_venue(
        venue=ins.id.venue, oms_type=OmsType.NETTING, account_type=AccountType.CASH,
        starting_balances=[Money(nakit0, Currency.from_str(para))], base_currency=None,
        # Emir borsaya 1 ms gecikmeyle ulaşır → sinyal barının kapanışında değil, sonraki barın açılışında dolar.
        latency_model=StaticLatencyModel(base_latency_nanos=1_000_000) if GECIKME else None,
    )
    motor.add_instrument(ins)
    bt = BarType.from_str(bar_str)
    motor.add_data(barlar(df, bt, ins.price_precision, sp))
    s = Sarmalayici(SarmalayiciConfig(instrument_id=ins.id, bar_type=bt, para=para))
    motor.add_strategy(s)
    t0 = time.perf_counter()
    motor.run()
    sure = time.perf_counter() - t0
    dolumlar = motor.generate_order_fills_report()
    hesap = motor.cache.account_for_venue(ins.id.venue)
    nakit = float(hesap.balance_total(Currency.from_str(para)))
    net = float(motor.portfolio.net_position(ins.id))
    kararlar = np.asarray(s.kararlar)
    sonuc = {"w": kararlar, "dolumlar": dolumlar, "ozkaynak": nakit + net * df["close"][-1], "sure": sure}
    motor.dispose()
    return sonuc


# ----------------------------------------------------------------------------- testler
def gelecek_bozma_testi(kap: np.ndarray, deneme: int = 200) -> bool:
    rng = np.random.default_rng(0)
    temel = hedef_agirlik(kap)
    for _ in range(deneme):
        t = int(rng.integers(100, len(kap) - 2))
        bozuk = kap.copy()
        bozuk[t + 1:] = rng.uniform(0.1, 10, len(kap) - t - 1) * bozuk[t + 1:]
        if not np.array_equal(hedef_agirlik(bozuk)[: t + 1], temel[: t + 1]):
            return False
    return True


def karsilastir(ad: str, df: pl.DataFrame, ins, para: str, nakit0: float, bar_str: str, sp: int, ucret: float) -> bool:
    print(f"\n=== {ad}: {len(df)} bar ===")
    v = vektorel(df, nakit0, ucret, float(ins.size_increment))
    n = nautilus(df, ins, para, nakit0, bar_str, sp)
    ok_karar = np.array_equal(v["w"], n["w"])
    print(f"karar serisi birebir aynı: {ok_karar}  (değişim sayısı {int(np.abs(np.diff(v['w'])).sum())})")
    d = n["dolumlar"]
    print(f"işlem sayısı — vektörel {len(v['islemler'])}, Nautilus {len(d)}")
    zaman = df["kapanis_ms"].to_numpy()
    fark_fiyat = fark_zaman = 0
    if len(d) == len(v["islemler"]):
        d = d.sort_values("ts_last") if "ts_last" in d.columns else d
        for (yon, i, fiyat, q), (_, satir) in zip(v["islemler"], d.iterrows()):
            nf = float(satir["avg_px"])
            if abs(nf - fiyat) > 1e-6:
                fark_fiyat += 1
            # Nautilus dolumu sonraki barın açılış anında (önceki barın kapanışı = bu barın açılışı)
            import pandas as pd
            ts = pd.Timestamp(satir["ts_last"]).value // 1_000_000 if "ts_last" in d.columns else None
            # Dolum anı sonraki barın (i) açılışı ya da kapanışı olmalı; sinyal barının kapanışı OLMAMALI
            # (kripto 7/24'te sinyal kapanışı = sonraki açılış olduğu için orada fiyat karşılaştırması belirleyicidir).
            if ts is not None and ts not in (int(df["acilis_ms"][i]), int(zaman[i])):
                fark_zaman += 1
        print(f"dolum fiyatı farkı: {fark_fiyat} işlem · dolum zamanı farkı: {fark_zaman} işlem")
    else:
        print(d.head(10).to_string())
    oz_v, oz_n = v["ozkaynak"], n["ozkaynak"]
    print(f"son özkaynak — vektörel {oz_v:,.2f} · Nautilus {oz_n:,.2f} · fark %{abs(oz_v - oz_n) / oz_v * 100:.4f}")
    print(f"Nautilus koşu süresi {n['sure']:.2f} sn")
    return ok_karar and len(d) == len(v["islemler"]) and fark_fiyat == 0


if __name__ == "__main__":
    btc = binance_kline("BTCUSDT", "1d", 1577836800000)  # 2020-01-01 →
    btc4 = binance_kline("BTCUSDT", "4h", 1640995200000)  # 2022-01-01 →
    spy_df = yahoo_gunluk("SPY")
    print("gelecek-bozma testi (BTC 1d):", gelecek_bozma_testi(btc["close"].to_numpy()))
    sonuc = [
        karsilastir("BTCUSDT 1d", btc, btcusdt(), "USDT", 100_000, "BTCUSDT.BINANCE-1-DAY-LAST-EXTERNAL", 5, 0.001),
        karsilastir("BTCUSDT 4h", btc4, btcusdt(), "USDT", 100_000, "BTCUSDT.BINANCE-4-HOUR-LAST-EXTERNAL", 5, 0.001),
        karsilastir("SPY 1d", spy_df, spy(), "USD", 100_000, "SPY.ARCA-1-DAY-LAST-EXTERNAL", 0, 0.0005),
    ]
    print("\nPARITY:", "GEÇTİ" if all(sonuc) else "KALDI")
    sys.exit(0 if all(sonuc) else 1)
