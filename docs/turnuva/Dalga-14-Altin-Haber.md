---
proje: TradeBot
created: 2026-10-05
type: turnuva-plani
durum: ön kayıt (koşudan önce commit edildi)
---
# Turnuva — Dalga 14: altın haber ivmesi / dönüşü (ön kayıt)

Dosya: `config/turnuva/dalga14_altin_haber.yaml`. Çekirdek `src/tradebot/cekirdek/haber.py` (`haber_ivme`). Kurallar
Altın M15 turnuvasıyla aynı (maliyet aleyhte, frenler, walk-forward IS 1,5 yıl → OOS 0,5 yıl, DSR), stres 3x.

## Neden

Scryne (2026-10-05) yönü değiştirdi: bütün kollar kapatıldı, hedef forex/XAUUSD botu, sık işlem, "haberlere göre işlem
açan bot mu yaparsın, ne yaparsan yap". Kanıt bir kez daha gösterildi (sık işlem iki projede de maliyet sonrası eksi);
Scryne "ikisi birlikte"yi seçti: sürekli işlem botu demoda hemen çalışır (Altın M15 `kanal_kirilim`, ölçülmüş en az
kötü aile), haber botu önce bu turnuvayla ölçülür.

Haber tarafı bu projede yalnız filtre olarak ölçüldü (Altın M15: ±60 dk filtrenin katkısı yok) ve döviz sepetinde FOMC
günü olarak (dalga 10, B ama zayıf). Altının yayın dakikası etrafındaki yönlü tepkisi hiç ölçülmedi. ScryneQuant'ta da
haber → işlem mantığı yok (2026-10-05 incelemesi).

## Kural

1 dakikalık barlar. Olay anı E = yayın dakikasının açılışı (New York saatiyle FOMC 14:00, diğerleri 08:30).

- Referans: E'den önceki son kapanış. Karar: yayından k dakika sonra (bar E + k − 1 kapanışı),
  s = yön × işaret(kapanış − referans).
- Pozisyon h dakika tutulur, dolum karar barından sonraki barın açılışında (kural 4). Stop yok: süre çıkışı.
- Atlanır: referans ya da karar barı eksikse, hareket 0 ise. Aynı dakikadaki yayınlar tek olay; pencereler örtüşürse
  önceki olay öncelikli.
- Boyut: %20 oynaklık hedefi, 3x tavan (Altın M15 ile aynı).

Olay takvimi (`config/haber_takvimi.yaml`, `tradebot veri haber-takvimi`): FOMC (Fed karar metinleri), NFP, CPI, PPI
(BLS arşivleri), haftalık işsizlik başvuruları (DOL kuralı: perşembe 08:30, perşembe tatilse çarşamba; önceden bilinir).
Takvimin hepsi yayından önce ilan edilir: geleceği görmez.

## Izgara (16 deneme, yeni aile `altin_haber`)

| Parametre | Değerler | Anlamı |
| --- | --- | --- |
| k | 1, 5 | yayından sonra kaç dakika beklenir |
| h | 15, 60 | kaç dakika tutulur |
| yon | +1, −1 | ivme (ilk hareketin yönü) / dönüş (tersi) |
| secim | buyuk, hepsi | FOMC + NFP + CPI (yılda ~32) / + PPI + işsizlik (yılda ~95) |

Beklenen işlem sayısı: `buyuk` haftada ~0,6, `hepsi` haftada ~1,8. Sürekli işlem değil; olay başına bir işlem.

## Ölçüt ve karar

A: DSR ≥ 0,95 + walk-forward OOS pozitif + 3x maliyet stresinde pozitif + yılların ≥ %60'ı pozitif + rejim t > −2.
B: kapılar DSR'sız. Geçen varyant NCM demo hesabında gözlem koluna girer (yayın anı spread'i ve kayması orada ölçülür;
canlı spread backtest varsayımından genişse kol durdurulur). Hiçbiri geçmezse KALDI yazılır, sonuca bakılıp ızgara ya da
kural değiştirilmez (kural 10); yeni deneme yeni ön kayıt ister.

## Bilinen sınırlar

- Dakikalık ASK yok: spread maliyet modelinin varsayılanından gelir. Yayın dakikasında gerçek spread daha geniş olabilir;
  3x stres bunun için. Demo kol canlı spread'i ölçecek.
- Üç yıllık veri: `buyuk` seçimde ~95 olay. Küçük örneklem; DSR ve walk-forward bunu cezalandırır.
- Sürpriz (beklentiden sapma) verisi yok: kural sürprizin işaretini ilk dakikanın fiyat hareketinden okur.

## Sonuç (2026-10-05, koşu `dalga14`, ön kayıt 9746092 + takvim 5de70e2)

**KALDI: 16 varyantın hepsi eksi; ne ivme ne dönüş.** En iyi varyant (k 5, h 60, büyük olaylar, ivme) Sharpe −0,14,
walk-forward OOS −%2,1/yıl (OOS Sharpe −1,51), DSR 0,05.

| Seçim | Varyant aralığı (Sharpe) | Olay (3 yıl) |
| --- | --- | --- |
| buyuk (FOMC/NFP/CPI) | −0,14 … −0,92 | ~92 |
| hepsi (+ PPI + işsizlik) | −0,59 … −1,54 | ~250 |

- Sorun maliyet değil: `maliyet_payi` 0,01–0,06 (maliyet brüt getirinin küçük bir kısmı). Brüt getiri de sıfır ya da
  eksi; altın yayından 1–5 dakika sonra yönlü bir iz bırakmıyor. Aynı (k, h) çiftinde ivme ve dönüş birlikte eksi.
- Geniş seçim (PPI + işsizlik) daha kötü: küçük yayınlar gürültü ekliyor.
- Yıllar: 2023 +%0,7, 2024 −%0,7, 2025 −%0,9, 2026 +%0,1 (en iyi varyant; maruziyet %0,24, getiriler küçük).
- Demo koluna girmez. Sonuca bakıp ızgara ya da kural değiştirilmedi (kural 10).
