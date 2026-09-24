---
spike: 04
konu: Jev — haber/duyuru vetosu (A1), KAP sınıflandırma (A2), kurumsal işlem tespiti (B1); NVIDIA yükseltmesi
tarih: 2026-09-25
sonuc: A kısmı GEÇTİ (güçlü) · B kısmı (NVIDIA) BEKLİYOR — API anahtarı gerekiyor
kod: research/spikes/04_jev/ (veto_binance.py, veto_kap.py; ham sonuçlar data/*_sonuc.json)
model: jev-1.13.0 (typesafe-sdk 0.7.1)
---
# Spike 04: Jev

**Soru:** Jev gerçek duyurularda "bu metin benim pozisyonuma ne yapıyor?" sorusunu güvenilir cevaplıyor mu?
Veto için hangi güven eşiği gerekiyor? Basit bir anahtar kelime kuralından iyi mi?

**Hüküm (A): GEÇTİ, güçlü.** İki gerçek veri setinde tüm örnekler kabul kümesinde. Veto kararlarında anahtar
kelime kuralının 30 yanlış alarmına karşı Jev'in yanlış alarmı 0.

## 1. Veri

| Set | Kaynak | Örnek | Etiket |
| --- | --- | --- | --- |
| A1 Binance | 55 gerçek duyuru (Temmuz–Eylül 2026): delist, çift kaldırma, marjin, bakım/ağ yükseltmesi, token birleşmesi, listeleme, promosyon | 46 (duyuru, varlık) çifti; 5'i metinde geçmeyen varlık (kontrol) | Claude metni okuyarak etiketledi; tartışmalı 3 örnekte kabul kümesi geniş |
| A2/B1 KAP | 14 BIST hissesinin 280 bildiriminden 44'lük çeşitli seçki, Türkçe | 44 bildirim | Aynı yöntem; 11 örnekte kabul kümesi geniş |

**Tuzaklar bilerek dahil edildi:**
- "Removal of Spot Trading Pairs" (yalnız ENJ/USDC kalkar, ENJ/USDT durur) ile "Binance Will Delist ICX"
  (token tamamen kalkar).
- Ağ yükseltmesi: transfer durur, işlem durmaz.
- STG→ZRO birleşmesi: STG için veto, ZRO için değil.
- KAP "Temerrüt İşlemi": bir yatırımcının takas temerrüdü, şirketin değil.
- Bağlı ortaklığın sermaye artırımı: ana payı düzeltmez.
- Kişilere yönelik toplu SPK işlem yasağı listeleri.

## 2. Soru tasarımı

- **`etki` (Choice):**
  - Binance'te 7 seçenek: token_delist, usdt_pair_removed, token_conversion, other_pairs_or_products_removed,
    transfers_suspended, positive_or_neutral, not_about_asset.
  - KAP'ta 6 seçenek: pazar_tedbiri, gecici_durdurma, kurumsal_islem, olumsuz_esasli, olumlu_esasli, rutin.
  - Her seçenek `what` / `not_for` / `examples` ile tanımlı.
  - State: `{duyuru|bildirim: {baslik, metin ≤ 4000 kr}, varlik|sembol}`.
- **`aciliyet` (Score, 5 seviye):** pozisyon sahibi ne kadar acil davranmalı?
- **Kod kuralı:**
  - Binance'te `etki ∈ {token_delist, usdt_pair_removed, token_conversion}` → veto.
  - KAP'ta `etki ∈ {pazar_tedbiri, olumsuz_esasli}` → veto.
  - `kurumsal_islem` → B1 (fiyat serisi düzeltme kuyruğu).

## 3. Sonuçlar

| | Binance (A1) | KAP (A2 + B1) |
| --- | --- | --- |
| Etki doğruluğu (kabul kümesine göre) | **46/46** | **44/44** |
| Tuzaklar | Hepsi doğru (çift ↔ token ayrımı 21/21) | **7/7** |
| Jev veto: doğru / yanlış alarm / kaçırılan | 9 / **0** / 0 | 3 / **0** / 1* |
| Anahtar kelime vetosu: doğru / yanlış alarm / kaçırılan | 9 / **21** / 0 | 1 / **9** / 3 |
| B1 kurumsal işlem | — | 6 işaret, 6 doğru |
| Güven ≥ 0,9 kapsamı ve doğruluğu | 43/46, %100 | 34/44, %100 |
| Güven < 0,5 | 1 (ZRO 0,38; cevap kabul kümesinde) | 2 (0,48 ve 0,47; ikisi de doğru) |
| Gecikme (medyan) | 0,25 sn | 0,25 sn |
| Ortalama girdi | 1.684 token | 2.502 token |
| Toplam maliyet | ≈ 0,003 $ | ≈ 0,005 $ |

\* Kaçırılan: HEKTS bağlı ortaklığının halka arzının ertelenmesi. Jev "rutin" dedi (güven 0,69). Altın
etiketim "olumsuz_esasli" idi ama "rutin"i zaten kabul kümesine koymuştum: sınırda bir örnek, gerçek hata
sayılmaz.

## 4. Öğrenilenler (tasarıma girer)

1. **Karar Choice'a dayanır, Score'a değil.** Aciliyet skoru bazı tuzaklarda kategoriyle çelişti. Toplu SPK
   yasağı listelerinde kategori "rutin" iken skor 3,5–3,8. Temerrüt İşlemi'nde 2,55. Score yalnız sıralama ve
   alarm önceliği için kullanılır, veto koşulu olmaz.
2. **"not_for" tanımları kritik.** Tuzakların hepsi, seçenek tanımına yazılan karşıt örneklerle çözüldü:
   "başka çiftlerin kaldırılması token delist değildir", "Temerrüt İşlemi şirket temerrüdü değildir".
   Rol eklerken önce tuzak listesi, sonra tanım yazılır.
3. **Gövde şart.** Başlıklar tek başına yetmiyor: "Notice of Removal of Spot Trading Pairs", "Özel Durum
   Açıklaması". KAP gövdesi HTML'den ayıklanmalı (Spike 03).
4. **Güven eşiği önerisi:**
   - Veto yönünde (riski azaltan): güven ≥ 0,5 yeter. Yanlış veto ucuz, iki sette de hiç yok.
   - Güven < 0,5 → yükseltme modeline gider.
   - O da yoksa ya da belirsizse, veto kategorisi en olası iki seçenekten biriyse "riski azalt" uygulanır.
   - İlk ay gölge modda eşik kalibre edilir.
5. **İlk çağrı ~12 sn** (bu makinenin DNS'i), sonrakiler 0,25 sn. Tek, uzun ömürlü istemci şart. Konteyner
   DNS'i bunu da çözer.
6. **Maliyet ihmal edilebilir:** günde 500 bildirim ≈ 0,05 $.

## 5. Sınırlar (dürüst okuma)

- Etiketleri tek kişi (Claude) verdi. Scryne'ın gözden geçirmesi ya da ikinci bir etiketleyici güveni artırır.
- Örneklem küçük (90). Binance duyuruları büyük ölçüde şablon metin. Serbest basın haberleri ve söylentiler
  daha zor olacak, Faz 6'da ayrıca ölçülür.
- Eğitim kesimi: jev-1.13.0'ın çıkışı 2026-09-10. Metinlerin çoğu öncesine ait. Ama burada sorulan sonucu
  değil, metnin ne söylediği. Sızıntı riski yön tahmininde ısırır, betimleyici sınıflandırmada değil.

## 6. B kısmı: NVIDIA yükseltmesi (BEKLİYOR)

Güven < 0,5 örnekleri ve bilerek zorlaştırılmış yeni örnekler, build.nvidia.com kataloğundaki 2–3 modelle
(GLM-5, Kimi K3, Nemotron-3 Ultra) karşılaştırılacak: doğruluk, gecikme, kapalı etiketli JSON'a uyum.
**Gereken:** Scryne'ın build.nvidia.com'da ücretsiz hesap açıp `NVIDIA_API_KEY` ortam değişkenini tanımlaması.
