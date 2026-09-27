"""MT5 verisi (Faz 8, Spike 08): NCM demo hesaplarının barları köprüden kataloğa.

- Enstrümanlar `config/evren.yaml` `mt5`'ten; önekli gruplar (VİOP vadelileri) köprünün bugünkü sembol listesinden açılır.
- Her (enstrüman, zaman dilimi) için son bardan sonrası istenir (yoksa `derinlik_gun` geriden). Köprü yalnız kapanmış
  barı ve UTC açılış zamanını verir (kural 4, 11).
- Ham yanıtlar (köprünün JSON'u, sunucu saat farkı dahil) HamDepo'ya yazılır; barlar ondan yeniden üretilebilir (kural 9).
- 1d barlar seans gününün 00:00 UTC'sine etiketlenir: MT5'in günlük barı sunucu gece yarısında açılır (NCM: 21:00 UTC,
  önceki takvim günü). Katalogdaki diğer günlük veriler (Yahoo, Dukascopy) gün başı gösterimini kullanır.
- `volume`: VİOP'ta gerçek hacim (kontrat), CFD'de tik hacmi. `spread` nokta cinsinden korunur (maliyet modeli).
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import polars as pl
from sqlalchemy.engine import Engine

from tradebot.kayit import log
from tradebot.mt5.istemci import KopruHatasi, Mt5Istemci
from tradebot.veri import enstruman as en
from tradebot.veri.depo import BarDepo, HamDepo
from tradebot.veri.takvim import ZAMAN_DILIMI_MS, gun_basi

MT5_ZD = {"1m": "M1", "1h": "H1", "1d": "D1"}
_log = log("veri.mt5")


def katalog_barlari(df: pl.DataFrame, zd: str, fark_ms: int, gercek_hacim: bool) -> pl.DataFrame:
    """Köprü tablosu → katalog şeması. 1d: açılış (UTC) + sunucu farkı = sunucu günü → o günün 00:00 UTC'si."""
    if zd == "1d":
        df = df.with_columns(pl.col("acilis_ms").map_elements(lambda t: gun_basi(t + fark_ms), return_dtype=pl.Int64))
    hacim = pl.col("real_volume") if gercek_hacim else pl.col("tick_volume")
    return df.with_columns(volume=hacim.cast(pl.Float64)).select(
        "acilis_ms", "open", "high", "low", "close", "volume", "tick_volume", "spread", "real_volume")


class Mt5Veri:
    def __init__(self, veri_dizini: Path, motor: Engine, istemciler: dict[str, Mt5Istemci],
                 evren: dict | None = None, saat=lambda: int(time.time() * 1000)) -> None:
        self.saat = saat
        self.ham = HamDepo(veri_dizini, motor)
        self.bar = BarDepo(veri_dizini)
        self.motor, self.istemciler = motor, istemciler
        self.evren = evren or en.evren_yukle()

    def enstrumanlar(self) -> list[en.Enstruman]:
        mevcut = {h: [s for s, _ in i.semboller()] for h, i in self.istemciler.items()}
        return en.mt5_enstrumanlari(self.evren, mevcut)

    def _bir(self, e: en.Enstruman, zd: str, simdi_ms: int) -> dict:
        ist = self.istemciler[e.meta["hesap"]]
        eski = self.bar.oku(e.kimlik, zd)
        adim = ZAMAN_DILIMI_MS[zd]
        derinlik = self.evren["mt5"]["derinlik_gun"][zd] * 86_400_000
        # 1d etiketi gün başıdır, MT5 açılışı önceki gün 21:00 UTC: bir gün geriden iste (birleştirmede yenisi kazanır)
        bas = simdi_ms - derinlik if eski.is_empty() else int(eski["acilis_ms"].max()) + adim - (adim if zd == "1d" else 0)
        fark = {"ms": None}

        def ham(anahtar: str, icerik: bytes) -> None:
            self.ham.kaydet("mt5", f"{e.meta['hesap']}/{anahtar}", icerik, "json")
            if fark["ms"] is None:
                fark["ms"] = json.loads(icerik)["fark_sn"] * 1000

        df = ist.mumlar(e.sembol, MT5_ZD[zd], bas, simdi_ms, ham=ham, hatada_devam=True)
        if df.is_empty():
            return {"kimlik": e.kimlik, "zd": zd, "yeni": 0, "hata": ist.son_hatalar[:1] or None}
        yeni = katalog_barlari(df, zd, fark["ms"], gercek_hacim=e.piyasa == "VIOP")
        n = self.bar.yaz(e.kimlik, zd, yeni)
        return {"kimlik": e.kimlik, "zd": zd, "yeni": len(yeni), "toplam": n}

    def guncelle(self, butce_dk: float = 60.0) -> list[dict]:
        """Bütün MT5 enstrümanları, bütün zaman dilimleri. Bir enstrümanın hatası diğerlerini durdurmaz."""
        bitis = time.monotonic() + butce_dk * 60
        liste = self.enstrumanlar()
        en.kaydet(self.motor, liste)
        out = []
        for e in liste:
            for zd in self.evren["mt5"]["zaman_dilimleri"]:
                if time.monotonic() > bitis:
                    out.append({"kimlik": e.kimlik, "zd": zd, "atlandi": "butce"})
                    continue
                try:
                    r = self._bir(e, zd, self.saat())
                except KopruHatasi as ex:
                    r = {"kimlik": e.kimlik, "zd": zd, "hata": str(ex)[:200]}
                    _log.warning("mt5_bar_hatasi", **r)
                out.append(r)
            d = self.bar.oku(e.kimlik, "1h")
            if not d.is_empty():
                en.sinir_guncelle(self.motor, e.kimlik, int(d["acilis_ms"].min()), int(d["acilis_ms"].max()))
        return out
