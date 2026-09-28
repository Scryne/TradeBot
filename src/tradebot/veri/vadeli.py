"""Dalga 3 vadeli serileri (günlük): gerçek vadeli (geçiş ayıklanmış) ya da vadeli fazla getirisi vekili.

Neden (2026-09-28 ölçümü, `docs/turnuva/Arastirma-Plani.md` › Dalga 3 tasarım notu): NCM'nin `ES!`/`NQ!`/`YM!`
sürekli grafikleri ayarsız ön aydır; vade geçişinde baz kadar (2023–25'te ~+100 bps) sıçrar. Ham seriyle koşan bir
trend backtest'i bu sıçramaları kâr sayar. Altın, gümüş ve dövizde uzun vadeli geçmiş yalnız spotta var.

İki yöntem (sonuca bakmadan, takvimden):

1. **Endeks vadelisi — pencere ayarı.** CME kontratları Mart/Haziran/Eylül/Aralık'ın 3. Cuması vadelenir. Geçiş
   penceresi vade gününden 3 işlem günü önce başlar, 2 gün sonra biter (NCM geçişi 18–19 Mart / 18–19 Eylül 2024'te
   ölçüldü; sıçrama iki güne yayılıyor: iki kaynağın kapanış saati farklı). Pencerenin her gününde vadeli getirisi spot
   getirisiyle değiştirilir; önceki fiyatlar oranla geri ayarlanır (son fiyat gerçek vadeli fiyatıdır). Pencere
   boyunca günlük getiriler toplanınca kapanış saati farkı birbirini götürür; geçiş sıçramasının tamamı çıkar, pencere
   içindeki ~6 günlük baz erimesi (~%0,07) de gider (ihmal edilir).
2. **Metal ve döviz — fazla getiri vekili.** Vadeli fiyatı F = S·e^{(r_taban − r_kote)T} olduğundan sürekli tutulan
   vadelinin getirisi ≈ spot getiri + (r_taban − r_kote)·Δt. Döviz çiftinde taban/kote para birimlerinin faizi, metalde
   taban faiz 0 (kira oranı yok sayılır; uzun için aleyhte). Faiz `veri/faiz.py`, iki ay gecikmeli (PIT).

Her iki seride de yıllık faiz ayrıca eklenmez: getiri zaten nakit üstü (fazla) getiridir; turnuva çıtası 0.
"""
from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import numpy as np
import polars as pl

from tradebot.veri import faiz as fz

GUN_MS = 86_400_000
CME_AYLARI = (3, 6, 9, 12)
ONCE, SONRA = 3, 2

# kimlik → (kaynak vadeli, spot) — endeks vadelisi, pencere ayarı
ENDEKS = {
    "ES": ("NCMFX:ES!", "DUKASCOPY:USA500IDXUSD"),
    "NQ": ("NCMFX:NQ!", "DUKASCOPY:USATECHIDXUSD"),
    "YM": ("NCMFX:YM!", "DUKASCOPY:USA30IDXUSD"),
}
# kimlik → (spot, taban para, kote para, sınıf) — fazla getiri vekili; taban None = metal (faizi 0)
VEKIL = {
    "XAU": ("DUKASCOPY:XAUUSD", None, "USD", "metal"),
    "XAG": ("DUKASCOPY:XAGUSD", None, "USD", "metal"),
    "EURUSD": ("DUKASCOPY:EURUSD", "EUR", "USD", "fx"),
    "GBPUSD": ("DUKASCOPY:GBPUSD", "GBP", "USD", "fx"),
    "USDJPY": ("DUKASCOPY:USDJPY", "USD", "JPY", "fx"),
    "AUDUSD": ("DUKASCOPY:AUDUSD", "AUD", "USD", "fx"),
    "USDCAD": ("DUKASCOPY:USDCAD", "USD", "CAD", "fx"),
    "USDCHF": ("DUKASCOPY:USDCHF", "USD", "CHF", "fx"),
}


def ucuncu_cuma(y: int, a: int) -> date:
    ilk = date(y, a, 1)
    return ilk + timedelta(days=(4 - ilk.weekday()) % 7 + 14)


def cme_vadeleri(bas_ms: int, bit_ms: int) -> list[int]:
    """[bas, bit) içindeki CME çeyrek vadeleri (gün başı ms, UTC)."""
    b = datetime.fromtimestamp(bas_ms / 1000, UTC).date()
    s = datetime.fromtimestamp(bit_ms / 1000, UTC).date()
    out = []
    for y in range(b.year, s.year + 1):
        for a in CME_AYLARI:
            g = ucuncu_cuma(y, a)
            ms = int(datetime(g.year, g.month, g.day, tzinfo=UTC).timestamp() * 1000)
            if bas_ms <= ms < bit_ms:
                out.append(ms)
    return out


def _olcekle(df: pl.DataFrame, carpan: np.ndarray) -> pl.DataFrame:
    return df.with_columns([(pl.col(c) * pl.Series(carpan)).alias(c) for c in ("open", "high", "low", "close")])


def pencere_ayari(vadeli: pl.DataFrame, spot: pl.DataFrame, vadeler: list[int], once: int = ONCE,
                  sonra: int = SONRA) -> tuple[pl.DataFrame, dict]:
    """Ham ön ay (günlük) + spot → geçiş pencereleri spot getirisiyle değiştirilmiş, oranla geri ayarlı seri."""
    v = vadeli.sort("acilis_ms").select("acilis_ms", "open", "high", "low", "close", "volume")
    j = v.join(spot.select("acilis_ms", pl.col("close").alias("spot")), on="acilis_ms", how="left")
    t = j["acilis_ms"].to_numpy()
    cv, cs = j["close"].to_numpy(), j["spot"].to_numpy()
    carpan = np.ones(len(t))
    gecisler, eksik = [], 0
    for e in vadeler:
        i = int(np.searchsorted(t, e))
        if i >= len(t) or t[i] - e > 5 * GUN_MS:     # vade serinin dışında ya da uzun delik
            continue
        top_v, top_s = 0.0, 0.0
        for d in range(max(1, i - once), min(len(t), i + sonra + 1)):
            if not (np.isfinite(cs[d]) and np.isfinite(cs[d - 1])):
                eksik += 1
                continue
            k = (cv[d] / cv[d - 1]) / (cs[d] / cs[d - 1])     # günün ayarı: vadeli getirisi → spot getirisi
            carpan[:d] *= k
            top_v += np.log(cv[d] / cv[d - 1])
            top_s += np.log(cs[d] / cs[d - 1])
        gecisler.append({"vade_ms": e, "sicrama": float(top_v - top_s)})
    s = [g["sicrama"] for g in gecisler]
    return _olcekle(j.drop("spot"), carpan), {
        "gecis": len(gecisler), "eksik_spot_gunu": eksik, "sicrama_medyan": float(np.median(s)) if s else None,
        "sicrama_toplam": float(np.sum(s)) if s else 0.0,
        "ham_toplam_getiri": float(cv[-1] / cv[0] - 1), "ayarli_toplam_getiri": float(cv[-1] / (cv[0] * carpan[0]) - 1)}


def fazla_getiri(spot: pl.DataFrame, r_taban: np.ndarray, r_kote: np.ndarray) -> tuple[pl.DataFrame, dict]:
    """Spot (günlük) + iki faiz (gün başına, yıllık ondalık) → vadeli fazla getirisi vekili (son fiyat = spot)."""
    s = spot.sort("acilis_ms").select("acilis_ms", "open", "high", "low", "close", "volume")
    t = s["acilis_ms"].to_numpy()
    fark = np.nan_to_num(np.asarray(r_taban, float)) - np.nan_to_num(np.asarray(r_kote, float))
    dt_yil = np.r_[0.0, np.diff(t) / GUN_MS / 365.0]
    tasima = np.exp(np.cumsum(fark * dt_yil))           # t anına kadar birikmiş taşıma
    carpan = tasima / tasima[-1]
    return _olcekle(s, carpan), {"tasima_toplam": float(tasima[-1] - 1), "fark_ort": float(np.mean(fark))}


def kur(depo, motor, faiz_csv: bytes) -> dict:
    """Bütün VADELI:* serilerini katalogdan baştan kurar ve kaydeder. Dönüş: seri başına rapor."""
    from tradebot.veri import enstruman as en

    aylik = fz.coz(faiz_csv)
    rapor, kayit = {}, []
    for ad, (kaynak, spot_k) in ENDEKS.items():
        v, sp = depo.oku(kaynak, "1d"), depo.oku(spot_k, "1d")
        if v.is_empty() or sp.is_empty():
            rapor[ad] = {"atlandi": "kaynak yok"}
            continue
        # spotun olmadığı dönemde geçiş ayıklanamaz: seri spotun kapsadığı aralığa kırpılır (YM spotu 2013'ten;
        # Dukascopy günlük dosyaları yıllık yayımlanır, 2026 henüz yok)
        v = v.filter(pl.col("acilis_ms").is_between(sp["acilis_ms"].min(), sp["acilis_ms"].max()))
        vadeler = cme_vadeleri(int(v["acilis_ms"].min()), int(v["acilis_ms"].max()) + 30 * GUN_MS)
        seri, r = pencere_ayari(v, sp, vadeler)
        rapor[ad] = r
        kayit.append((ad, "endeks", seri, {"kaynak": [kaynak, spot_k], "yontem": "pencere_ayari", "once": ONCE,
                                           "sonra": SONRA}))
    for ad, (spot_k, taban, kote, sinif) in VEKIL.items():
        sp = depo.oku(spot_k, "1d")
        if sp.is_empty():
            rapor[ad] = {"atlandi": "kaynak yok"}
            continue
        g = sp.sort("acilis_ms")["acilis_ms"].to_numpy()
        rt = np.zeros(len(g)) if taban is None else fz.gunluk(aylik.get(fz.PARA[taban], {}), g)
        rk = fz.gunluk(aylik.get(fz.PARA[kote], {}), g)
        seri, r = fazla_getiri(sp, rt, rk)
        rapor[ad] = r
        kayit.append((ad, sinif, seri, {"kaynak": [spot_k, "oecd:IR3TIB"], "yontem": "fazla_getiri",
                                        "gecikme_ay": fz.GECIKME_AY}))
    for ad, sinif, seri, meta in kayit:
        kimlik = f"VADELI:{ad}"
        depo.yaz(kimlik, "1d", seri, birlestir=False)
        en.kaydet(motor, [en.Enstruman("VADELI", ad, sinif, "fx_24x5", "USD", "turetilmis", meta)])
        en.sinir_guncelle(motor, kimlik, int(seri["acilis_ms"].min()), int(seri["acilis_ms"].max()))
    return rapor
