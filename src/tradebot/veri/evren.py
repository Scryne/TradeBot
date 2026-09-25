"""Tarihsel (point-in-time) evren: her gün için o gün işlem gören ve O GÜNE KADARKİ veriye göre likit enstrümanlar.

Evren tablosu (gün × enstrüman) bar verisinden önceden hesaplanır ve `data/evren/<grup>.parquet`'e yazılır:
- `mevcut`: son `taze_gun` gün içinde barı var mı (listelenmemiş, kaldırılmış ya da uzun boşluktaki enstrüman girmez;
  kimlik kırılmasında yeni varlık boşluktan sonra yeniden "listelenmiş" gibi girer).
- `likidite`: son `pencere` günün işlem hacmi (kote para birimiyle; kripto quote_volume, borsa close × volume).
  Yalnız o güne kadarki barlardan hesaplanır: gün d'nin değeri d dahil geçmiş günlerden gelir, d+1 ve sonrasını görmez.
Sorgu: `evren(tablo, gun_ms, ilk_n)` → o gün mevcut olanlar, likiditeye göre ilk N.
"""
from __future__ import annotations

from pathlib import Path

import polars as pl

from tradebot.veri.depo import BarDepo

GUN = 86_400_000


def gunluk_likidite(df: pl.DataFrame) -> pl.DataFrame:
    """Barlardan (herhangi bir zaman dilimi) güne göre işlem hacmi."""
    hacim = pl.col("quote_volume") if "quote_volume" in df.columns else pl.col("close") * pl.col("volume")
    return (df.with_columns((pl.col("acilis_ms") // GUN * GUN).alias("gun"))
              .group_by("gun").agg(hacim.sum().alias("hacim")).sort("gun"))


def tablo_kur(depo: BarDepo, kimlikler: list[str], zaman_dilimi: str, bas_ms: int, bit_ms: int,
              pencere: int = 30, taze_gun: int = 3) -> pl.DataFrame:
    gunler = pl.DataFrame({"gun": pl.int_range(bas_ms // GUN * GUN, bit_ms, GUN, eager=True)})
    parcalar = []
    for k in kimlikler:
        g = gunluk_likidite(depo.oku(k, zaman_dilimi))
        if g.is_empty():
            continue
        tam = (gunler.join(g, on="gun", how="left")
               .with_columns(pl.col("hacim").is_not_null().alias("_bar"), pl.col("hacim").fill_null(0.0))
               .with_columns(pl.col("hacim").rolling_sum(window_size=pencere, min_samples=1).alias("likidite"),
                             pl.col("_bar").cast(pl.Int32).rolling_sum(window_size=taze_gun, min_samples=1).gt(0).alias("mevcut"))
               .filter(pl.col("gun") >= g["gun"].min())
               .select("gun", pl.lit(k).alias("kimlik"), "mevcut", "likidite"))
        parcalar.append(tam)
    return pl.concat(parcalar) if parcalar else pl.DataFrame(schema={"gun": pl.Int64, "kimlik": pl.Utf8,
                                                                      "mevcut": pl.Boolean, "likidite": pl.Float64})


def evren(tablo: pl.DataFrame, gun_ms: int, ilk_n: int | None = None) -> list[str]:
    g = gun_ms // GUN * GUN
    d = tablo.filter((pl.col("gun") == g) & pl.col("mevcut")).sort("likidite", descending=True)
    if ilk_n:
        d = d.head(ilk_n)
    return d["kimlik"].to_list()


def yaz(tablo: pl.DataFrame, veri_dizini: Path, grup: str) -> Path:
    y = Path(veri_dizini) / "evren" / f"{grup}.parquet"
    y.parent.mkdir(parents=True, exist_ok=True)
    tablo.write_parquet(y, compression="zstd")
    return y


def oku(veri_dizini: Path, grup: str) -> pl.DataFrame:
    return pl.read_parquet(Path(veri_dizini) / "evren" / f"{grup}.parquet")
