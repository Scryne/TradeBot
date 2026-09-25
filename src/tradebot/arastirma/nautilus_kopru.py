"""NautilusTrader köprüsü: saf çekirdek stratejisini Nautilus'ta çalıştıran ince sarmalayıcı (Final Doküman §7-8).

Kural (Spike 02): Nautilus'ta bar verisiyle "sonraki açılışta dolum" modu yok. Gerçekçi doğrulama 1 dk yürütme
verisiyle yapılır: karar barı (ör. 1 gün) Nautilus'un 1 dk veriden İÇ olarak topladığı bardır; emir 1 ms gecikmeyle
borsaya ulaşır ve sinyalden sonraki ilk dakika barında dolar. Vektörel eşdeğeri: yürütme fiyatı = sonraki karar barının
ilk dakikasının kapanışı. Parity testi (tests/test_nautilus_parity.py) ikisinin birebir aynı olduğunu korur.

Nautilus'a dokunan her şey bu dosyadadır (sürüm değişikliği tek yerden karşılanır). Sürüm: 2.0.0rc5 (sabit).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from decimal import Decimal

import numpy as np
import polars as pl
from nautilus_trader.backtest import BacktestEngine
from nautilus_trader.common import LogLevel
from nautilus_trader.config import BacktestEngineConfig, LoggerConfig, StrategyConfig
from nautilus_trader.execution import StaticLatencyModel
from nautilus_trader.model import (
    AccountType,
    Bar,
    BarType,
    Currency,
    CurrencyPair,
    InstrumentId,
    Money,
    OmsType,
    OrderSide,
    Price,
    Quantity,
    Symbol,
    TraderId,
    Venue,
)
from nautilus_trader.trading import Strategy

from tradebot.cekirdek import Barlar, StratejiTanimi

NAKIT_TAMPONU = 0.98  # dolum fiyatı karar anında bilinmediği için (sonraki dakika) nakit hesabında pay


@dataclass(frozen=True)
class KriptoSpot:
    sembol: str = "BTCUSDT"
    piyasa: str = "BINANCE"
    taban: str = "BTC"
    kote: str = "USDT"
    fiyat_hassasiyeti: int = 2
    miktar_hassasiyeti: int = 5
    taker: Decimal = Decimal("0.001")

    def nautilus(self) -> CurrencyPair:
        return CurrencyPair(
            instrument_id=InstrumentId(Symbol(self.sembol), Venue(self.piyasa)), raw_symbol=Symbol(self.sembol),
            base_currency=Currency.from_str(self.taban), quote_currency=Currency.from_str(self.kote),
            price_precision=self.fiyat_hassasiyeti, size_precision=self.miktar_hassasiyeti,
            price_increment=Price(10**-self.fiyat_hassasiyeti, self.fiyat_hassasiyeti),
            size_increment=Quantity(10**-self.miktar_hassasiyeti, self.miktar_hassasiyeti), ts_event=0, ts_init=0,
            maker_fee=self.taker, taker_fee=self.taker, margin_init=Decimal(0), margin_maint=Decimal(0))


class CekirdekStratejiConfig(StrategyConfig):
    def __init__(self, *, instrument_id: InstrumentId, bar_type: BarType, tanim: StratejiTanimi, kote: str, **_kw) -> None:
        super().__init__()
        self.instrument_id, self.bar_type, self.tanim, self.kote = instrument_id, bar_type, tanim, kote


class CekirdekStratejisi(Strategy):
    """Her karar barında saf çekirdeği o ana kadarki geçmişle çağırır; hedef 0/1 değiştiğinde piyasa emri verir."""

    def __init__(self, config: CekirdekStratejiConfig) -> None:
        super().__init__(config)
        self._b: dict[str, list] = {k: [] for k in ("t", "open", "high", "low", "close", "volume")}
        self.kararlar: list[float] = []

    def on_start(self) -> None:
        self.subscribe_bars(self.config.bar_type)

    def on_bar(self, bar: Bar) -> None:
        adim = self.config.bar_type.spec.timedelta.total_seconds() * 1000 if hasattr(self.config.bar_type, "spec") else 0
        self._b["t"].append(int(bar.ts_event // 1_000_000 - adim))  # Nautilus ts_event = kapanış; çekirdek açılış ister
        for k in ("open", "high", "low", "close", "volume"):
            self._b[k].append(float(getattr(bar, k)))
        w = float(self.config.tanim.sinyal(Barlar.sozlukten(self._b))[-1])
        onceki = self.kararlar[-1] if self.kararlar else 0.0
        self.kararlar.append(w)
        if w == onceki:
            return
        iid = self.config.instrument_id
        ins = self.cache.instrument(iid)
        net = float(self.portfolio.net_position(iid))
        if w > 0 and net == 0.0:
            nakit = float(self.portfolio.account(venue=iid.venue).balance_free(Currency.from_str(self.config.kote)))
            adim_q = float(ins.size_increment)
            q = math.floor(nakit * NAKIT_TAMPONU * w / float(bar.close) / adim_q) * adim_q
            if q > 0:
                self.submit_order(self.order_factory.market(iid, OrderSide.BUY, ins.make_qty(q)))
        elif w == 0.0 and net > 0.0:
            self.submit_order(self.order_factory.market(iid, OrderSide.SELL, ins.make_qty(net)))


def dakika_barlari(df: pl.DataFrame, bar_type: BarType, fp: int, sp: int) -> list[Bar]:
    """acilis_ms'li 1 dk barlar → Nautilus Bar (ts_event = kapanış = açılış + 60 sn)."""
    return [Bar(bar_type, Price(o, fp), Price(h, fp), Price(lo, fp), Price(c, fp), Quantity(v, sp),
                (t + 60_000) * 1_000_000, (t + 60_000) * 1_000_000)
            for t, o, h, lo, c, v in df.select("acilis_ms", "open", "high", "low", "close", "volume").iter_rows()]


def calistir(dakika: pl.DataFrame, tanim: StratejiTanimi, karar: str = "1-DAY", baslangic_nakit: float = 100_000.0,
             ins: KriptoSpot | None = None) -> dict:
    ins = ins or KriptoSpot()
    ni = ins.nautilus()
    motor = BacktestEngine(BacktestEngineConfig(trader_id=TraderId("TRADEBOT-001"),
                                                logging=LoggerConfig(stdout_level=LogLevel.ERROR)))
    motor.add_venue(venue=ni.id.venue, oms_type=OmsType.NETTING, account_type=AccountType.CASH, base_currency=None,
                    starting_balances=[Money(baslangic_nakit, Currency.from_str(ins.kote))],
                    latency_model=StaticLatencyModel(base_latency_nanos=1_000_000))
    motor.add_instrument(ni)
    dk_tipi = BarType.from_str(f"{ni.id}-1-MINUTE-LAST-EXTERNAL")
    motor.add_data(dakika_barlari(dakika, dk_tipi, ins.fiyat_hassasiyeti, ins.miktar_hassasiyeti))
    karar_tipi = BarType.from_str(f"{ni.id}-{karar}-LAST-INTERNAL@1-MINUTE-EXTERNAL")
    s = CekirdekStratejisi(CekirdekStratejiConfig(instrument_id=ni.id, bar_type=karar_tipi, tanim=tanim, kote=ins.kote))
    motor.add_strategy(s)
    motor.run()
    dolum = motor.generate_order_fills_report()
    hesap = motor.cache.account_for_venue(ni.id.venue)
    out = {
        "kararlar": np.asarray(s.kararlar),
        "dolum_fiyat": [float(x) for x in dolum.sort_values("ts_last")["avg_px"]] if len(dolum) else [],
        "dolum_yon": [str(x) for x in dolum.sort_values("ts_last")["side"]] if len(dolum) else [],
        "nakit": float(hesap.balance_total(Currency.from_str(ins.kote))),
        "adet": float(motor.portfolio.net_position(ni.id)),
    }
    motor.dispose()
    return out
