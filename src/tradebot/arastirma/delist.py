"""Dalga 12 — Binance spot delist duyurusu → token perp kısa + BTC perp uzun (piyasa nötr). Motor kilit ile aynı
(`arastirma/kilit.py` → `cekirdek/kilit.py`, kural 3).

Olay (kural 8: kod tetikler, Jev yalnız eler): delist kataloğunda başlığında "Will Delist <liste> on <tarih>" geçen
duyuru (oylamalı delist sonuçları dahil); marjin, vadeli, opsiyon ve kredi duyuruları hariç. Liste başlıktaki büyük
harfli sembollerdir. Olay günü T, yayın + `GECIKME_MS`'den sonraki ilk 00:00 UTC açılışıdır (giriş T'nin açılışında,
`cikis` gün tutulur). Jev'li varyant yalnız A1'in aynı tokena `token_delist` vetosu verdiği olayları tutar
(dondurulmuş yargılar; riski yalnız azaltır).

Perp tarafı (canlı düğümün `teslim_planli` korumasıyla aynı kural): Binance vadeli o perp'in kaldırılmasını duyurursa
pozisyon duyurudan sonraki ilk açılışta kapanır. Bunun için perp mumları o günden sonrası kesilir. Hacmi sıfır mumlar
(kaldırılmış kontratın donmuş fiyatı) işlem sayılmaz. Kaldırılmış kontratların mumları da API'den alınır: hayatta kalan
yanlılığı yok; yalnız hiç perp'i olmamış tokenlar "perp yok" sayılır.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import polars as pl
from sqlalchemy import select

from tradebot.db import metin, olay
from tradebot.veri import binance_vadeli as bv

GUN_MS = 86_400_000
GECIKME_MS = 60_000          # yayından sonra aleyhte tepki payı (zekâ katmanının geriye dönük gecikmesiyle aynı)
JEV_PENCERE_MS = GUN_MS      # Jev vetosu duyurudan en çok bu kadar önce/sonra görünürse aynı olaydır
_SPOT = re.compile(r"\bWill Delist (.+?) on \d{4}-\d{2}-\d{2}", re.I)
_HARIC = re.compile(r"Margin|Futures|Options|Loans?|Perpetual|Pairs", re.I)
_SEMBOL = re.compile(r"(?<![A-Za-z0-9])[A-Z0-9]{2,15}(?![A-Za-z0-9])")
_PERP = re.compile(r"(?<![A-Za-z0-9])([A-Z0-9]{2,20}USDT)(?![A-Za-z0-9])")
_ONEK = re.compile(r"^(1000000|1000|1M)(?=[A-Z0-9])")


def spot_delist(baslik: str) -> list[str]:
    """Başlık bir spot token delist duyurusuysa tokenlar, değilse boş liste."""
    m = _SPOT.search(baslik)
    if not m or _HARIC.search(baslik):
        return []
    return [t for t in _SEMBOL.findall(m.group(1)) if t != "AND"]


def perp_delist(baslik: str, govde: str) -> list[str]:
    """Başlık bir USDT-M perp kaldırma duyurusuysa kontratların tabanları (1000 öneki atılır). Başlıkta sembol yoksa
    ("Multiple ... Contracts") gövdeden alınır: fazla sembol erken kapanış demektir (aleyhte yön belirsiz, küçük)."""
    if not re.search(r"Futures (Will|to) Delist", baslik, re.I):
        return []
    if re.search(r"COIN-M|Coin-Margined", baslik, re.I) and not re.search(r"USD[ⓈS]-M|USDT-Margined", baslik):
        return []
    s = _PERP.findall(baslik) or _PERP.findall(govde)
    return sorted({_ONEK.sub("", x[: -len("USDT")]) for x in s})


def duyurular(motor) -> tuple[pl.DataFrame, pl.DataFrame]:
    """(spot delist olayları [sembol, yayin_ms, metin_id], perp kaldırma duyuruları [sembol, yayin_ms])."""
    with motor.connect() as b:
        rows = list(b.execute(select(metin.c.id, metin.c.baslik, metin.c.govde, metin.c.yayin_ms)
                              .where(metin.c.kaynak == "binance_duyuru", metin.c.katalog == "delist")))
    spot, perp = [], []
    for r in rows:
        spot += [(s, int(r.yayin_ms), int(r.id)) for s in spot_delist(r.baslik)]
        perp += [(s, int(r.yayin_ms)) for s in perp_delist(r.baslik, r.govde)]
    sp = pl.DataFrame(spot, schema={"sembol": pl.Utf8, "yayin_ms": pl.Int64, "metin_id": pl.Int64}, orient="row")
    pp = pl.DataFrame(perp, schema={"sembol": pl.Utf8, "yayin_ms": pl.Int64}, orient="row")
    return sp.sort("yayin_ms", "sembol"), pp.sort("yayin_ms", "sembol")


def jev_onaylari(motor) -> pl.DataFrame:
    """A1'in `token_delist` vetoları [sembol, gecerli_ms] (dondurulmuş yargılar; kaldırılan vetolar dahil değil)."""
    with motor.connect() as b:
        kal = {int(r.ayrinti["veto_id"]) for r in b.execute(select(olay.c.ayrinti).where(olay.c.tur == "kaldir"))}
        rows = [(r.enstruman, int(r.gecerli_ms)) for r in b.execute(
            select(olay.c.id, olay.c.enstruman, olay.c.gecerli_ms, olay.c.neden)
            .where(olay.c.tur == "veto", olay.c.rol.like("A1%"))) if "token_delist" in r.neden and r.id not in kal]
    return pl.DataFrame([(k.removeprefix("BINANCE:").removesuffix("USDT"), t) for k, t in rows],
                        schema={"sembol": pl.Utf8, "gecerli_ms": pl.Int64}, orient="row")


def olay_gunu(yayin_ms: int) -> int:
    return (yayin_ms + GECIKME_MS) // GUN_MS * GUN_MS + GUN_MS


def olaylar(spot: pl.DataFrame, jev: pl.DataFrame | None = None) -> pl.DataFrame:
    """Motor biçimi [sembol, gun_ms = T (giriş günü), oran = 1]. Aynı token ikinci kez duyurulursa ilki sayılır.
    `jev` verilirse yalnız ±`JEV_PENCERE_MS` içinde `token_delist` vetosu olan olaylar kalır."""
    satir, gorulen = [], set()
    onay: dict[str, list[int]] = {}
    if jev is not None:
        for s, t in jev.iter_rows():
            onay.setdefault(s, []).append(t)
    for s, y in spot.select("sembol", "yayin_ms").iter_rows():
        if s in gorulen:
            continue
        gorulen.add(s)
        if jev is not None and not any(abs(t - y) <= JEV_PENCERE_MS for t in onay.get(s, [])):
            continue
        satir.append((s, olay_gunu(y), 1.0))
    return pl.DataFrame(satir, schema={"sembol": pl.Utf8, "gun_ms": pl.Int64, "oran": pl.Float64},
                        orient="row").sort("gun_ms", "sembol")


def kirp(bar: pl.DataFrame, kapanis_ms: list[int]) -> pl.DataFrame:
    """Hacmi sıfır mumları atar; perp kaldırma duyurusu varsa duyurudan sonraki ilk açılıştan (D) sonrasını keser:
    D-1 → D getirisi kalır, D'de pozisyon "işlem görmüyor" sayılıp D'nin açılışında kapanır."""
    b = bar.filter(pl.col("volume") > 0)
    if kapanis_ms:
        b = b.filter(pl.col("acilis_ms") <= olay_gunu(min(kapanis_ms)))
    return b


def hazirla(veri_dizini: Path, ham, http_al, motor, kayitci=None) -> dict:
    """Duyurular + Jev onayları + olaylı her tokenın perp günlük mumu ve funding'i (ve BTC) → data/delist/."""
    d = Path(veri_dizini) / "delist"
    (d / "perp").mkdir(parents=True, exist_ok=True)
    spot, perp_kap = duyurular(motor)
    spot.write_parquet(d / "spot_delist.parquet")
    perp_kap.write_parquet(d / "perp_kapanis.parquet")
    jev_onaylari(motor).write_parquet(d / "jev.parquet")
    kayitli = bv.usdt_perpler(http_al, ham)
    semboller = sorted(set(spot["sembol"].to_list())) + ["BTC"]
    eslesme, hatali = {}, []
    for i, s in enumerate(semboller):
        adaylar = [kayitli[s]["sembol"]] if s in kayitli else [f"{s}USDT", f"1000{s}USDT"]
        for k in adaylar:
            if (d / "perp" / f"{s}_1d.parquet").exists():   # kaldığı yerden devam
                eslesme[s] = k
                break
            try:
                bar = bv.gunluk(http_al, ham, k)
            except Exception as e:  # noqa: BLE001 — hiç perp'i olmamış token (400 Invalid symbol)
                hatali.append({"sembol": k, "hata": f"{type(e).__name__}: {e}"[:80]})
                continue
            if bar.is_empty():
                continue
            bar.write_parquet(d / "perp" / f"{s}_1d.parquet")
            bv.funding(http_al, ham, k).write_parquet(d / "perp" / f"{s}_funding.parquet")
            eslesme[s] = k
            break
        if kayitci is not None and i % 25 == 0:
            kayitci.info("ilerleme", bitti=i + 1, toplam=len(semboller))
    (d / "perp_listesi.json").write_text(json.dumps(eslesme, ensure_ascii=False), encoding="utf-8")
    return {"spot_delist": spot.height, "token": len(semboller) - 1, "perp_eslesen": len(eslesme) - 1,
            "perp_kapanis": perp_kap.height, "jev_onay": int(pl.read_parquet(d / "jev.parquet").height),
            "hatali": len(hatali)}
