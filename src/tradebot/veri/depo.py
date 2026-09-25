"""Veri depoları.

HamDepo: indirilen dosya OLDUĞU GİBİ saklanır; SHA-256 kimliğidir; asla üzerine yazılmaz. Aynı anahtarla farklı içerik
gelirse (ör. kaynak geçmişi düzeltti) yeni sürüm ayrı dosya olarak eklenir; ikisi de kalır.

BarDepo: normalize barlar (enstrüman × zaman dilimi başına bir Parquet). Hamdan yeniden üretilebilir türevdir;
atomik yazılır (geçici dosya + yeniden adlandırma). Şema: acilis_ms (UTC, barın açılışı), open, high, low, close,
volume ve kaynağa göre ek kolonlar (spread, quote_volume, trades).
"""
from __future__ import annotations

import hashlib
import os
from datetime import UTC, datetime
from pathlib import Path

import polars as pl
from sqlalchemy import insert, select
from sqlalchemy.engine import Engine

from tradebot.db import ham_dosya

BAR_KOLONLARI = ("acilis_ms", "open", "high", "low", "close", "volume")


def sha256(icerik: bytes) -> str:
    return hashlib.sha256(icerik).hexdigest()


def _guvenli(ad: str) -> str:
    return ad.replace(":", "__").replace("/", "_").replace("\\", "_")


class HamDepo:
    def __init__(self, kok: Path, motor: Engine) -> None:
        self.kok = Path(kok) / "ham"
        self.motor = motor

    def var_mi(self, kaynak: str, anahtar: str) -> str | None:
        """Bu anahtar için kayıtlı en son sürümün hash'i (yoksa None)."""
        with self.motor.connect() as b:
            return b.execute(select(ham_dosya.c.sha256).where(ham_dosya.c.kaynak == kaynak, ham_dosya.c.anahtar == anahtar)
                             .order_by(ham_dosya.c.id.desc()).limit(1)).scalar()

    def kaydet(
        self, kaynak: str, anahtar: str, icerik: bytes, uzanti: str, beklenen_sha: str | None = None
    ) -> tuple[Path, str, bool]:
        """Döndürür: (yol, sha256, yeni_mi). `beklenen_sha` verilirse (kaynağın yayınladığı sağlama) uyuşmazlıkta hata."""
        h = sha256(icerik)
        if beklenen_sha is not None and h != beklenen_sha.lower():
            raise ValueError(f"{kaynak}/{anahtar}: sağlama uyuşmuyor (beklenen {beklenen_sha[:12]}, gelen {h[:12]})")
        with self.motor.connect() as b:
            ayni = b.execute(select(ham_dosya.c.yol).where(ham_dosya.c.kaynak == kaynak, ham_dosya.c.anahtar == anahtar,
                                                            ham_dosya.c.sha256 == h)).scalar()
            if ayni is not None:
                return Path(ayni), h, False
            # Aynı içerik başka anahtarla zaten varsa dosya tekrar yazılmaz, yalnız eşleme kaydı eklenir
            # (ör. Dukascopy'de verisiz dönemlerin hepsi boş dosya: aynı hash, farklı anahtar).
            mevcut_dosya = b.execute(select(ham_dosya.c.yol).where(ham_dosya.c.sha256 == h).limit(1)).scalar()
        if mevcut_dosya is not None:
            yol = Path(mevcut_dosya)
        else:
            son = self.var_mi(kaynak, anahtar)
            ad = f"{anahtar}.{uzanti}" if son is None else f"{anahtar}.{h[:12]}.{uzanti}"
            yol = self.kok / kaynak / ad
            yol.parent.mkdir(parents=True, exist_ok=True)
            gecici = yol.with_suffix(yol.suffix + ".yaziliyor")
            gecici.write_bytes(icerik)
            os.replace(gecici, yol)
        with self.motor.begin() as b:
            b.execute(insert(ham_dosya).values(kaynak=kaynak, anahtar=anahtar, yol=str(yol), sha256=h, boyut=len(icerik),
                                               indirildi=datetime.now(UTC)))
        return yol, h, mevcut_dosya is None

    def dosyalar(self, kaynak: str, anahtar_on_eki: str = "") -> list[tuple[str, Path, str]]:
        """(anahtar, yol, sha) listesi; her anahtarın EN SON sürümü, anahtara göre sıralı."""
        with self.motor.connect() as b:
            satir = b.execute(select(ham_dosya.c.anahtar, ham_dosya.c.yol, ham_dosya.c.sha256)
                              .where(ham_dosya.c.kaynak == kaynak, ham_dosya.c.anahtar.like(f"{anahtar_on_eki}%"))
                              .order_by(ham_dosya.c.anahtar, ham_dosya.c.id)).all()
        son: dict[str, tuple[Path, str]] = {}
        for a, y, h in satir:
            son[a] = (Path(y), h)
        return [(a, y, h) for a, (y, h) in sorted(son.items())]


class BarDepo:
    def __init__(self, kok: Path) -> None:
        self.kok = Path(kok) / "bar"

    def yol(self, kimlik: str, zaman_dilimi: str) -> Path:
        return self.kok / zaman_dilimi / f"{_guvenli(kimlik)}.parquet"

    def oku(self, kimlik: str, zaman_dilimi: str, bas_ms: int | None = None, bit_ms: int | None = None) -> pl.DataFrame:
        y = self.yol(kimlik, zaman_dilimi)
        if not y.exists():
            return pl.DataFrame(schema={k: (pl.Int64 if k == "acilis_ms" else pl.Float64) for k in BAR_KOLONLARI})
        df = pl.read_parquet(y)
        if bas_ms is not None:
            df = df.filter(pl.col("acilis_ms") >= bas_ms)
        if bit_ms is not None:
            df = df.filter(pl.col("acilis_ms") < bit_ms)
        return df

    def yaz(self, kimlik: str, zaman_dilimi: str, yeni: pl.DataFrame, birlestir: bool = True) -> int:
        """Yeni barları mevcutla birleştirir (aynı açılışta YENİ kazanır), sıralar, atomik yazar. Dönüş: satır sayısı."""
        eksik = [k for k in BAR_KOLONLARI if k not in yeni.columns]
        if eksik:
            raise ValueError(f"eksik kolon: {eksik}")
        y = self.yol(kimlik, zaman_dilimi)
        df = yeni
        if birlestir and y.exists():
            df = pl.concat([pl.read_parquet(y), yeni], how="diagonal_relaxed")
        df = df.unique(subset="acilis_ms", keep="last", maintain_order=True).sort("acilis_ms")
        y.parent.mkdir(parents=True, exist_ok=True)
        gecici = y.with_suffix(".yaziliyor")
        df.write_parquet(gecici, compression="zstd")
        os.replace(gecici, y)
        return len(df)

    def kimlikler(self, zaman_dilimi: str) -> list[str]:
        d = self.kok / zaman_dilimi
        return sorted(p.stem.replace("__", ":") for p in d.glob("*.parquet")) if d.exists() else []


def turet(df: pl.DataFrame, hedef_ms: int, kaydirma_ms: int = 0) -> pl.DataFrame:
    """Alt zaman diliminden üst zaman dilimi (ör. 1h → 4h/1d). Kova = floor((t - kaydirma) / hedef) * hedef + kaydirma.

    `kaydirma_ms`: günlük kovanın başlangıcı (kripto 0 = 00:00 UTC). Açık/eksik bar varsa kova yine üretilir;
    eksiklik kalite raporunun işidir.
    """
    ek = [k for k in ("spread", "quote_volume", "trades") if k in df.columns]
    kova = ((pl.col("acilis_ms") - kaydirma_ms) // hedef_ms) * hedef_ms + kaydirma_ms
    return (df.sort("acilis_ms").group_by(kova.alias("kova"), maintain_order=True)
            .agg(pl.col("open").first(), pl.col("high").max(), pl.col("low").min(), pl.col("close").last(),
                 pl.col("volume").sum(), pl.len().alias("alt_bar"),
                 *[(pl.col(k).mean() if k == "spread" else pl.col(k).sum()) for k in ek])
            .rename({"kova": "acilis_ms"}))
