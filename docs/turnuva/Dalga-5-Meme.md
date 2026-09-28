---
proje: TradeBot
created: 2026-09-29
type: turnuva-plani
durum: ön kayıt (koşudan önce commit edildi)
---
# Turnuva — Dalga 5: meme coin sepeti trendi (ön kayıt)

Dosya: `config/turnuva/dalga5_meme.yaml`. Gerekçe: `docs/Arastirma-2-Genis.md` §6 (hızlı kontrol) — Scryne'ın "meme
coin'lere de bakalım" isteği.

## Neden

Çalışan tek fikrimiz kripto trendi. Meme coin'ler en oynak kripto varlıklar: trend takibi uzun yükselişleri yakalayıp
çöküşlerde nakde geçerse, oynaklık hedefiyle küçük boyutta bile anlamlı getiri olabilir. Sniper/pump.fun oyunu değil:
yalnız Binance spot'ta işlem gören, likit meme coin'ler.

**Önsel (dürüst):** Dalga 1–2'de kripto sepeti genişledikçe trend kötüleşti (büyük 5 < BTC+ETH). Meme'ler daha da
gürültülü. Liste bugün seçildi: hayatta kalan yanlılığı var (delist olan meme'ler yok), sonuç iyimser taraflı.

## Sepet

DOGE, SHIB, PEPE, FLOKI, BONK, WIF, MEME, BOME, 1000SATS, TURBO, NEIRO, PEOPLE, TRUMP, PNUT (Binance spot, USDT). Her
coin listelendiği günden 60 gün sonra sepete girer (point-in-time). Yalnız uzun (spot).

## Aileler, ızgara, boyut

Dalga 2 ile aynı: `tsmom`, `ma_yon`, `donchian_ls`; 4h ve 1d; 32 deneme. Oynaklık hedefi %20 (90 günlük), kaldıraç
tavanı 3x (spot'ta pratikte ≤ 1), bant 0,25, frenler açık. Maliyet Binance spot modeli (aleyhte), stres 2 kat.

## Karar ölçütü

Dalga 1–3 ile aynı; çıta ABD T-bill (%4,5, USDT sepeti nakitte bu kadar kazanabilirdi).

## Raporlanacak

Paper kollarıyla (BTC/ETH trend) haftalık korelasyon.
