"""Binance USDT-M perp arşivi (data.binance.vision): saatlik mum, funding ve 5 dakikalık açık pozisyon (metrics).

Evren arşivin S3 listelemesindeki TÜM USDT perp'leri (kaldırılmışlar dahil → hayatta kalma yanlılığı yok; `fapi`
`exchangeInfo` kaldırılanları göstermez). Ham zip olduğu gibi saklanır (kural 9); türevler `data/um/` altında sembol
başına Parquet: `1h/<S>.parquet`, `funding/<S>.parquet`, `oi/<S>.parquet` (5 dk OI → saatlik son değer).

Metrics günlük dosyadır (sembol × gün): yalnız `asgari_hacim`'i geçen aylar indirilir (aylık quote hacmi, USDT).
Aylık dosyalar yayınlanan SHA-256 ile doğrulanır; günlük metrics sağlaması atlanır (istek sayısını yarıya indirir).
"""
from __future__ import annotations

import io
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import polars as pl

from tradebot.kayit import log
from tradebot.veri.binance import ARSIV, S3, funding_zip_oku, kline_zip_oku
from tradebot.veri.depo import HamDepo
from tradebot.veri.http import NazikIstemci, YokHatasi

SAAT_MS = 3_600_000
_log = log("veri.binance_um")


def metrics_zip_oku(icerik: bytes) -> pl.DataFrame:
    """5 dakikalık satırlar → saatlik son açık pozisyon (adet ve USDT). Saat = satırın düştüğü saatin AÇILIŞI.

    Satır zamanı (`create_time`) ölçüm anıdır; saat h'nin son ölçümü h+1 açılışından önce bilinir, yani saatlik
    barla aynı anda (kapanışta) görülebilir. Boş kolonlar ("") null olur."""
    with zipfile.ZipFile(io.BytesIO(icerik)) as z:
        df = pl.read_csv(io.BytesIO(z.read(z.namelist()[0])), infer_schema_length=0)
    if df.is_empty():
        return pl.DataFrame(schema={"acilis_ms": pl.Int64, "oi": pl.Float64, "oi_usdt": pl.Float64})
    t = pl.col("create_time").str.to_datetime("%Y-%m-%d %H:%M:%S", time_zone="UTC").dt.epoch("ms")
    return (df.select(t.alias("t"), pl.col("sum_open_interest").cast(pl.Float64, strict=False).alias("oi"),
                      pl.col("sum_open_interest_value").cast(pl.Float64, strict=False).alias("oi_usdt"))
            .drop_nulls("oi").sort("t")
            .group_by((pl.col("t") // SAAT_MS * SAAT_MS).alias("acilis_ms"), maintain_order=True)
            .agg(pl.col("oi").last(), pl.col("oi_usdt").last()))


class BinanceUM:
    def __init__(self, veri_dizini: Path, motor, isci: int = 16) -> None:
        self.ham = HamDepo(veri_dizini, motor)
        self.kok = Path(veri_dizini) / "um"
        self.http = NazikIstemci("binance_um", aralik_sn=0.01, baglanti=isci + 4)
        self.isci = isci

    def _liste(self, prefix: str, desen: str) -> list[str]:
        import re
        out, marker = [], ""
        while True:
            x = self.http.al(S3, {"delimiter": "/", "prefix": prefix} | ({"marker": marker} if marker else {})).decode()
            parca = re.findall(desen, x)
            out += parca
            if "<IsTruncated>true</IsTruncated>" not in x or not parca:
                return out
            marker = re.findall(r"<(?:Key|Prefix)>(.*?)</(?:Key|Prefix)>", x)[-1]

    def semboller(self) -> list[str]:
        p = "data/futures/um/monthly/klines/"
        return sorted(s for s in self._liste(p, rf"<Prefix>{p}([^/]+)/</Prefix>") if s.endswith("USDT"))

    def _al(self, anahtar_s3: str, mantiksal: str, sagla: bool) -> bytes | None:
        if (h := self.ham.var_mi("binance", mantiksal)) is not None:
            y = [p for a, p, s in self.ham.dosyalar("binance", mantiksal) if a == mantiksal and s == h]
            return y[0].read_bytes() if y else None
        try:
            icerik = self.http.al(f"{ARSIV}/{anahtar_s3}")
            saglama = None
            if sagla:
                try:
                    saglama = self.http.al(f"{ARSIV}/{anahtar_s3}.CHECKSUM").decode().split()[0]
                except YokHatasi:
                    pass
        except YokHatasi:
            return None
        self.ham.kaydet("binance", mantiksal, icerik, "zip", beklenen_sha=saglama)
        return icerik

    def _yaz(self, alt: str, sembol: str, df: pl.DataFrame, anahtar: str) -> None:
        y = self.kok / alt / f"{sembol}.parquet"
        y.parent.mkdir(parents=True, exist_ok=True)
        df.unique(anahtar, keep="last").sort(anahtar).write_parquet(y, compression="zstd")

    def sembol(self, s: str, metrics: bool, asgari_hacim: float) -> dict:
        """Bir sembolün 1h mumu ve funding'i; `metrics` ise hacim eşiğini geçen aylarda günlük OI."""
        kl = self._liste(f"data/futures/um/monthly/klines/{s}/1h/", r"<Key>([^<]*.zip)</Key>")
        parca = [kline_zip_oku(b) for k in kl
                 if (b := self._al(k, "um/klines/1h/" + k.rsplit("/", 1)[1][:-4], True)) is not None]
        parca = [p for p in parca if not p.is_empty()]
        if not parca:
            return {"sembol": s, "bar": 0}
        bar = pl.concat(parca)
        self._yaz("1h", s, bar, "acilis_ms")
        fl = self._liste(f"data/futures/um/monthly/fundingRate/{s}/", r"<Key>([^<]*.zip)</Key>")
        fp = [funding_zip_oku(b) for k in fl
              if (b := self._al(k, "um/funding/" + k.rsplit("/", 1)[1][:-4], True)) is not None]
        fp = [p for p in fp if not p.is_empty()]
        if fp:
            self._yaz("funding", s, pl.concat(fp), "zaman_ms")
        oi_gun = 0
        if metrics:
            ay = (bar.with_columns(ay=pl.from_epoch("acilis_ms", "ms").dt.strftime("%Y-%m"))
                  .group_by("ay").agg(pl.col("quote_volume").sum()).filter(pl.col("quote_volume") >= asgari_hacim))
            aylar = set(ay["ay"].to_list())
            if aylar:
                ml = self._liste(f"data/futures/um/daily/metrics/{s}/", r"<Key>([^<]*.zip)</Key>")
                ml = [k for k in ml if k.rsplit("-metrics-", 1)[1][:7] in aylar]
                op = [metrics_zip_oku(b) for k in ml
                      if (b := self._al(k, "um/metrics/" + k.rsplit("/", 1)[1][:-4], False)) is not None]
                op = [p for p in op if not p.is_empty()]
                if op:
                    self._yaz("oi", s, pl.concat(op), "acilis_ms")
                oi_gun = len(op)
        return {"sembol": s, "bar": bar.height, "funding": len(fp), "oi_gun": oi_gun}

    def hepsi(self, metrics: bool = True, asgari_hacim: float = 3e8, sinir: int | None = None) -> dict:
        ss = self.semboller()[:sinir] if sinir else self.semboller()
        sonuc, hata = [], []
        with ThreadPoolExecutor(max_workers=self.isci) as h:
            fs = {h.submit(self.sembol, s, metrics, asgari_hacim): s for s in ss}
            for i, f in enumerate(as_completed(fs), 1):
                try:
                    sonuc.append(f.result())
                except Exception as e:  # noqa: BLE001 — tek sembol evreni durdurmaz; yeniden koşu kaldığı yerden sürer
                    hata.append({"sembol": fs[f], "hata": f"{type(e).__name__}: {e}"[:160]})
                if i % 25 == 0:
                    _log.info("ilerleme", bitti=i, toplam=len(ss), hata=len(hata))
        return {"sembol": len(ss), "bar_olan": sum(1 for r in sonuc if r["bar"]),
                "oi_olan": sum(1 for r in sonuc if r.get("oi_gun")), "hata": hata[:20], "hata_sayisi": len(hata)}
