"""Dalga 6 — token kilit açılımı: açılımdan önce perp kısa, BTC perp uzun (piyasa nötr). Saf backtest (I/O yok).

Olay (ön kayıt): ekip/yatırımcı (`insiders`, `privateSale`) cliff açılımı, aynı gün toplamı azami arzın ≥ `asgari_oran`'ı.
Kural takvimden (kodla), Jev'den değil (kural 8). Giriş açılım gününün `giris` gün öncesinin açılışında (00:00 UTC),
çıkış açılım gününün `cikis` gün sonrasının açılışında. Her olay bacak başına özkaynağın `notional`'ı; açık olayların
brüt toplamı 3x'i aşamaz (kural 6; aşarsa yeni olay kırpılır). Günlük karar `cekirdek/kilit.py`'dedir (paper ile ortak).

Günlük işaretleme: kısa bacak −r_token, uzun bacak +r_btc (günlük getiri, açılıştan açılışa). Funding 8 saatte bir:
kısa bacak `oran`'ı alır (negatifse öder), uzun bacak BTC `oran`'ını öder. Ücret (taker) ve kayma giriş/çıkışta, aleyhte.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import polars as pl

from tradebot.cekirdek import kilit as ck
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
    azami_brut: float = KALDIRAC_TAVANI      # ön kayıt (e088b94): yalnız 3x brüt tavanı
    azami_btc: float = float("inf")          # paper kolu: risk motorunun enstrüman tavanı (0,5)
    zarar_kes: float | None = None           # olay zararı (bacak nominaline oranla) bu eşiğe ulaşınca ertesi açılışta kapat

    def kural(self) -> ck.KilitKural:
        return ck.KilitKural(self.giris, self.cikis, self.notional, self.azami_brut, self.azami_btc)


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
    """Döndürür: (günlük portföy getirisi [gun_ms, getiri, brut], olay tablosu [sembol, gun_ms, getiri, kurulmadi]).

    Karar her gün `cekirdek.kilit.gun_karari` ile verilir (paper düğümüyle aynı fonksiyon, kural 3). Gün `d`'de "işlem
    gören" = o gün açılıştan açılışa getirisi olan perp (d ve d+1 mumları var). Pozisyon, perp işlem görmez olursa o gün
    açılışta kapanır (delist). Maliyetin yarısı giriş, yarısı çıkış gününe yazılır."""
    rb, fb = _gunluk_getiri(btc), _gunluk_funding(btc_funding)
    kural = a.kural()
    secili = ev.filter(pl.col("gun_ms").is_between(bas_ms, bit_ms - 1))
    olay_satir, olaylar = [], []
    for e in secili.iter_rows(named=True):
        s, T = e["sembol"], int(e["gun_ms"])
        if T + a.cikis * GUN_MS >= bit_ms or s not in barlar:
            olay_satir.append({"sembol": s, "gun_ms": T, "getiri": None,
                               "kurulmadi": "perp yok" if s not in barlar else "dönem dışı"})
        else:
            olaylar.append(ck.Olay(s, T, float(e["oran"])))
    rt = {s: _gunluk_getiri(b) for s, b in barlar.items() if s in {o.sembol for o in olaylar}}
    ft = {s: _gunluk_funding(fundingler.get(s, pl.DataFrame())) for s in rt}
    gun_olay: dict[int, list[ck.Olay]] = {}
    for o in olaylar:
        gun_olay.setdefault(o.gun_ms + a.giris * GUN_MS, []).append(o)
    maliyet_birim = 2 * (a.ucret + a.kayma_token) + 2 * (a.ucret + a.kayma_btc)
    gun_pnl: dict[int, float] = {}
    brut: dict[int, float] = {}
    birim: dict[tuple[str, int], float] = {}
    acik: tuple[ck.Pozisyon, ...] = ()
    ilk = min([d for d in gun_olay] + [bas_ms]) // GUN_MS * GUN_MS
    for d in range(ilk, bit_ms, GUN_MS):
        bugun = gun_olay.get(d, [])
        if not bugun and not acik:
            continue
        gerek = {o.sembol for o in bugun} | {p.sembol for p in acik}
        islem = {s for s in gerek if d in rt[s]} if d in rb else set()
        kes = frozenset(p.anahtar for p in acik if a.zarar_kes is not None and birim[p.anahtar] <= -a.zarar_kes)
        k = ck.gun_karari(d, bugun, acik, islem, kural, zarar_kes=kes)
        for p, _ in k.kapat:
            gun_pnl[d] = gun_pnl.get(d, 0.0) - p.notional * maliyet_birim / 2
        for o, neden in k.red:
            olay_satir.append({"sembol": o.sembol, "gun_ms": o.gun_ms, "getiri": None,
                               "kurulmadi": {"islem_gormuyor": "fiyat eksik"}.get(neden, neden)})
        for p in k.ac:
            gun_pnl[d] = gun_pnl.get(d, 0.0) - p.notional * maliyet_birim / 2
            birim[p.anahtar] = -maliyet_birim
        for p in k.acik:
            r = -rt[p.sembol][d] + rb[d] + ft[p.sembol].get(d, 0.0) - fb.get(d, 0.0)
            gun_pnl[d] = gun_pnl.get(d, 0.0) + p.notional * r
            brut[d] = brut.get(d, 0.0) + 2 * p.notional
            birim[p.anahtar] += r
        acik = k.acik
    olay_satir += [{"sembol": s, "gun_ms": T, "kurulmadi": None, "getiri": float(g)} for (s, T), g in birim.items()]
    gunler = sorted(gun_pnl)
    seri = pl.DataFrame({"gun_ms": gunler, "getiri": [gun_pnl[d] for d in gunler],
                         "brut": [brut.get(d, 0.0) for d in gunler]},
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
