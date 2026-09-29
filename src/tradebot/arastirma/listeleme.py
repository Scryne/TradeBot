"""Dalga 7 — yeni listelenen token perp kısası (BTC ile piyasa nötr). Olay günü Binance'in kontrat kaydındaki listeleme
anıdır (`onboardDate`, point-in-time: kontrat o gün açıldı). İşlem, maliyet, funding ve tavanlar kilit motoruyla aynıdır
(`arastirma/kilit.py` → `cekirdek/kilit.py`): listelemeden `giris_gun` gün sonra açılışta token perp kısa + BTC perp
uzun, `bitis_gun`. günün açılışında kapat.

Motor olayı "çıkış günü" olarak görür: olay günü T = L + bitis_gun, giriş T − (bitis_gun − giris_gun), çıkış T.

Yanlılıklar (ön kayıtta yazılı): `exchangeInfo` yalnız hâlâ kayıtlı kontratları verir; tamamen silinen (çoğunlukla
çöken) kontratlar eksiktir → kısa pozisyonun ALEYHİNE yanlılık. Yeniden listelenen/ad değiştiren kontratlar (ilk mum
listeleme anından > 3 gün önce) yeni token sayılmaz ve dışlanır.
"""
from __future__ import annotations

import json
from pathlib import Path

import polars as pl

from tradebot.veri import binance_vadeli as bv

GUN_MS = 86_400_000
# Yeni token olmayan kontratlar: sabit paralar, fiat ve endeks kontratları
HARIC = {"BTC", "ETH", "USDC", "BUSD", "TUSD", "FDUSD", "USDP", "DAI", "USDE", "EUR", "GBP", "BTCDOM", "DEFI",
         "BLUEBIRD", "FOOTBALL", "ALLUSDT", "ALL"}
YENIDEN_LISTELEME_MS = 3 * GUN_MS


def haric_mi(taban: str) -> bool:
    return taban in HARIC or taban.endswith("DOM") or taban.startswith("USD")


def hazirla(veri_dizini: Path, ham, http_al, bas_ms: int, kayitci=None) -> dict:
    """Listeleme anı `bas_ms`'den sonra olan her USDT-M perp'in (ve BTC'nin) günlük mumu ve funding'i → data/listeleme/."""
    d = Path(veri_dizini) / "listeleme"
    (d / "perp").mkdir(parents=True, exist_ok=True)
    perp = bv.usdt_perpler(http_al, ham)
    secili = sorted(s for s, v in perp.items() if v.get("liste_ms") and int(v["liste_ms"]) >= bas_ms and not haric_mi(s))
    hatali = []
    for i, s in enumerate(secili + ["BTC"]):
        k = perp[s]["sembol"]
        if (d / "perp" / f"{s}_funding.parquet").exists():   # kaldığı yerden devam
            continue
        try:
            bv.gunluk(http_al, ham, k).write_parquet(d / "perp" / f"{s}_1d.parquet")
            bv.funding(http_al, ham, k).write_parquet(d / "perp" / f"{s}_funding.parquet")
        except Exception as e:  # noqa: BLE001 — işlem görmemiş / kaldırılmış kontrat (400): atla
            hatali.append({"sembol": s, "hata": f"{type(e).__name__}: {e}"[:120]})
        if kayitci is not None and i % 25 == 0:
            kayitci.info("ilerleme", bitti=i + 1, toplam=len(secili) + 1)
    (d / "perp_listesi.json").write_text(json.dumps({s: perp[s] for s in secili + ["BTC"]}, ensure_ascii=False),
                                          encoding="utf-8")
    return {"kontrat": len(secili), "hatali": hatali}


def olaylar(perpler: dict[str, dict], ilk_mum: dict[str, int], giris_gun: int, bitis_gun: int,
            bas_ms: int) -> pl.DataFrame:
    """Olay tablosu (kilit motorunun biçimi: sembol, gun_ms = çıkış günü, oran = 1).

    `ilk_mum`: sembolün ilk günlük mumunun açılışı. Mumu olmayan sembol de olay olarak kalır (motor "perp yok" sayar)."""
    if not 0 <= giris_gun < bitis_gun:
        raise ValueError("0 ≤ giris_gun < bitis_gun olmalı")
    satir = []
    for s, v in sorted(perpler.items()):
        if haric_mi(s) or not v.get("liste_ms"):
            continue
        liste = int(v["liste_ms"])
        L = liste // GUN_MS * GUN_MS
        if L < bas_ms:
            continue
        if s in ilk_mum and ilk_mum[s] < L - YENIDEN_LISTELEME_MS:
            continue
        satir.append((s, L + bitis_gun * GUN_MS, 1.0))
    return pl.DataFrame(satir, schema={"sembol": pl.Utf8, "gun_ms": pl.Int64, "oran": pl.Float64}, orient="row")
