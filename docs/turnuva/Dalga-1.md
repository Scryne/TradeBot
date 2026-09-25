---
proje: TradeBot
created: 2026-09-25
type: turnuva-plani
durum: ön kayıt (koşudan önce commit edildi)
---
# Turnuva — Dalga 1 (ön kayıt)

Bu doküman ve `config/turnuva/dalga1.yaml` koşudan **önce** commit edilir. Koşu sırasında değişmez. Bir şey
değişecekse yeni dalga dosyası ve yeni plan kimlikleri açılır (değişmez kural 10).

## Kol nedir

**Kol = strateji × piyasa grubu × zaman dilimi.** Örnek: `tsmom@kripto_ilk10@4h`, yani kripto likidite ilk 10'unda
4 saatlik zaman serisi momentumu.

Tek enstrüman yerine grup seçilmesinin iki nedeni var:

1. **Seçim yanlılığı azalır.** 26 ETF'nin en iyisini seçmek 26 deneme demektir; hepsini birlikte işlemek tek
   denemedir.
2. **Çeşitlendirme kolun kendi içinde olur.** Aynı riskte (yıllık %20 oynaklık) daha yüksek Sharpe, daha sığ en
   kötü hafta. Sektör pratiği de budur (managed futures).

Kol içinde her enstrüman eşit risk taşır (sinyal / gerçekleşen oynaklık / evren büyüklüğü). Kol toplamı hedef
oynaklığa ölçeklenir ve brüt maruziyet 3x ile sınırlıdır. Kolun ağırlığı Faz 7'de sermaye dağıtıcıya kalır
(yarım Kelly, korelasyon).

## Gerçekçilik kuralları

- Karar kapanmış barla verilir, dolum sonraki barın açılışında olur (tek enstrüman motoruyla birebir; test).
- **Maliyet her zaman aleyhtedir:**
  - Piyasa başına model.
  - Kripto küçük coinlerde likiditeye bağlı ek kayma (günlük hacim < 100 M$ → +5 bps, < 20 M$ → +15 bps).
  - ETF açığa satışında yıllık %1.
  - CFD finansmanı.
  - İşlemi biten (delist) enstrümandan zorla çıkış 3 kat maliyetle.
- **Point-in-time evren:** Bir bar için yalnız o bar kapanmadan önce bitmiş günlerin hacmi kullanılır (test). Kripto
  evreninden kural olarak dışlananlar:
  - kaldıraçlı tokenlar,
  - stabil ve itibari paralar,
  - sarılı varlıklar,
  - 30 günlük oynaklığı %10'un altında olanlar (sabitlenmiş).
- **Veri sonu 2026-09-01.** Gece gelen veri sonuçları değiştirmez.
- **Frenler açık:** günlük −%3, haftalık −%8, acil −%25. Araştırmada acil durdurma bir olaydır ve tetikleyen kol
  kapıdan geçemez.
- **Yön kısıtları:** Kripto spot ve BIST yalnız long; açığa satış yok. CFD ve ETF iki yönlü.
- **BIST getirileri USD ile ölçülür.** Sinyal TRY fiyatından üretilir, getiri USD fiyatla ölçülür (TRY enflasyonu
  kazanç sayılmaz).

## Eleme hunisi ve geçme ölçütü

| Aşama | Ne | Nerede |
| --- | --- | --- |
| 0 | Test planı (bu doküman + plan kimlikleri deneme defterinde) | `arastirma turnuva` planları açar |
| 1 | Izgaradaki her varyant, maliyet + frenler + oynaklık hedefiyle; her biri deneme defterine | `turnuva.kol_kos` |
| 2 | DSR (ailenin **tüm** denemeleri), plato, walk-forward (IS 3 yıl → OOS 1 yıl, IS'te seç), yıllık, rejim | aynı |
| 3 | Yürütme stresi: maliyet 2 kat; dolum bir bar geç | aynı |

Nautilus parity motor düzeyinde kalıcı testtir (`tests/test_nautilus_parity.py`). Kollar Nautilus'ta paper'da
yaşar (Final Doküman §7).

**Ortak koşullar (A ve B için):**
- Tam dönem kapıları: en kötü hafta ≥ −%10, en kötü düşüş ≥ −%30, ≥ 20 işlem, acil durdurma yok.
- Walk-forward OOS: en kötü hafta ≥ −%10, düşüş ≥ −%30, yıllık > 0.
- Tam yılların ≥ %60'ı pozitif.
- Hiçbir rejimde (grup endeksinin son 26 haftası yukarı/aşağı) t < −2 değil.
- Stres testlerinin ikisinde de puan > 0.

**Sınıflar:**
- **A (paper, sermayeli):** ortak koşullar + DSR ≥ 0,95 + plato.
- **B (paper, sermayesiz gözlem):** ortak koşullar + DSR ≥ 0,80.
- **KALDI:** diğer her şey.

**Paper'a giriş:** A kolları Faz 7'de paper sermayesi alır (kademeli; dağıtıcı korelasyonu yönetir). B kolları
sermayesiz gözlemde sinyal üretir. En az 4 haftalık canlı kanıtla A'ya terfi edebilirler; terfi ölçütü Faz 7
planında yazılacak.

## Okuma notları

- **DSR sert bir eşik.** Aile başına yüzlerce deneme var, eşik de ona göre yükselir. "Hiçbir kol A değil" sonucu
  yanlış değil, bilgidir. Eşik sonuca bakılarak gevşetilmez.
- **BIST hisse grubu bugünkü listeden kuruldu.** Geçmiş endeks üyeliği yok, yani hayatta kalma yanlılığı var.
  BIST hisse kolları en fazla B olabilir; A için yanlılıksız veri gerekir.
- **Puan (ortalama haftalık log büyüme) aynı riskte karşılaştırılır.** Kaldıraç kararı dağıtıcınındır.

## Bu dalgaya girmeyenler (Faz 5 içinde sonra koşulacak)

| Aile | Neden sonra | Ne zaman |
| --- | --- | --- |
| Carry (kripto funding) | Getiri fiyattan değil fundingten gelir; ayrı getiri modeli gerekir | Dalga 1b: `config/turnuva/dalga1b.yaml` (ön kayıt f2252c0; en fazla B, baz riski modellenmiyor) |
| Carry (FX swap) | Ücretsiz swap/faiz verisi yok | Veri bulununca (dalga 2) |
| Gün içi kırılım (açılış aralığı) | Dukascopy dakikalık verisi (son 3 yıl) henüz iniyor | Dalga 1c: `config/turnuva/dalga1c.yaml` (USA500 CFD, 5m/15m, XNYS seansı; WF 1,5 yıl/0,5 yıl) |
| Olay tabanlı (KAP/SEC) | Metin toplayıcılar ve Jev servisi Faz 6'da kuruluyor | Faz 6'dan sonra |
| Çift ticareti (pairs) | Eşbütünleşme seçimi kendi başına bir denemedir; ayrı plan gerekir | Dalga 2 |
| Jev'li ↔ Jev'siz A/B | Veto verisi Faz 6'da oluşur | Faz 6–7 |

## Ekler (ön kayıttan sonra; yalnız sıkılaştırır)

- **2026-09-25, ek 1: Nihai DSR.** Kolun DSR'ı koşu anında o ana kadarki deneme sayısıyla hesaplanıyordu. Bu yüzden
  erken koşan kol daha düşük bir eşikle ölçülüyordu. Dalga bitince `tradebot arastirma sonlandir` her kolun DSR'ını
  ailenin **nihai** deneme sayısı ve Sharpe varyansıyla yeniden hesaplar. Karar bu değerle verilir, koşu anındaki
  değer `dsr_kosu`'da kalır.
  - Bu ek, ilk 3 kolun (kripto_btc_eth 1d) sonucu görüldükten sonra yazıldı.
  - Eşiği yalnız yükseltir, kararı gevşetemez.
- **2026-09-25, hata kaydı.** d0625fa'da kol oynaklık ölçeği hatalıydı: nakitten sonra girişte kaldıraç patlıyordu.
  470df3a'da düzeltildi. d0625fa ile koşulan 3 kolun denemeleri defterde sayılı kalır (DSR'ı sertleştirir).
  Sonuçları `data/turnuva/dalga1/_hatali_d0625fa/` altında arşivlendi.
- **2026-09-25, ek 2: Ölçüm düzeltmeleri.** İlk ABD ETF sonuçlarından sonra üç hata bulundu ve düzeltildi.
  1. **Enstrüman tavanı yoktu.** Kol ağırlıkları risk motorunun enstrüman tavanını (0,5) uygulamıyordu. Eşit risk
     ağırlığı, çok düşük oynaklıklı SHY'a özkaynağın katları kadar pozisyon veriyordu: brüt 2,5x, yılda 64 kat devir.
     Backtest canlı risk motorundan gevşek olamaz (kural 5). Artık aynı tavan backtest'te de uygulanıyor.
  2. **Temettü yoktu.** Yahoo fiyatları yalnız bölünmeye göre düzeltilmişti. Short, temettü günündeki düşüşten kâr
     ediyor, long temettüyü almıyordu. Artık getiri toplam getiri olarak ölçülüyor (`adj_close / close`).
  3. **`ay_donumu` parametre adları** `_gun` çevrim kuralına takıldı ve koşu durdu. Çekirdekteki parametre adları
     değişti; dalga dosyası değişmedi (1d'de çevrim birebir).

  Bu düzeltmeler ölçütü değiştirmez, ölçümü doğrular. Dalganın bütün kolları (kripto dahil) yeni kodla yeniden
  koşulur; önceki koşuların denemeleri defterde sayılı kalır. Önceki sonuçlar `data/turnuva/dalga1/_v7df0fdd/`
  altında arşivlendi.
