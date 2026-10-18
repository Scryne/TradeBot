---
proje: TradeBot
created: 2026-10-18
type: turnuva-plani
durum: sonuçlandı — B (esit_agirlik), diğerleri KALDI (2026-10-18)
---
# Turnuva — Dalga 19b: dalga 19'un ızgarası, Alpaca verisiyle (ön kayıt)

Dosya: `config/turnuva/dalga19b_nasdaq_alpaca.yaml`. Veri: `src/tradebot/veri/alpaca_veri.py` (`tradebot veri alpaca`).

## Neden

Dalga 19 (Yahoo) hayatta kalma yanlılığıyla ölçüldü: verisi olan üye-gün oranı 2016'da %76, 2007–2013'te %60–70;
satın alınan ve kapanan üyeler (ATVI, CELG, XLNX, SPLK…) kaynakta yoktu, bu yüzden grup en fazla B'ydi. Alpaca'nın
tarihsel verisi (SIP, 2016'dan) bu şirketleri de taşır ve o gün işlem gören sembolle sorgulanabilir (`asof`; 2026-10-18
host'ta ölçüldü: ATVI 2023-10'a, CELG, XLNX, SPLK, EA geçmişleri var; `FB` 2020 sorgusu Meta'nın geçmişini döndürür,
bugünkü FB bir ETF'tir). Aynı ızgara, yanlılığı büyük ölçüde giderilmiş veriyle yeniden ölçülür.

## Kural

Dalga 19 ile **birebir aynı** ızgara (18 deneme), boyut, maliyet (`NASDAQ:hisse`, taraf başı 5,5 bps), ölçüt (çıta
T-bill %4,5) ve walk-forward (IS 3 yıl / OOS 1 yıl). Farklar yalnız veri:

- Fiyat: Alpaca günlük, `adjustment=all` (bölünme + temettü düzeltmeli toplam getiri), ayrı depo `veri/alpaca/`.
- Dönem: 2016-01 → 2025-12-31 (2026 kör). Momentum ve 200 günlük filtre ısınması nedeniyle ilk yıl büyük ölçüde nakit;
  walk-forward OOS pencereleri ~2019'dan.
- Üyelik ve dönem kapsamı dalga 19 ile aynı (n100tickers sabit commit, sembol eşleme). Kapsam yıl yıl raporlanır.
- Grup **A olabilir** (kapanan üyeler dahil). Kapsam bir yılda %95'in altındaysa sonuç bölümünde belirtilir.

Aileler dalga 19 ile ortaktır: her varyant yeni denemedir, DSR bütün denemelerle (kural 10).

## Paper'a ne girer (sonuçtan önce yazıldı)

- 19b'de A ya da B çıkan her ailenin en iyi varyantı Alpaca verisiyle çalışan yeni kol olarak paper'a girer
  (`d19b:<strateji>@nasdaq100@1d`, grup `depo: alpaca`).
- Dalga 19'un kolu (`d19:esit_agirlik@nasdaq100@1d`): `esit_agirlik` 19b'de de A/B ise yerini aynı varyantlı d19b
  koluna bırakır (durdurulur, düzleşir); 19b'de KALDI ise d19'un B'si hayatta kalma yanlılığının ürünüdür ve durdurulur.
- 19b'de hiçbir aile geçmezse: Scryne'ın yön kararı gereği bir günlük kol yine çalışır; walk-forward OOS Sharpe'ı en
  yüksek varyant "gözlem kolu" etiketiyle (d19b) paper'a girer, d19 kolu durdurulur.
- Gerçek para kapısı değişmez; sonuca bakıp ızgara değiştirilmez.

## Sonuç (2026-10-18, koşu `dalga19b`, ön kayıt 0385fd1)

**Dalga 19 ile aynı karar: `esit_agirlik` B, diğer üç aile KALDI.** Veri kapsamı: 2016'dan sonraki 217 üyelik
döneminin hepsinin Alpaca'da verisi var (eksik 0; Yahoo'da 271'in 74'ü yoktu). Verisi olan üye-gün oranı 2017–2025'te
%99,8–100 (2016 %76: ısınma, ilk 60 gün). Yani bu sonuç hayatta kalma yanlılığının ürünü değildir. Dönem 2016-01 →
2025-12; kör 2026-01 → 10-16.

| Strateji | En iyi varyant | Yıllık | Sharpe | Düşüş | En kötü hafta | OOS yıllık | DSR (deneme) | Kör 2026 | Karar |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| esit_agirlik | filtre 200 | +%8,6 | 0,71 | −%17 | −%6,9 | +%7,2 | 0,01 (681) | +%13,1 | **B** |
| hisse_momentum | 126 gün, ilk 10 | +%16,4 | 0,88 | −%25 | −%11,1 | +%10,8 | 0,67 (58) | +%33,2 | KALDI (en kötü hafta, 1 acil) |
| dusuk_oynaklik | 60 gün, ilk 20 | +%8,6 | 0,70 | −%27 | −%9,0 | +%7,2 | 0,97 (8) | +%7,9 | KALDI (1 acil durdurma) |
| kisa_donus | 10 gün, trend yok | +%9,9 | 0,59 | −%30 | −%9,5 | +%12,4 | 0,18 (88) | −%7,1 | KALDI (2 acil) |

Kıyas (bilgi): evren eşit ağırlıklı al-tut +%10,6/yıl, Sharpe 0,70, düşüş −%27 (kör +%18,1); QQQ +%19,8/yıl, Sharpe
0,97, düşüş −%37 (kör +%22,1).

- 2016–2025'te QQQ'yu (birkaç mega şirketin yükselişi) hiçbir eşit ağırlıklı kural geçmiyor; esit_agirlik al-tutun
  getirisinin ~%80'ini, düşüşün ~%60'ıyla veriyor. DSR ~0: A olamaz, gerçek para kapısı kapalı.
- Düşük oynaklık DSR 0,97 ile A'ya en yakın aileydi, ama 2020 Mart'ında acil durdurma (−%25 tepe) eşiğine değdi; tam
  dönem kapısı acil durdurma tetikleyen stratejiyi kabul etmiyor. Momentum en kötü haftada (−%11,1) kaldı.

**Paper (ön kayıt gereği):** `d19` kolu durduruldu (henüz pozisyonu yoktu), yerine `d19b:esit_agirlik@nasdaq100@1d`
(Alpaca verisi + Alpaca paper) ve A3 vetolu ikizi `d19b:esit_agirlik@nasdaq100@1d+jev` (iç simülasyon).
