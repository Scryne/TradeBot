---
proje: TradeBot
created: 2026-09-29
type: turnuva-plani
durum: ön kayıt (koşudan önce commit edildi)
---
# Turnuva — Dalga 7: yeni listelenen token perp kısası (ön kayıt)

Dosya: `config/turnuva/dalga7_listeleme.yaml`. Veri: `tradebot veri listeleme`. Motor: kilit motoru (`arastirma/kilit.py`,
karar `cekirdek/kilit.py`); olay üretimi `arastirma/listeleme.py`.

## Neden

Kilit kolu (dalga 6) ilk gerçek ikinci getiri kaynağı oldu: fiyat deseni değil, yapısal arz akışı. Aynı akışın en yoğun
anı listelemedir. 2024'ten beri yeni token'ların çoğu düşük dolaşım / yüksek FDV ile listeleniyor; airdrop alıcıları ve
erken yatırımcılar satıyor, piyasa yapıcı ve borsa ilgisi ilk günlerden sonra azalıyor. Binance Research'ün "low float,
high FDV" raporu (Mayıs 2024) ve piyasa takipçilerinin 2024–25 ölçümleri yeni listelemelerin çoğunun ilk aylarda BTC'nin
gerisinde kaldığını söylüyor. Kural tamamen kodla kurulur (listeleme anı kontrat kaydından); Jev yön vermez (kural 8).

**Önsel (dürüst):** etki biliniyor, bu yüzden fiyatlanmış olabilir. Kalabalık kısa pozisyon funding'i negatife iter
(kısa öder); ayrıca yeni token'larda sert kısa sıkıştırmaları olur. Kol ikisini de gerçek funding ve günlük fiyatla öder.

## Olay ve kural

- Olay: Binance USDT-M perp'inin `onboardDate`'i (listeleme anı, UTC gün başına indirilir) 2021-01-01 sonrası.
- Dışlananlar (koşudan önce sabit): BTC, ETH, sabit paralar, fiat ve endeks kontratları (`listeleme.HARIC`); ilk günlük
  mumu listeleme anından 3 günden fazla önce olan kontratlar (yeniden listeleme / ad değişikliği: yeni token değil).
- İşlem: listelemeden `giris_gun` gün sonra 00:00 UTC açılışında token perp kısa + BTC perp uzun, bacak başına özkaynağın
  %10'u; listelemenin `bitis_gun`. günü açılışında kapat.
- Tavan: paper risk motorunun varsayılanları (BTC bacağı ≤ %50, açık brüt ≤ 1x): en çok 5 açık olay; fazlası reddedilir.
- Izgara (6 deneme): giriş 1 / 7 gün × çıkış 14 / 30 / 60. gün.

## Maliyet (aleyhte, koşudan önce sabit)

Taker %0,05 her bacak her yönde; kayma token %0,2 (yeni listeleme: kilit kolunun iki katı), BTC %0,01; funding gerçek.
Stres: 2 kat.

## Karar ölçütü

Dalga 6 ile aynı: yılların ≥ %60'ı pozitif, en kötü hafta ≥ −%10, en kötü düşüş ≥ −%30, 2 kat maliyette pozitif, kör
dönem (2025-01 → 2026-09) pozitif ve düşüşü ≥ −%30; A ayrıca DSR ≥ 0,95 (6 deneme, ayrı aile `listeleme_kisa`). Ek
bilgi: kilit koluyla haftalık korelasyon ve 50/50 karışım.

## Bilinen sınırlar

- **Hayatta kalan yanlılığı kısanın ALEYHİNE:** `exchangeInfo` yalnız kayıtlı kontratları verir; tamamen silinen
  (çoğunlukla çöken) token'lar eksiktir.
- Günlük mum: giriş/çıkış 00:00 açılışında; listeleme günü (gün 0) yüksek oynaklıklı ilk saatler ölçülmez.
- Kısa pozisyonun borsa riski (ADL, likidasyon) modellenmedi; %10 nominal ve BTC bacağı riski küçültür.
- Kilit koluyla aynı token'lar çakışabilir (listelemeden sonraki ilk kilit açılımları): korelasyon raporlanır.
