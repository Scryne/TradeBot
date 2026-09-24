"""Spike 02 (c)+(d): canlı düğüm — Binance public veri (yerleşik) + KENDİ Python veri istemcimiz + sandbox yürütme.

Kendi istemci: Yahoo grafik uç noktasını yoklayıp 1 dk bar üretir. BIST (.IS) ve seans dışı piyasalar için
yazacağımız bağlantının iskeleti; seans kapalı olduğu için testte 7/24 açık BTC-USD kullanılır.
Anahtar yok, gerçek para yok. Süre: SURE_DK dakika.
"""
from __future__ import annotations

import asyncio
import json
import time
import urllib.request
from decimal import Decimal

from nautilus_trader.adapters.binance import (
    BinanceDataClientConfig, BinanceDataClientFactory, BinanceEnvironment, BinanceProductType, BinanceSpotMarketDataMode,
)
from nautilus_trader.adapters.sandbox import SandboxExecutionClientConfig, SandboxExecutionClientFactory
from nautilus_trader.common import Environment
from nautilus_trader.config import DataClientConfig, LiveRiskEngineConfig, StrategyConfig
from nautilus_trader.execution import MakerTakerFeeModel
from nautilus_trader.live import LiveNode
from nautilus_trader.live.clients import DataClientFactory, MarketDataClient
from nautilus_trader.model import (
    AccountId, Bar, BarType, ClientId, Currency, CurrencyPair, InstrumentId, Money, OrderSide, Price, Quantity, Symbol,
    TraderId, Venue,
)
from nautilus_trader.trading import Strategy

SURE_DK = 4
YAHOO = Venue("YAHOO")
YAHOO_ID = InstrumentId(Symbol("BTC-USD"), YAHOO)
YAHOO_BAR = BarType.from_str("BTC-USD.YAHOO-1-MINUTE-LAST-EXTERNAL")
BIN_ID = InstrumentId.from_str("BTCUSDT.BINANCE")
BIN_BAR = BarType.from_str("BTCUSDT.BINANCE-1-MINUTE-LAST-EXTERNAL")


# ----------------------------------------------------------------------------- kendi veri istemcimiz
def _yahoo_1dk(sembol: str) -> list[tuple]:
    req = urllib.request.Request(
        f"https://query1.finance.yahoo.com/v8/finance/chart/{sembol}?range=1d&interval=1m",
        headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        res = json.load(r)["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    return [(t * 1000, o, h, l, c, v or 0.0) for t, o, h, l, c, v in
            zip(res["timestamp"], q["open"], q["high"], q["low"], q["close"], q["volume"]) if c is not None]


class YahooVeriIstemcisi(MarketDataClient):
    """Yoklama tabanlı 1 dk bar istemcisi. Yalnız KAPANMIŞ barları yayar (açılış + 60 sn ≤ şimdi)."""

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self._son_ms = 0
        self._gorev = None
        self.yayilan = 0

    async def _connect(self) -> None:
        self._handle_instrument(CurrencyPair(
            instrument_id=YAHOO_ID, raw_symbol=Symbol("BTC-USD"), base_currency=Currency.from_str("BTC"),
            quote_currency=Currency.from_str("USD"), price_precision=2, size_precision=0,
            price_increment=Price(0.01, 2), size_increment=Quantity(1, 0), ts_event=0, ts_init=0,
            margin_init=Decimal(0), margin_maint=Decimal(0), maker_fee=Decimal(0), taker_fee=Decimal(0)))

    async def _disconnect(self) -> None:
        if self._gorev is not None:
            self._gorev.cancel()

    async def _subscribe_bars(self, command) -> None:
        self._gorev = self.create_task(self._yokla(command.bar_type), "yahoo-yoklama")

    async def _unsubscribe_bars(self, command) -> None:
        if self._gorev is not None:
            self._gorev.cancel()

    async def _yokla(self, bar_type: BarType) -> None:
        while True:
            try:
                satirlar = await asyncio.to_thread(_yahoo_1dk, "BTC-USD")
                simdi = int(time.time() * 1000)
                for t, o, h, l, c, v in satirlar:
                    kapanis = t + 60_000
                    if t > self._son_ms and kapanis <= simdi:
                        if self._son_ms == 0 and kapanis < simdi - 120_000:
                            continue  # ilk turda eski barları atla, yalnız son kapanmışı yay
                        self._handle_data(Bar(bar_type, Price(o, 2), Price(h, 2), Price(l, 2), Price(c, 2),
                                              Quantity(0, 0), kapanis * 1_000_000, simdi * 1_000_000))
                        self._son_ms = t
                        self.yayilan += 1
            except Exception as e:  # yoklama hatası düğümü düşürmez
                print("yahoo yoklama hatası:", e)
            await asyncio.sleep(15)


class YahooFabrika(DataClientFactory):
    @staticmethod
    def create(*, name, config, cache, clock):
        return YahooVeriIstemcisi(name=name, config=config, cache=cache, clock=clock, venue=YAHOO)


# ----------------------------------------------------------------------------- gözlemci strateji
class GozlemciConfig(StrategyConfig):
    def __init__(self, **kw) -> None:
        super().__init__(**kw)


class Gozlemci(Strategy):
    def __init__(self, config: GozlemciConfig) -> None:
        super().__init__(config)
        self.bin_bar = 0
        self.yahoo_bar = 0
        self.dolumlar = []
        self.gecikme_ms = []

    def on_start(self) -> None:
        self.subscribe_bars(BIN_BAR)
        self.subscribe_trades(BIN_ID)
        self.subscribe_bars(YAHOO_BAR, client_id=ClientId("YAHOO"))

    def on_bar(self, bar: Bar) -> None:
        gec = (self.clock.timestamp_ns() - bar.ts_event) / 1e6
        if bar.bar_type == BIN_BAR:
            self.bin_bar += 1
            self.gecikme_ms.append(gec)
            print(f"[BINANCE] {bar.close} · bar kapanışından {gec:.0f} ms sonra geldi")
            if self.bin_bar == 1:
                self.submit_order(self.order_factory.market(BIN_ID, OrderSide.BUY, Quantity.from_str("0.00100")))
            elif self.bin_bar == 3:
                self.submit_order(self.order_factory.market(BIN_ID, OrderSide.SELL, Quantity.from_str("0.00100")))
        else:
            self.yahoo_bar += 1
            print(f"[YAHOO/özel istemci] {bar.close} · kapanıştan {gec / 1000:.0f} sn sonra")

    def on_order_filled(self, event) -> None:
        self.dolumlar.append((str(event.order_side), str(event.last_px), str(event.last_qty), str(event.commission)))
        print(f"[DOLUM] {event.order_side} {event.last_qty} @ {event.last_px} komisyon {event.commission}")


async def ana() -> None:
    # Bu makinede IPv6 kaydı olmayan adların DNS çözümlemesi ~11 sn sürüyor (Nautilus WS zaman aşımı 5 sn).
    # Adı önceden çözümleyip Windows DNS önbelleğine alıyoruz. Kalıcı çözüm: DNS ayarı (host'ta kontrol edilecek).
    import socket
    for h in ("stream.binance.com", "data-stream.binance.vision", "query1.finance.yahoo.com"):
        t0 = time.time(); socket.getaddrinfo(h, 443); print(f"DNS ön ısıtma {h}: {time.time() - t0:.1f} sn")
    node = (
        LiveNode.builder("SPIKE-CANLI", TraderId.from_str("SPIKE-003"), Environment.SANDBOX)
        .with_reconciliation(reconciliation=False)
        .with_risk_engine_config(LiveRiskEngineConfig(bypass=False))
        .add_data_client(None, BinanceDataClientFactory(), BinanceDataClientConfig(
            product_type=BinanceProductType.SPOT, environment=BinanceEnvironment.LIVE,
            spot_market_data_mode=BinanceSpotMarketDataMode.Json))
        .add_data_client("YAHOO", YahooFabrika, DataClientConfig())
        .add_simulated_exec_client("BINANCE", SandboxExecutionClientFactory(), SandboxExecutionClientConfig(
            venue=Venue("BINANCE"), starting_balances=[Money(10_000.0, Currency.from_str("USDT"))],
            account_id=AccountId.from_str("BINANCE-SANDBOX-001"),
            fee_model=MakerTakerFeeModel()))
        .build()
    )
    s = Gozlemci(GozlemciConfig())
    node.add_strategy(s)
    tutamak, cache = node.handle(), node.cache  # v2: run_async sırasında durdurma tutamak üzerinden
    gorev = asyncio.create_task(node.run_async())
    await asyncio.sleep(SURE_DK * 60)
    tutamak.stop()
    try:
        await asyncio.wait_for(gorev, timeout=60)
    except Exception as e:
        print("durdurma:", type(e).__name__, e)
    print("\n=== ÖZET ===")
    print(f"Binance 1 dk bar: {s.bin_bar} · özel istemci (Yahoo) bar: {s.yahoo_bar}")
    if s.gecikme_ms:
        print(f"Binance bar gecikmesi: ortalama {sum(s.gecikme_ms) / len(s.gecikme_ms):.0f} ms, azami {max(s.gecikme_ms):.0f} ms")
    print(f"dolumlar: {s.dolumlar}")
    hesap = cache.account_for_venue(Venue("BINANCE"))
    if hesap is not None:
        print("sandbox bakiye:", hesap.balance_total(Currency.from_str("USDT")), "·", hesap.balance_total(Currency.from_str("BTC")))
    node.dispose()


if __name__ == "__main__":
    asyncio.run(ana())
