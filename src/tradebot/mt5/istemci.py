"""MT5 köprüsünün istemcisi (Docker tarafı). Köprü host Windows'ta (`kopru.py`), adres `host.docker.internal`.

Mumlar arşiv şemasına yakın bir tabloya döner: `acilis_ms` UTC, yalnız kapanmış barlar (köprü süzer). Uzun aralıklar
köprünün tek istek sınırına göre sayfalanır.
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

import polars as pl

from tradebot.mt5.kopru import EN_COK_BAR, SUTUNLAR, ZD

SEMA = {"acilis_ms": pl.Int64, "open": pl.Float64, "high": pl.Float64, "low": pl.Float64, "close": pl.Float64,
        "tick_volume": pl.Int64, "spread": pl.Int64, "real_volume": pl.Int64}


class KopruHatasi(RuntimeError):
    pass


class Mt5Istemci:
    def __init__(self, url: str, zaman_asimi: float = 90.0) -> None:
        self.url, self.zaman_asimi = url.rstrip("/"), zaman_asimi

    def _al(self, yol: str, **q) -> dict:
        adres = f"{self.url}{yol}" + (f"?{urllib.parse.urlencode(q)}" if q else "")
        try:
            with urllib.request.urlopen(adres, timeout=self.zaman_asimi) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            raise KopruHatasi(f"{yol}: HTTP {e.code} {e.read()[:300]!r}") from e
        except OSError as e:
            raise KopruHatasi(f"{yol}: {type(e).__name__}: {e}") from e

    def saglik(self) -> dict:
        return self._al("/saglik")

    def semboller(self, adlar: list[str] | None = None) -> dict:
        return self._al("/semboller", **({"ad": ",".join(adlar)} if adlar else {}))["semboller"]

    def kotasyon(self, semboller: list[str]) -> dict:
        return self._al("/kotasyon", semboller=",".join(semboller))

    def mumlar(self, sembol: str, zd: str, bas_ms: int, bit_ms: int) -> pl.DataFrame:
        """[bas_ms, bit_ms) aralığındaki kapanmış barlar. Köprü tek istekte EN_COK_BAR bar verir; sayfalanır."""
        adim = EN_COK_BAR * ZD[zd][1] * 1000
        parcalar = []
        b = bas_ms
        while b < bit_ms:
            s = min(b + adim, bit_ms)
            r = self._al("/mumlar", sembol=sembol, tf=zd, bas_ms=b, bit_ms=s)
            if "hata" in r and not r["satirlar"]:
                raise KopruHatasi(f"/mumlar {sembol} {zd}: MT5 {r['hata']}")
            parcalar.extend(r["satirlar"])
            b = s
        df = pl.DataFrame(parcalar, schema=SEMA, orient="row") if parcalar else pl.DataFrame(schema=SEMA)
        assert list(df.columns) == SUTUNLAR
        return df.unique("acilis_ms").sort("acilis_ms").filter(pl.col("acilis_ms") < bit_ms)
