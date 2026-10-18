---
proje: TradeBot
created: 2026-10-18
type: turnuva-plani
durum: ön kayıt (koşudan önce commit edildi)
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
