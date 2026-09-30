---
proje: TradeBot
created: 2026-09-30
type: turnuva-plani
durum: ön kayıt (koşudan önce commit edildi)
---
# Turnuva — Dalga 9: G10 döviz kesitseli (ön kayıt)

Dosya: `config/turnuva/dalga9_doviz.yaml`. Kod: `cekirdek/aileler.py::doviz_kesitsel`, taşıma farkı
`veri/vadeli.py::tasima_farki`.

## Neden

Scryne (2026-09-30): "Forex trading'e geçiyoruz, tüm yetki sende." Gerçek para kararı: **önce demo, kapıdan sonra
gerçek** (Scryne'ın seçimi). Forex'te bugüne kadar ölçülenler: dalga 1 döviz CFD'leri (5 aile, hepsi negatif), altın
M15 (6 aile, negatif), dalga 3 döviz + metal + endeks vadeli trendi (Sharpe ≤ 0,27), dalga 8 yalnız altın (Sharpe
0,43). Hepsi **zaman serisi** fikirleriydi (tek paritenin kendi geçmişi).

Ölçülmemiş olan, döviz literatüründe en çok belgelenmiş iki **kesitsel** prim:
- **Taşıma** (Lustig-Verdelhan 2007, Menkhoff-Sarno-Schmeling-Schrimpf 2012a): yüksek faizli para uzun, düşük faizli
  kısa. Getiri faiz farkından gelir; bedeli seyrek, sert çöküşlerdir (2008).
- **Momentum** (Menkhoff vd. 2012b): son 1–12 ayda USD'ye karşı en güçlü paralar uzun, en zayıflar kısa.
- **Dolar taşıması** (Lustig-Roussanov-Verdelhan 2014): yabancı faizlerin ortalaması USD'nin üstündeyse bütün
  yabancı paralar uzun, değilse kısa.

**Önsel (dürüst):** 2010–2025 G10 taşıması için kötü bir dönemdi (sıfır faiz yılları, taşıma farkları dar; 2022'den
sonra fark açıldı). Literatürdeki primlerin çoğu 48+ paralı, gelişmekte olan piyasalı sepetlerden gelir; burada yalnız
7 para var, kesit ince. Kurum swap payı taşımanın bir kısmını yer. Sıfır hipotezinin ayakta kalması şaşırtıcı olmaz.

## Kural

- Evren: `VADELI:EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF` (dalga 3 vekilleri: Dukascopy spot + OECD 3 aylık faiz
  farkı, iki ay gecikmeli; PIT). USD puanı 0 olan yedinci para.
- Para puanı t'de bilinenle; en yüksek `n` para uzun, en düşük `n` kısa, her biri 1/n (para uzayında dolar-nötr).
  Enstrüman ağırlığı = yön × para ağırlığı (USDJPY'de JPY kısa = USDJPY uzun). Yalnız haftanın ilk barında yenilenir.
- Boyut: %10 oynaklık hedefi (90 gün), **1x brüt tavan**, enstrüman 0,5, bant 0,25, frenler açık (ek 1). Karar
  kapanmış barla, dolum ertesi barın açılışında.
- Dönem 2010 → 2025-12-31. Walk-forward IS 3 yıl → OOS 1 yıl. Çıta 0 (seri nakit üstü getiri).

## Izgara (9 deneme, tek aile `doviz_kesitsel`)

| Strateji | Izgara |
| --- | --- |
| `doviz_tasima` | n ∈ {1, 2, 3} |
| `doviz_momentum` | n = 2; geriye ∈ {21, 63, 252} gün |
| `doviz_birlesik` (iki sıranın ortalaması) | n = 2; geriye ∈ {63, 252} gün |
| `doviz_dolar` | tek varyant |

## Maliyet (aleyhte, koşudan önce sabit)

`VADELI:fx`: komisyon 0, yarım spread 1 bps, kayma 1 bps (NCM canlı tik tam spread medyanı EURUSD 1,8, USDJPY 1,3 bps),
kurum swap payı yıllık %1 (brüt maruziyet üzerinden; faiz farkı serinin içinde). Stres: maliyet 2 kat, bir bar gecikme.
NCM demo hesabında majör swap'ları 0 görünüyor (spike 08): gerçek hesap swap'ı gerçek paradan önce ölçülür (Faz 12).
Rapor ayrıca başa baş kurum payını verir (bilgi).

## Karar ölçütü

Dalga 3 ile aynı: A için DSR ≥ 0,95 + walk-forward OOS + stres; B için DSR şartı yok.

**Demo hesaba ne girer (sonuçtan önce yazıldı):** A ya da B çıkan en iyi varyant, NCM forex demo hesabında (MT5 emir
yolu, Faz 8) paper kolu olarak çalışır; gerçek para kapısı değişmez (paper haftalarında PSR(0) ≥ 0,95 ve ≥ 26 hafta).
Hiçbiri geçmezse: sıfır hipotezi ayakta kalır, bu yazılır; ailenin DSR'ı en yüksek varyantı yine demo hesapta
**ileriye dönük gözlem kolu** olarak çalışır (sermayesi sanal, kapı sayacı aynı). Bu, geçmiş testin yerine geçmez:
kapı yalnız ileriye dönük haftalarla açılır.

## Ek 1 (2026-09-30, koşudan önce): boyut canlı tavanlarına çekildi

İlk ön kayıt (e8acbd9) dalga 3'ün boyutunu taşıyordu (%20 hedef, 3x). Demo düğümü risk motorunun varsayılan
tavanlarıyla çalışacak (kol brütü 1x, tek enstrüman özkaynağın %50'si; kilit kolu da böyle). Tavanı yükseltmek
Scryne'ın açık onayını ister (kural 7) ve backtest canlıdan gevşek olamaz. Hiçbir sonuç görülmeden değiştirildi:
%10 hedef, 1x tavan. Sharpe ve DSR ölçekten büyük ölçüde bağımsızdır; getiri ve düşüş ~%10 oynaklıkla okunmalı.

## Raporlanacak (kapı değil, bilgi)

- Kilit koluyla ve BTC/ETH trend kollarıyla haftalık korelasyon.
- 2022 (faiz şoku), 2008 yok (veri 2010'dan), 2015 CHF şoku (15 Ocak) ayrı.
- Başa baş kurum payı (yıllık %).
