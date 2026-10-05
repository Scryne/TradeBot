"""Mikro ivme skalpı (XAUUSD, saniyeler; NCM demo GÖZLEM deneyi, canli/skalp.py). Saf: G/Ç yok, yalnız verilen anlık
fiyatlar ve pozisyon durumu.

Scryne (2026-10-05) bir TikTok videosu gösterdi: MT5 Strategy Tester'da XAUUSD M1, 0,01 lot, ~10 saniyede bir işlem,
çok dar stop; 5 $ → 731 $ (4.448 işlem, işlem başı ortalama +0,16 $). EA'nın kuralları açık değil; bu, aynı biçimin
açık bir karşılığıdır: düz iken son `bekleme` saniyedeki orta fiyat hareketinin yönünde 0,01 lot aç; kârı (kapanış
tarafının fiyatıyla, yani spread düşülmüş) `tp` doları geçince, zararı `sl` doları geçince ya da `azami` süre dolunca
kapat. Amaç: aynı biçimin gerçek spread ve gerçek dolumla ne ürettiğini canlı göstermek. Martingale ve lot büyütme yok.
"""
from __future__ import annotations


def karar(poz: int, giris: float, bid: float, ask: float, orta_once: float | None, tutma_ms: int, bos_ms: int,
          tp: float, sl: float, azami_ms: int, bekleme_ms: int) -> tuple[int, str]:
    """Hedef yön ∈ {−1, 0, 1} ve neden.

    poz/giris: açık pozisyonun yönü ve MT5 giriş fiyatı. orta_once: `bekleme` önceki orta fiyat (yoksa None).
    tutma_ms: pozisyonun yaşı. bos_ms: son kapanıştan beri geçen süre. tp/sl: ons başına dolar.
    """
    if poz != 0:
        kar = (bid - giris) if poz > 0 else (giris - ask)      # şimdi kapatılırsa ons başına (spread düşülmüş)
        if kar >= tp:
            return 0, "hedef"
        if kar <= -sl:
            return 0, "stop"
        if tutma_ms >= azami_ms:
            return 0, "sure"
        return poz, "tut"
    if bos_ms < bekleme_ms or orta_once is None:
        return 0, "bekle"
    orta = (bid + ask) / 2
    if orta > orta_once:
        return 1, "giris"
    if orta < orta_once:
        return -1, "giris"
    return 0, "hareket_yok"
