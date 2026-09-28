---
proje: TradeBot
created: 2026-09-28
type: turnuva-plani
durum: sonuçlandı — KALDI (2026-09-28)
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

**Değişiklik (2026-09-28, koşudan önce, sonuç görülmeden):** Spike 08 demo işleminde komisyon ölçüldü (F_USDTRY 1
kontrat, taraf başı 7,91 TL = 1,5 bps + BSMV); model 4 → 2 bps + BSMV oldu. Taraf başı maliyet 6,2 → 4,1 bps. 2 kat stres
(8,2 bps) ön kayıttaki maliyetin üstünde kalır: stres testini geçen bir varyant ön kayıt maliyetinde de geçer.

## Raporlanacak (kapı değil, bilgi)

En iyi varyantın paper kollarıyla (BTC/ETH trend backtest'i) haftalık korelasyonu ve 50/50 karışımın Sharpe'ı.

## Bilinen sınırlar

- 2015 öncesi yok: 2008 ve 2013–14 taşıma çöküşleri örneklemde yok (2018, 2021 var).
- Seri tek kurumun yakın vade serisi; 2026-02 sonrası donmuş (kontratlarla uzatılabilir, bu dalgada yok).
- Gerçek parada TL taşıma bir **kur pozisyonudur**: hesabın para birimine göre sonuç değişir (USD hesap için USDTRY
  kısa = TL uzun). Portföyde TL riski ayrıca ele alınır.

## Sonuç (2026-09-28, koşu `dalgaviop2`)

**Hiçbir varyant geçmedi; sıfır hipotezi ayakta. TL taşıma bu seride maliyet ve çöküşler sonrası prim vermiyor.**

Seri: `VIOP:USDTRY_SUREKLI`, 2015-07 → 2026-02, 2 519 gün, 128 vade geçişi ayıklandı, 9 bozuk tik atıldı; kaynak zaten
USDTRY yönünde kote (ters çevrilmedi). Ham seri +%1.552 (≈ spot), ayarlı +%139: aradaki fark faiz primidir. Primi
toplayan kısa pozisyon bile TL'nin değer kaybını karşılamadı. Spot saatliği (15:00 UTC) Dukascopy'den bu koşu için
indirildi (host'un indirmesi 503'lerle takıldı; dosyalar ana bilgisayardan çekilip ham depoya aynı anahtarla girdi).

| Varyant (ufuk, oynaklık penceresi) | Yıllık | Sharpe | En kötü düşüş | Maruziyet | Kapılar |
| --- | --- | --- | --- | --- | --- |
| 20, 20 (en iyi) | +%0,5 | 0,13 | −%21 | %16 | geçti |
| 60, 20 | +%0,0 | 0,03 | −%18 | %15 | geçti |
| 20, yok | −%1,8 | −0,20 | −%33 | %21 | — |
| 120, 20 | −%2,1 | −0,48 | −%23 | %11 | — |
| yok, 20 | −%2,5 | −0,41 | −%36 | %29 | — |
| 60, yok | −%2,5 | −0,30 | −%29 | %18 | — |
| 120, yok | −%4,1 | −0,54 | −%39 | %15 | — |
| yok, yok (saf taşıma) | −%8,2 | −0,56 | −%64 | %40 | — |

- En iyi varyant: DSR 0,21 (kapı 0,95), plato yok (komşuların ortalaması negatif), walk-forward dışı yıllık +%0,5
  (Sharpe 0,12, 7 pencerede 3 farklı seçim). Yılların %60'ı pozitif; 2022 −%8, 2023 −%6, 2024 +%12. 2 kat maliyet
  +%0,2, bir bar gecikme −%0,4.
- Filtreler işini yapıyor ama kurtarmıyor: saf taşımanın −%64 düşüşü −%21'e iniyor, fakat kalan maruziyet (%16) primi
  de kesiyor. Oynaklık filtresi olmayan her varyant negatif.
- Paper kollarıyla korelasyon raporu atlandı: kol KALDI, karışımın Sharpe'ı anlamlı değil.

Okuma: TL taşıması 2015–2026'da, TL faizinin çoğu yıl enflasyonun ve kur kaybının altında kaldığı bir dönemde ölçüldü;
prim var ama değer kaybı daha büyük. Sonuca bakıp filtre ya da eşik değiştirilmedi (kural 10). Fikir kapanan
fikirlere girer; yeni bir gerekçe olmadan (ör. pozitif reel faiz rejiminin kalıcılaşması) tekrar denenmez.
