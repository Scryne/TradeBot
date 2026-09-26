---
spike: 04
konu: Jev — haber/duyuru vetosu (A1), KAP sınıflandırma (A2), kurumsal işlem tespiti (B1); NVIDIA yükseltmesi
tarih: 2026-09-25
sonuc: A kısmı GEÇTİ (güçlü) · B kısmı GEÇTİ — nemotron-3-ultra birincil (yedek zinciri ölçümü sürüyor)
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

## 6. B kısmı: NVIDIA yükseltmesi (2026-09-26)

Kod: `yukseltme_nvidia.py` (ölçüm), `yukseltme_analiz.py` (belirsiz 60 seti). Ham sonuçlar `data/yukseltme_*.json`.
Aynı Choice tanımları, istem `tradebot.zeka.yukseltme.istem` ile birebir. Ücretsiz katman, `temperature 0`.

**İki set:**
- **90 etiketli örnek** (04-A'nın seti). Jev'in güveni < 0,5 olan yalnız 3 örnek var, yani yükseltmenin asıl işini
  az ölçer.
- **60 gerçek belirsiz vaka:** host'taki geri doldurmada Jev güveni < 0,5 kalan A1 kararlarının hepsi (2022–2026).
  Claude metni okuyarak etiketledi: 15 veto gerektirir, 45 gerektirmez. Asıl ölçüm budur.

| Model | 90 örnek | 60 belirsiz: veto kararı | Yanlış veto | Kaçırılan | JSON yok | Gecikme medyan / p90 |
| --- | --- | --- | --- | --- | --- | --- |
| `nvidia/nemotron-3-ultra-550b-a55b` | 89/90 | **60/60** | 0 | 0 | 0 | 12–19 sn / 37–64 sn |
| Eski kural (belirsizde ilk iki seçenekte veto varsa veto) | — | 51/60 | 8 | 1 | — | — |
| `moonshotai/kimi-k3`, `z-ai/glm-5.3`, `deepseek-ai/deepseek-v4.1-flash` | sürüyor | sürüyor | | | | tek çağrı 55–220 sn |

- 90 örnekte nemotron'un tek hatası veto dışı (KAP `rutin` → `olumlu_esasli`). 04-A'daki "kaçırılan 2", kabul
  kümesinde `rutin` de olan iki KAP örneği, gerçek kaçırma değil.
- Eski kuralın 8 yanlış vetosu: PHB, FLOKI, INJ, ALPACA, ADA (yalnız /TUSD veya /BTC çifti kaldırılmış), ALCX (yalnız
  margin), NOT ×2 (aday "is NOT guaranteed" kelimesinden). Kaçırılan: ADAUP (ADAUP/USDT işlemi durdu).
- **Jev'in zayıf yeri:** /TUSD çifti ile /USDT çiftini karıştırıyor (`other_pairs` tanımının `not_for` listesinde TUSD
  yok). Soru değişikliği yeni rol sürümü ve yeni ölçüm demek, şimdilik yükseltme yakalıyor.
- **Gecikme:** ücretsiz katmanda bekleme sırası baskın (üretilen token az, süre uzun). A1 için yeterli: delist duyuruları
  günler önceden gelir. Canlı istemcide zaman aşımı 180 sn.

**Karar:** yükseltme zinciri `[nemotron-3-ultra]` (`config/zeka.yaml`). Yedek model diğer üçünün sonucuyla eklenir.
Sınır: etiketleri tek kişi (Claude) verdi.
