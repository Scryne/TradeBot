"""Dalga 6 — token kilit açılımı: açılımdan önce perp kısa, BTC perp uzun (piyasa nötr). Saf backtest (I/O yok).

Olay (ön kayıt): ekip/yatırımcı (`insiders`, `privateSale`) cliff açılımı, aynı gün toplamı azami arzın ≥ `asgari_oran`'ı.
Kural takvimden (kodla), Jev'den değil (kural 8). Giriş açılım gününün `giris` gün öncesinin açılışında (00:00 UTC),
çıkış açılım gününün `cikis` gün sonrasının açılışında. Her olay bacak başına özkaynağın `notional`'ı; açık olayların
brüt toplamı 3x'i aşamaz (kural 6; aşarsa yeni olay kırpılır).

Günlük işaretleme: kısa bacak −r_token, uzun bacak +r_btc (günlük getiri, açılıştan açılışa). Funding 8 saatte bir:
kısa bacak `oran`'ı alır (negatifse öder), uzun bacak BTC `oran`'ını öder. Ücret (taker) ve kayma giriş/çıkışta, aleyhte.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl

from tradebot.cekirdek.boyut import KALDIRAC_TAVANI

GUN_MS = 86_400_000


@dataclass(frozen=True)
class KilitAyar:
    giris: int = -7
    cikis: int = 0
    notional: float = 0.10
    ucret: float = 0.0005          # Binance USDT-M taker
    kayma_token: float = 0.0005
    kayma_btc: float = 0.0001


def olaylar(tablo: pl.DataFrame, kategoriler: list[str], asgari_oran: float) -> pl.DataFrame:
    """Aynı token + aynı gün (UTC) seçili kategorilerin cliff'leri toplanır; eşiği geçenler."""
    return (tablo.filter(pl.col("kategori").is_in(kategoriler))
            .with_columns(gun_ms=pl.col("zaman_ms") // GUN_MS * GUN_MS)
            .group_by("sembol", "gun_ms").agg(pl.col("oran").sum(), pl.col("kategori").unique().sort().str.join("+"))
            .filter(pl.col("oran") >= asgari_oran).sort("gun_ms", "sembol"))


def _gunluk_getiri(bar: pl.DataFrame) -> dict[int, float]:
    o = bar.sort("acilis_ms")
    t, a = o["acilis_ms"].to_numpy(), o["open"].to_numpy()
    return {int(t[i]): float(a[i + 1] / a[i] - 1) for i in range(len(t) - 1) if t[i + 1] - t[i] == GUN_MS}


def _gunluk_funding(f: pl.DataFrame) -> dict[int, float]:
    if f.is_empty():
        return {}
    g = f.with_columns(gun=pl.col("zaman_ms") // GUN_MS * GUN_MS).group_by("gun").agg(pl.col("oran").sum())
    return dict(zip(g["gun"].to_list(), g["oran"].to_list(), strict=True))


def kos(ev: pl.DataFrame, barlar: dict[str, pl.DataFrame], fundingler: dict[str, pl.DataFrame], btc: pl.DataFrame,
        btc_funding: pl.DataFrame, a: KilitAyar, bas_ms: int, bit_ms: int) -> tuple[pl.DataFrame, pl.DataFrame]:
    """Döndürür: (günlük portföy getirisi [gun_ms, getiri, brut], olay tablosu [sembol, gun_ms, getiri, kurulmadi])."""
    rb, fb = _gunluk_getiri(btc), _gunluk_funding(btc_funding)
    gun_pnl: dict[int, float] = {}
    brut: dict[int, float] = {}
    olay_satir = []
    for e in ev.filter(pl.col("gun_ms").is_between(bas_ms, bit_ms - 1)).iter_rows(named=True):
        s, T = e["sembol"], int(e["gun_ms"])
        g0, g1 = T + a.giris * GUN_MS, T + a.cikis * GUN_MS
        if g1 >= bit_ms or s not in barlar:
            neden = "perp yok" if s not in barlar else "dönem dışı"
            olay_satir.append({"sembol": s, "gun_ms": T, "getiri": None, "kurulmadi": neden})
            continue
        rt, ft = _gunluk_getiri(barlar[s]), _gunluk_funding(fundingler.get(s, pl.DataFrame()))
        gunler = list(range(g0, g1, GUN_MS))
        if not gunler or any(d not in rt or d not in rb for d in gunler):
            olay_satir.append({"sembol": s, "gun_ms": T, "getiri": None, "kurulmadi": "fiyat eksik"})
            continue
        n = a.notional
        dolu = max(brut.get(d, 0.0) for d in gunler)   # pencere boyunca en yüksek açık brüt
        if dolu + 2 * n > KALDIRAC_TAVANI:
            n = max(0.0, (KALDIRAC_TAVANI - dolu) / 2)
            if n == 0:
                olay_satir.append({"sembol": s, "gun_ms": T, "getiri": None, "kurulmadi": "tavan"})
                continue
        maliyet = n * (2 * (a.ucret + a.kayma_token) + 2 * (a.ucret + a.kayma_btc))
        for i, d in enumerate(gunler):
            p = n * (-rt[d] + rb[d]) + n * (ft.get(d, 0.0) - fb.get(d, 0.0))
            if i == 0:
                p -= maliyet / 2
            if i == len(gunler) - 1:
                p -= maliyet / 2
            gun_pnl[d] = gun_pnl.get(d, 0.0) + p
            brut[d] = brut.get(d, 0.0) + 2 * n
        ham = sum(-rt[d] + rb[d] + ft.get(d, 0.0) - fb.get(d, 0.0) for d in gunler)   # olayın birim getirisi (bilgi)
        olay_satir.append({"sembol": s, "gun_ms": T, "kurulmadi": None,
                           "getiri": float(ham - 2 * (a.ucret + a.kayma_token) - 2 * (a.ucret + a.kayma_btc))})
    gunler = sorted(gun_pnl)
    seri = pl.DataFrame({"gun_ms": gunler, "getiri": [gun_pnl[d] for d in gunler], "brut": [brut[d] for d in gunler]},
                        schema={"gun_ms": pl.Int64, "getiri": pl.Float64, "brut": pl.Float64})
    return seri, pl.DataFrame(olay_satir, schema={"sembol": pl.Utf8, "gun_ms": pl.Int64, "getiri": pl.Float64,
                                                  "kurulmadi": pl.Utf8})


def haftalik(seri: pl.DataFrame, bas_ms: int, bit_ms: int) -> np.ndarray:
    """Günlük getiriden haftalık bileşik getiri; pozisyonsuz günler 0 (nakitte). Hafta Pazartesi başlar."""
    from tradebot.arastirma.metrik import HAFTA_MS, PAZARTESI_KAYMA_MS

    h0 = (bas_ms - PAZARTESI_KAYMA_MS) // HAFTA_MS
    h1 = (bit_ms - PAZARTESI_KAYMA_MS) // HAFTA_MS
    out = np.zeros(int(h1 - h0))
    for d, r in zip(seri["gun_ms"].to_list(), seri["getiri"].to_list(), strict=True):
        i = int((d - PAZARTESI_KAYMA_MS) // HAFTA_MS - h0)
        if 0 <= i < len(out):
            out[i] = (1 + out[i]) * (1 + r) - 1
    return out
