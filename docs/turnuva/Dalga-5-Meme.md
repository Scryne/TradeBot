---
proje: TradeBot
created: 2026-09-29
type: turnuva-plani
durum: sonuçlandı — KALDI (2026-09-29)
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

## Sonuç (2026-09-29, koşu `dalga5`, ön kayıt 50f8964)

**Altı kolun hepsi kaldı. Meme sepetinde trend, hayatta kalan yanlılığına rağmen walk-forward'da nakit getirisini
geçemiyor; getiri 2020–21 boğasından geliyor ve BTC trendine bağlı.**

| Kol (en iyi varyant) | Sharpe | En kötü düşüş | OOS yıllık | Kapılar | BTC trend korelasyonu |
| --- | --- | --- | --- | --- | --- |
| donchian_ls 1d (20/10) | 0,90 | −%22 | +%3,7 | geçti | 0,46 |
| donchian_ls 4h (55/20) | 0,81 | −%26 | +%4,9 | — | 0,48 |
| ma_yon 4h (10/100) | 0,76 | −%31 | +%5,6 | — | 0,52 |
| tsmom 1d (20) | 0,78 | −%27 | −%6,5 | — | 0,49 |
| ma_yon 1d (10/100) | 0,67 | −%28 | +%1,9 | — | 0,52 |
| tsmom 4h (20) | 0,65 | −%40 | −%5,6 | — | 0,44 |

- En yakın aday `donchian_ls@kripto_meme@1d`: bütün kapılar geçti (yılların %100'ü pozitif, plato var, 2x maliyet
  +%18, OOS düşüşü −%23) ama OOS yıllık +%3,7 çıtanın (T-bill %4,5) altında. Çıta sonuca bakıp değiştirilmedi (kural 10).
- Yıllar: 2020 +%37, 2021 +%61, sonra +%6, +%17, +%24, 2025 +%4, 2026 +%2: etki zayıflıyor.
- BTC/ETH trend koluyla haftalık korelasyon 0,44–0,52: meme sepeti ayrı bir getiri kaynağı değil, aynı kripto riskinin
  daha gürültülü sürümü.
