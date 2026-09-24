---
proje: TradeBot
created: 2026-09-24
type: proje-fikri
status: taslak (denetimde)
kaynak: docs/Arastirma.md
---
# TradeBot — Proje Fikri

## Problem

Scryne kendi sermayesini otomatik ve kurallı bir sistemle büyütmek istiyor. Elle işlemde duygusal hatalar
(panik satış, FOMO alım, kayıp kovalamak) ve disiplinsiz boyutlandırma en büyük kayıp kaynağıdır. Piyasadaki
hazır botların çoğu ise doğrulanmamış strateji, gizli maliyet ya da aşırı kaldıraçla para kaybettirir
(Araştırma §0, §11). TradeBot, stratejilerini ölçerek seçen, maliyeti ilk günden hesaba katan ve batmayı
imkânsız kılacak risk sınırlarıyla çalışan kişisel bir trade botudur.

## Hedef

**Scryne'ın kararı (2026-09-24):** kısa vadeli maksimum kazanç.

**Operasyonel tanım (kaldıraç kararı Claude'a bırakıldı):** sermayenin **en hızlı bileşik büyümesi**, şu
kısıtla: hiçbir yapılandırma hesabı sıfırlayabilecek risk almaz. Gerekçe: Araştırma §5.11'de kaldıraç
arttıkça önce büyüme artıyor, sonra hızla sıfıra iniyor. "Maksimum kazanç" bu eğrinin tepesidir, en yüksek
kaldıraç değil.

Başarı ölçütleri (her hafta raporlanır):

| Ölçüt | Anlamı |
| --- | --- |
| Net bileşik getiri (haftalık, aylık, yıllıklandırılmış) | Maliyet, funding, kayma dahil |
| En kötü düşüş | Kill switch eşiğine uzaklık |
| Canlı ↔ backtest sapması | Aynı dönemi backtest yeniden üretiyor mu? |
| Strateji başına net katkı | Hangi strateji para kazandırıyor, hangisi maliyet üretiyor? |

## Hedef Kullanıcı

Yalnız Scryne, yalnız kendi hesabı ve kendi parası. Başkası adına işlem, sinyal satışı ve copy trading
kapsam dışıdır (Araştırma §3.1).

## Temel Özellikler (v1)

1. **Veri katmanı:** Binance public tarihsel veri (1 dk → 1 gün), funding, listeleme tarihleriyle
   point-in-time evren, kalite kontrolleri. Parquet, dosya hash'i = veri kimliği.
2. **Backtest motoru:** tek karar fonksiyonu (backtest = canlı), dolum sonraki barın açılışında, aleyhte
   kayma, gerçek ücret modeli, look-ahead bozma testi, walk-forward raporu, Deflated Sharpe ve deneme
   sayacı.
3. **Strateji turnuvası:** kısa vadeli hedefe uygun aday aileler 1h/4h/1d zaman dilimlerinde ve çok
   varlıkta, aynı altyapıda ölçülür. Adaylar: trend/kırılım, oynaklık hedefli trend, kesitsel momentum,
   kısa vadeli dönüş (maker emirle), funding carry. Hepsi paper'da paralel koşar. Sermaye yalnız
   **ölçülmüş maliyet sonrası üstünlüğü** olanlara gider.
4. **Boyutlandırma ve kaldıraç:** oynaklık hedefli boyut. Kaldıraç, stratejinin ölçülen Kelly oranının
   **yarısı**. Kodda sabit **3x tavan**, **≥ 5x hiçbir modda yok.** Paper'da kaldıraç simüle edilir.
   Gerçek parada kaldıraç, borsa kararı ve hukuki netlikten sonra açılır.
5. **Risk motoru:** günlük/haftalık kayıp freni, maksimum düşüş kill switch'i, varlık ve toplam maruziyet
   tavanı, likidasyon mesafesi bekçisi, bayat veri ve borsa sağlık kontrolü. Sinyal risk motorunu
   atlayamaz.
6. **Canlı yürütme:** paper (gerçek fiyat, simüle dolum) → gerçek emir. İdempotent emir, her turda
   mutabakat, çökme sonrası durumun yeniden kurulması. Borsa bağımsız (CCXT).
7. **Jev katmanı (Scryne'ın seçtiği üç rol):**
   - **Haber/duyuru risk vetosu:** delist, hack, çekim durdurma, düzenleyici yaptırım → o varlıkta alım
     durur, pozisyon küçülür, alarm gider. Yalnız riski azaltır, asla alım tetiklemez.
   - **Olay özellikleri → strateji:** haber yargıları sayısal özelliğe çevrilir. Backtest için
     dondurulur, değer kattığı ölçülürse stratejiye girer.
   - **Log/alarm triyajı:** borsa ve bot hataları "geçici" ya da "müdahale gerekli" olarak ayrılır.
8. **Bildirim ve pano:** Telegram alarmları (işlem, fren, veto, hata) ve web pano (PnL, pozisyon,
   strateji karnesi, sağlık).
9. **Kayıt ve vergi hazırlığı:** her işlem TL karşılığıyla kalıcı kayıt, FIFO maliyet raporu.

## Kapsam Dışı

- **≥ 5x kaldıraç**, martingale, ortalama düşürme (kayıpta pozisyon büyütme).
- Market making, HFT, borsalar arası arbitraj (perakende için zayıf, Araştırma §5.8).
- TensorTrade/RL'yi temel olarak kullanmak (Araştırma §8.5). İleride deney olabilir.
- Jev'e yön/fiyat tahmini yaptırmak ya da Jev çıktısıyla alım yapmak.
- Telegram'dan doğal dil komutları (bu turda seçilmedi, ileride eklenebilir).
- Başkasının parası, sinyal paylaşımı, copy trading.

## Açık Sorular (denetimde kapatılacak)

1. **Gerçek işlem borsası:** Binance.com spot mu, yerli (Binance TR / BtcTurk) mi? Ertelendi. Mimari
   CCXT ile ikisini de destekler. Paper aşamasının sonunda karar verilir.
2. **Başlangıç sermayesi** (mikro gerçek para fazı) ve tavanı.
3. **Çalışma yeri:** bu bilgisayar mı, 7/24 açık ikinci bir makine mi, VPS mi?
4. **Vergi:** beyan yükümlülüğü mali müşavirle netleştirilecek (Araştırma §3.2).
5. **Haber kaynağı:** Binance duyuruları + hangi toplayıcı/RSS? (Jev spike'ında ölçülür.)
6. **Çekirdek yaklaşımı:** ince kendi çekirdek (öneri) mi, Freqtrade mi? (Spike'ta kıyaslanır.)
7. **Kısa vadeli stratejilerin maliyeti:** maker emirle gerçek dolum oranı ve kayma paper'da ölçülecek.
   Kısa vadeli dönüş ailesinin kaderi buna bağlı.
