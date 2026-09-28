"""VİOP sürekli vadeli serisi (Faz 8): kurumun ham yakın vade serisinden backtest'e uygun günlük seri.

Neden (2026-09-28 ölçümü, `docs/spikes/08-mt5.md`): NCM'nin `XU30_YAKINVADE`'si ham yakın vadedir. Vade geçişinde bir
sonraki kontrata atlar ve fiyat iki kontratın baz farkı kadar sıçrar. TL faizi yüksekken bu tek günde +%7–15'tir
(2022-09-01 +%14,8, 2024-04-30 +%7,1, 2026-05-05 +%6,8; vadeli getirisi − spot getirisi). Ham seriyle koşan bir trend
backtest'i bu sıçramaları kâr sayar.

Kural (sonuca bakmadan, takvimden):
- Vade sonları: sözleşme aylarının (BIST30: çift aylar) son XIST iş günü.
- Geçiş günü: vade sonundan başlayan `pencere` iş gününün içinde |vadeli getirisi − spot getirisi|'nin en büyük olduğu
  gün (kurum geçişi vade günü ya da 1–3 gün sonra yapıyor).
- O günün vadeli getirisi spot getirisiyle değiştirilir: önceki bütün fiyatlar k = (1 + r_vadeli) / (1 + r_spot) ile
  çarpılır (oranla geri ayar; son fiyat gerçek vadeli fiyatıdır). Baz erimesi (taşıma maliyeti) seride kalır, yalnız
  kontrat değişiminin sıçraması çıkar.
- Önce imkânsız sıçra-dön barları atılır (2008-10-23: kapanış 10, gerçekte ~300; Yahoo'daki kuralın aynısı).
- Kurum serisindeki delik (2025-10-31 → 2026-05-05, 186 gün) doldurulmaz: `delikler` listesiyle raporlanır, backtest
  dönemi deliğin öncesiyle sınırlanır.

Spot seri: Yahoo `BIST:XU030` (günlük). Barlar gün başı (00:00 UTC) etiketlidir, iki seri gün üzerinden birleşir.
"""
from __future__ import annotations

import numpy as np
import polars as pl

from tradebot.veri.takvim import gun_basi, takvim

BIST30_AYLARI = (2, 4, 6, 8, 10, 12)
GUN_MS = 86_400_000


def vade_sonlari(bas_ms: int, bit_ms: int, aylar: tuple[int, ...] = BIST30_AYLARI) -> list[int]:
    """[bas, bit) içindeki sözleşme aylarının son XIST işlem günü (gün başı ms)."""
    gunler = takvim("XIST").gunluk_barlar(bas_ms, bit_ms)
    son: dict[tuple[int, int], int] = {}
    for g in gunler:
        t = np.datetime64(int(g), "ms").astype("datetime64[M]").astype(str)
        y, a = int(t[:4]), int(t[5:7])
        if a in aylar:
            son[(y, a)] = max(son.get((y, a), 0), int(g))
    return sorted(son.values())


def sicra_don(kapanis: np.ndarray, esik: float = 0.25) -> np.ndarray:
    """Kapanıştan kapanışa > ±%25 ve ertesi gün en az yarısı kadar geri dönen bar (bkz. `yahoo.normalize`)."""
    lr = np.diff(np.log(np.where(kapanis > 0, kapanis, np.nan)))
    sic = np.zeros(len(kapanis), dtype=bool)
    if len(lr) > 1:
        buyuk = np.abs(lr[:-1]) > np.log(1 + esik)
        don = (np.sign(lr[1:]) == -np.sign(lr[:-1])) & (np.abs(lr[1:]) >= 0.5 * np.abs(lr[:-1]))
        sic[1:-1] = buyuk & don
    return sic


def surekli(vadeli: pl.DataFrame, spot: pl.DataFrame, vadeler: list[int], pencere: int = 4,
            delik_gun: int = 30) -> tuple[pl.DataFrame, dict]:
    """Ham yakın vade (günlük) + spot → oranla geri ayarlanmış sürekli seri. Döndürür: (seri, rapor)."""
    v = vadeli.sort("acilis_ms")
    at = sicra_don(v["close"].to_numpy())
    v = v.filter(pl.Series(~at))
    j = v.join(spot.select("acilis_ms", pl.col("close").alias("spot")), on="acilis_ms", how="left")
    t = j["acilis_ms"].to_numpy()
    cv, cs = j["close"].to_numpy(), j["spot"].to_numpy()
    rv = np.r_[np.nan, cv[1:] / cv[:-1] - 1]
    rs = np.r_[np.nan, cs[1:] / cs[:-1] - 1]      # spot eksikse NaN: o gün geçiş adayı olamaz
    ara = np.r_[0, np.diff(t)] // GUN_MS
    carpan = np.ones(len(t))
    gecisler = []
    for e in vadeler:
        aday = np.flatnonzero(t >= e)[:pencere]
        aday = [i for i in aday if i > 0 and np.isfinite(rv[i]) and np.isfinite(rs[i]) and ara[i] <= 7]
        if not aday:
            continue
        i = max(aday, key=lambda k: abs(rv[k] - rs[k]))
        k = (1 + rv[i]) / (1 + rs[i])   # geçiş günü ayarlı getiri: (1 + r_v) / k − 1 = r_s
        carpan[:i] *= k
        gecisler.append({"vade_ms": e, "gecis_ms": int(t[i]), "vadeli": float(rv[i]), "spot": float(rs[i]), "k": float(k)})
    fiyat = ["open", "high", "low", "close"] + (["spread"] if "spread" in j.columns else [])  # spread fiyat birimi
    out = j.with_columns([(pl.col(c) * pl.Series(carpan)).alias(c) for c in fiyat] + [pl.Series("ayar", carpan)]) \
        .drop("spot")
    delikler = [{"bas_ms": int(t[i - 1]), "bit_ms": int(t[i]), "gun": int(ara[i])} for i in np.flatnonzero(ara > delik_gun)]
    return out, {"atilan_sicrama": int(at.sum()), "gecis": len(gecisler), "gecisler": gecisler, "delikler": delikler,
                 "ham_toplam_getiri": float(cv[-1] / cv[0] - 1), "ayarli_toplam_getiri": float(cv[-1] / (cv[0] * carpan[0]) - 1)}


AYLIK = tuple(range(1, 13))   # döviz vadelileri her ay vadelenir


def ters_mi(vadeli: pl.DataFrame, spot: pl.DataFrame) -> bool:
    """Kaynak seri spotla ters yönde mi kote (ör. TRY/USD)? Ortak günlerin günlük log getirisi korelasyonu < 0 ise."""
    j = vadeli.select("acilis_ms", pl.col("close").alias("v")).join(
        spot.select("acilis_ms", pl.col("close").alias("s")), on="acilis_ms").sort("acilis_ms")
    if j.height < 30:
        raise ValueError("ters kote tespiti için ortak gün yetersiz")
    rv, rs = np.diff(np.log(j["v"].to_numpy())), np.diff(np.log(j["s"].to_numpy()))
    ok = np.isfinite(rv) & np.isfinite(rs)
    return float(np.corrcoef(rv[ok], rs[ok])[0, 1]) < 0


def ters_cevir(df: pl.DataFrame) -> pl.DataFrame:
    """1/fiyat: yüksek ve düşük yer değiştirir."""
    return df.with_columns((1 / pl.col("open")).alias("open"), (1 / pl.col("low")).alias("high"),
                           (1 / pl.col("high")).alias("low"), (1 / pl.col("close")).alias("close"))


def saatlik_kapanis_gunluk(saatlik: pl.DataFrame, saat_utc: int) -> pl.DataFrame:
    """Saatlik barlardan günlük seri: her günün `saat_utc`'de biten barının kapanışı, gün başı etiketli. VİOP döviz
    vadelisi TR 18:10'da (15:10 UTC) kapanır; spotun da aynı anki kapanışı karşılaştırılır (gece FX hareketi karışmasın)."""
    return saatlik.filter((pl.col("acilis_ms") // 3_600_000) % 24 == saat_utc - 1).select(
        (pl.col("acilis_ms") // GUN_MS * GUN_MS).alias("acilis_ms"), "close")


def surekli_kur(depo, motor, kaynak: str, spot: pl.DataFrame, hedef: str, sinif: str, takvim_adi: str,
                para: str, aylar: tuple[int, ...]) -> dict:
    """Kaynak yakın vade (1d) + spot → `hedef` (1d) sürekli seri; enstrüman kaydı. Katalogdan türetilir, her koşuda
    baştan kurulur. Kaynak spotla ters kote ise önce çevrilir."""
    from tradebot.veri import enstruman as en

    v = depo.oku(kaynak, "1d")
    if v.is_empty() or spot.is_empty():
        return {"atlandi": "kaynak seri yok"}
    ters = ters_mi(v, spot)
    if ters:
        v = ters_cevir(v)
    t0, t1 = int(v["acilis_ms"].min()), int(v["acilis_ms"].max())
    seri, r = surekli(v, spot, vade_sonlari(gun_basi(t0), t1 + GUN_MS, aylar))
    kimlik = f"VIOP:{hedef}"
    depo.yaz(kimlik, "1d", seri, birlestir=False)
    en.kaydet(motor, [en.Enstruman("VIOP", hedef, sinif, takvim_adi, para, "turetilmis",
                                   {"kaynak": [kaynak], "ters_cevrildi": ters, "gecis": r["gecis"],
                                    "delikler": r["delikler"], "kural": "veri/viop.py surekli"})])
    en.sinir_guncelle(motor, kimlik, t0, t1)
    return {k: x for k, x in r.items() if k != "gecisler"} | {"ters_cevrildi": ters}


def xu030_surekli(depo, motor) -> dict:
    """VIOP:XU30_YAKINVADE + BIST:XU030 (Yahoo günlük) → VIOP:XU030_SUREKLI."""
    return surekli_kur(depo, motor, "VIOP:XU30_YAKINVADE", depo.oku("BIST:XU030", "1d"), "XU030_SUREKLI",
                       "endeks_vadeli", "viop_aksam", "TRY", BIST30_AYLARI)


def usdtry_surekli(depo, motor) -> dict:
    """VIOP:TRYUSD_YAKINVADE + Dukascopy USDTRY (15:00 UTC kapanışı) → VIOP:USDTRY_SUREKLI (VİOP 2, TL taşıma)."""
    spot = saatlik_kapanis_gunluk(depo.oku("DUKASCOPY:USDTRY", "1h"), 15)
    return surekli_kur(depo, motor, "VIOP:TRYUSD_YAKINVADE", spot, "USDTRY_SUREKLI", "doviz_vadeli", "viop", "TRY",
                       AYLIK)
