---
proje: TradeBot
created: 2026-09-30
type: turnuva-plani
durum: sonuçlandı — fomc_dolar B, diğerleri KALDI (2026-09-30)
---
# Turnuva — Dalga 10: döviz akış ve olay primleri (ön kayıt)

Dosya: `config/turnuva/dalga10_akis.yaml`. Kod: `cekirdek/doviz_akis.py` (saf, nedensel; `tests/test_doviz_akis.py`).
FOMC takvimi: `config/fomc_planli.yaml`.

## Neden

Scryne (2026-09-30): "Piyasadaki en iyi botu yap, tüm yetki sende, en iyi sonuçları alana kadar devam et." Forex'te
ölçülen her fikir kaldı (dalga 1 CFD trendi, dalga 3 vadeli trend, dalga 8 altın, dalga 9 G10 kesitsel taşıma ve
momentum, altın M15 ve aynası). Hepsi ya fiyatın kendi geçmişine (trend, dönüş) ya da faiz farkına dayanıyordu.

Ölçülmemiş olan, döviz piyasasının **yapısından** doğan primlerdir: belirli anlarda belirli katılımcıların fiyata
bakmadan yaptığı zorunlu işlemler. Bunlar tahmin değil, takvimdir: ne zaman olacağı önceden bilinir, işlem sayısı azdır
(maliyet düşük), ekonomik gerekçesi yayımlanmış hakemli çalışmalarda vardır.

| Strateji | Hipotez ve gerekçe | Kaynak |
| --- | --- | --- |
| `fomc_dolar` | Planlı FOMC karar günlerinde USD, sepete karşı ortalamada değer kaybeder: para politikası belirsizliğinin çözülmesi için ödenen risk primi. | Mueller, Tahbaz-Salehi, Vedolin (2017), *Exchange Rates and Monetary Policy Uncertainty*, Journal of Finance 72(3) |
| `ay_sonu_hedge` | ABD hisseleri ay içinde yabancı hisselerden iyi gittiyse, ABD hissesi tutan yabancı yatırımcılar kur riskini dengelemek için ay sonu 16:00 Londra fixing'inde USD satar (tersi de). Fiyata bakmayan, önceden bilinen akış. | Melvin, Prins (2015), *Equity hedging and exchange rates at the London 4 p.m. fix*, Journal of Financial Markets 22 |
| `seans_para` | Paralar kendi ülkelerinin işlem saatlerinde değer kaybeder, yabancı saatlerde kazanır (yerel likidite talebi, sipariş akışı). | Ranaldo (2009), *Segmentation and time-of-day patterns in foreign exchange markets*, JBF 33; Breedon, Ranaldo (2013), *Intraday patterns in FX returns and order flow*, JMCB 45(5) |

**Önsel (dürüst, koşudan önce):** literatürdeki örneklemler çoğunlukla 2010 öncesidir ve bu primler yayımlandıktan sonra
zayıflamış olabilir (McLean-Pontiff yayın sonrası çürüme). Olay başına etki bps mertebesindedir; NCM'de bir gidiş-dönüş
~4 bps. FOMC ve ay sonu kolları yılda 8 ve 12 işlemle maliyeti taşıyabilir ama 1x tavanla yıllık getiri küçük kalır
(tahmin: iyi durumda yılda %0,5–2). Seans kolu her gün 1–2 gidiş-dönüş yapar: maliyet 1x'te yılda ~%10–20; etki günde
4–8 bps'i aşmazsa kaybeder, bu yüksek olasılıktır. Sıfır hipotezinin ayakta kalması şaşırtıcı olmaz.

## Kural

- Evren: `DUKASCOPY:EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, USDCHF, NZDUSD` saatlik BID, 2010-01 → 2025-12-31 (2026-01 →
  08 kör). Hepsi NCM forex hesabında işlem görüyor (2026-09-30 sembol listesi; USDTRY/EURTRY işleme kapalı, gelişmekte
  olan ülke paraları yok: EM taşıma sepeti bu yüzden bu dalgada yok).
- Ağırlık para uzayında kurulur (yabancı para başına ±1/m), enstrümana `para_yon` ile çevrilir (JPY uzun = USDJPY kısa).
- Karar bar kapanışında, dolum sonraki barın açılışında. Pencere [E, X): açılışı bu aralıktaki barlar tutulur.
- **fomc_dolar** (3 deneme): yedi paranın eşit sepeti uzun (USD kısa). Giriş karar gününden önceki gün 21:00 UTC (NY
  kapanışı). Çıkış: `on` karar günü 16:00 UTC (açıklamadan önce), `gun` karar günü 21:00 UTC, `iki` ertesi gün 21:00
  UTC. Yalnız planlı toplantılar (olağanüstüler önceden bilinmez; 2020-03-18 planlısı iptal edildi): 2010–2025'te 127 olay.
- **ay_sonu_hedge** (4 deneme): giriş ayın sondan `gun` ∈ {1, 2}. iş gününün 00:00 UTC'si, çıkış son iş gününün Londra
  16:00 fixing'i (yaz saatinde 15:00, kışın 16:00 UTC). Yön girişte bilinen ay içi hisse getirisinden (günlük kapanış
  ertesi gün 00:00'dan önce kullanılmaz): `sepet` ABD (S&P 500) − ortalama(DAX, FTSE, Nikkei) > 0 ise yedi para uzun,
  < 0 ise kısa; `kendi` yalnız EUR, GBP, JPY, her biri ABD − kendi endeksi. DAX günlüğü 2013'ten: öncesinde `sepet` iki
  endeksle, `kendi`de EUR yok. Tatiller yok sayılır (iş günü = hafta içi).
- **seans_para** (2 deneme): ABD saatlerinde (13–21 UTC) EUR, GBP, CHF, JPY, AUD, NZD uzun; `tam`: ayrıca Avrupa
  paraları 07–13, Asya-Pasifik paraları 00–07 UTC kısa. CAD'nin yerel saati ABD'ninkiyle aynı: dışarıda. Saatler UTC
  sabit (yaz saati kaydırması yok; önceden yazıldı, veriye bakılmadı).
- Boyut: %10 oynaklık hedefi (90 gün, ex-ante), **1x brüt tavan**, enstrüman 0,5, bant 0,25, frenler açık. Pratikte
  pencere içinde sepet ~1x (sepet oynaklığı %10'un altında), pencere dışında nakit.
- Walk-forward IS 3 yıl → OOS 1 yıl. Çıta 0 (kaldıraçlı spot kâr/zararı; sermaye sepete yatırılmaz).

## Maliyet (aleyhte, koşudan önce sabit)

`NCMFX:fx_sabit`: komisyon 0, yarım spread 1 bps, kayma 1 bps (taraf başı 2 bps, gidiş-dönüş 4 bps). Dukascopy veri
spread'i (yarım ~0,2–0,5 bps) NCM'den dar olduğu için kullanılmaz; NCM canlı tik tam spread medyanı 1,3–1,8 bps.
Finansman yıllık %2 (tutulan süreye orantılı; gecelik swap'ın aleyhte vekili). Stres: maliyet 2 kat, bir bar gecikme.

## Karar ölçütü

Dalga 9 ile aynı: A için DSR ≥ 0,95 (aile 9 denemeyle) + tam dönem kapıları + walk-forward OOS > 0 + yılların ≥ %60'ı
pozitif + rejim + stres; B için DSR şartı yok.

**Demo hesaba ne girer (sonuçtan önce yazıldı):** A ya da B çıkan her strateji kolunun en iyi varyantı NCM forex demo
hesabında (MT5 emir yolu) ayrı bir gözlem kolu olarak çalışır; gerçek para kapısı değişmez (kolun kendi paper
haftalarında PSR(0) ≥ 0,95 ve ≥ 26 hafta). Hiçbiri geçmezse: sıfır hipotezi ayakta kalır, yazılır, üç fikir kapanan
fikirlere eklenir; demo hesaba yeni kol girmez.

## Sonuç (2026-09-30, koşu `dalga10`, ön kayıt 7b3b75d + ek 1 9c7e0dc)

**`fomc_dolar` B; `ay_sonu_hedge` ve `seans_para` KALDI.** 9 deneme; aile DSR'ı nihai 9 denemeyle (seans kolunun çok
negatif Sharpe'ı Sharpe varyansını büyüttüğü için DSR eşiği yükseldi: B için DSR şartı yok).

| Strateji | En iyi varyant | Yıllık | Sharpe | En kötü düşüş | OOS yıllık | Karar |
| --- | --- | --- | --- | --- | --- | --- |
| fomc_dolar | pencere = gun | +%0,40 | 0,25 | −%6,2 | +%0,16 | **B** |
| ay_sonu_hedge | — | — | −0,31 | −%12 | −%0,6 | KALDI |
| seans_para | — | — | −2,33 | −%84 | −%11,4 | KALDI |

- **FOMC günü dolar:** önceki gün 21:00 → karar günü 21:00 UTC yabancı sepet uzun. Yıllar: 16 yılın 10'u pozitif
  (2014 −%3,5, 2025 −%2,3 en kötüler; 2023 +%2,9 en iyi). Stres: 2x maliyette +%0,09/yıl, bir bar gecikmede +%0,38.
  Rejimden bağımsız (yukarı/aşağı t 0,73 / 0,62). Walk-forward seçimleri çoğunlukla `gun` (12 pencerenin 8'i). `on`
  (açıklamadan önce çıkış) ~0, `iki` (ertesi gün) negatif: etki açıklama gününe sıkışık, Mueller vd. ile tutarlı.
  **Ölçek dürüstçe:** yılda 8 olay, olay başına net ~5 bps, 1x tavanla yıllık +%0,4. Beklenen değer pozitif ama tek
  başına kullanılabilir bir getiri değil.
- **Olay bazında (bilgi, aynı varyantın ayrıştırması):** 124 olay, net ortalama +5,3 bps (medyan +11,4), isabet %54,
  **t = 0,98: sıfırdan istatistiksel olarak ayırt edilemiyor.** Dönemler: 2010–15 −3,5 bps (isabet %44), 2016–20 +12,9
  (%59), 2021–25 +7,9 (%60); 2025'in 8 olayının 7'si negatif. B kararı ön kayıtlı ölçütün sonucudur (B için DSR şartı
  yok); kanıt zayıftır, demo kolu bunu ileriye dönük sınar.
- **Ay sonu hedge:** yön işareti ters çalıştı ya da etki yok; walk-forward negatif.
- **Seans saati:** önceden yazıldığı gibi günlük 1–2 gidiş-dönüş maliyeti (yılda %10–20) etkiyi siliyor.

**Demo hesaba giren (ön kayıttaki kural):** `fomc_dolar(pencere=gun)` NCM forex demo hesabında gözlem kolu olarak
çalışır (yılda 8 işlem). Gerçek para kapısı değişmez. Ay sonu hedge ve seans saati kapanan fikirlere eklenir.

## Ek 1 (2026-09-30, sonuç görülmeden): YAML düzeltmesi

İlk koşu (7b3b75d) `fomc_dolar`'ın ilk varyantında durdu: YAML 1.1'de çıplak `on` değeri `True` okunuyor
(`bilinmeyen pencere: True`). Hiçbir varyant hesaplanmadı, deftere deneme yazılmadı. Izgara değerleri tırnaklandı;
tasarım değişmedi.

## Raporlanacak (kapı değil, bilgi)

- Olay başına brüt ve net ortalama getiri (bps), isabet oranı.
- Yıllık kırılım; 2020 (pandemi), 2022 (faiz şoku) ayrı okunur.
- Seçilen varyantın 2026-01 → 08 kör dönem sonucu.
- Kilit koluyla ve döviz taşıma gözlem koluyla haftalık korelasyon.
