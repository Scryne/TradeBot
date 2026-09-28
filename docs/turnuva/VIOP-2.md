---
proje: TradeBot
created: 2026-09-28
type: turnuva-plani
durum: ön kayıt (koşudan önce commit edildi)
---
# Turnuva — VİOP 2: TL taşıma (ön kayıt)

Dosya: `config/turnuva/viop2.yaml`. Araştırma planının 1. dalgası (`Arastirma-Plani.md`). Kurallar dalga 1–2 ve VİOP 1
ile aynı; çıta 0 (seri faiz farkını içerir, Dalga-1 ek 4).

## Neden

Paper'daki tek fikir BTC/ETH trendi. TL taşıma farklı bir risk primidir: kaynağı faiz farkı, riski kur çöküşü. Kripto
trendiyle korelasyonunun düşük olması beklenir. Carry'nin momentum ve oynaklık filtresiyle korunması FX
literatüründe bilinen bir kalıp (çöküş riskini, "merdivenle çık, asansörle in" profilini keser).

## Seri

- `VIOP:USDTRY_SUREKLI`: NCM `TRYUSD_YAKINVADE` (günlük, 2015-07 → 2026-02). Spotla getiri korelasyonu negatifse ters
  kote sayılır ve 1/fiyat'a çevrilir.
- Vade geçişi sıçraması VİOP 1'deki kuralla ayıklanır: vade sonları her ayın son XIST iş günü; spot, Dukascopy USDTRY'nin
  15:00 UTC kapanışı (VİOP döviz vadelisi 18:10 TR = 15:10 UTC'de kapanır).
- Faiz farkı (baz erimesi) serinin içinde: kısa pozisyon primi kazanır, TL'nin değer kaybını öder.

## Strateji (`cekirdek/aileler.py` `tasima`)

Sinyal −1 (kısa USDTRY vadeli). Filtreler kapatır (0): son `ufuk` gün serisi yükseldiyse (TL primden hızlı değer
kaybediyor); son 20 günün oynaklığı son 250 günün oynaklık medyanının 1,5 katını aştıysa. Isınmada 0.

Izgara (8): ufuk 0 / 20 / 60 / 120 × oynaklık filtresi yok / var. `ufuk 0, pencere 0` saf taşımadır (referans).

## Maliyet (aleyhte, koşudan önce sabit)

`VIOP:doviz_vadeli`: komisyon 4 bps + BSMV, yarım spread 1 bps (ölçülen ~0,3), kayma 1 bps; aylık devir yıllık %1,5.
Stres 2 kat.

## Raporlanacak (kapı değil, bilgi)

En iyi varyantın paper kollarıyla (BTC/ETH trend backtest'i) haftalık korelasyonu ve 50/50 karışımın Sharpe'ı.

## Bilinen sınırlar

- 2015 öncesi yok: 2008 ve 2013–14 taşıma çöküşleri örneklemde yok (2018, 2021 var).
- Seri tek kurumun yakın vade serisi; 2026-02 sonrası donmuş (kontratlarla uzatılabilir, bu dalgada yok).
- Gerçek parada TL taşıma bir **kur pozisyonudur**: hesabın para birimine göre sonuç değişir (USD hesap için USDTRY
  kısa = TL uzun). Portföyde TL riski ayrıca ele alınır.
