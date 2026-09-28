---
proje: TradeBot
created: 2026-09-29
type: turnuva-plani
durum: sonuçlandı — 1 kol A (2026-09-29)
---
# Turnuva — Dalga 6: token kilit açılımı öncesi kısa (ön kayıt)

Dosya: `config/turnuva/dalga6_kilit.yaml`. Gerekçe: `docs/Arastirma-2-Genis.md` §4.1 (yapısal akış).

## Neden

Keyrock 16.000+ açılımı inceledi: ~%90'ı fiyatı düşürüyor; düşüş ~30 gün önce başlıyor, son hafta hızlanıyor, ~14 gün
sonra nötrleşiyor; ekip açılımları en sert. Bu bir fiyat deseni değil, yapısal bir akış: kilitli token alanlar (ekip,
yatırımcı) satmak ya da perp ile korunmak ister, alıcı tarafı bunu önceden bilir. Kural tamamen takvimden (kodla)
kurulur; Jev yön vermez (kural 8).

**Önsel (dürüst):** etki çok iyi biliniyor (Keyrock, The Tie, borsalar yayımlıyor); bilinen etkiler zamanla fiyatlanır.
Kör dönem (2025+) Keyrock'un yayımından (Aralık 2024) sonrasıdır: fikir için gerçek dışarıda kalan dönem.

## Veri

- Olaylar: DefiLlama'nın herkese açık `/unlocks` sayfası (`veri/kilit.py`): 304 token, 33 bin cliff olay.
- Fiyat ve funding: Binance USDT-M perp günlük mum + 8 saatlik funding (`veri/binance_vadeli.py`), delist edilen perp'ler
  dahil: 188 token eşleşti.
- Seçim (koşudan önce görülen sayım): `insiders` + `privateSale`, aynı gün toplamı azami arzın ≥ %1'i: 633 olay, 116
  token; 2021–2024 ~235, 2025–2026 ~361. Perp listelenmeden önceki olaylar kurulamaz.

## Kural

Açılım gününden `giris` gün önce 00:00 UTC açılışında: token perp kısa, BTC perp uzun, bacak başına özkaynağın %10'u.
Çıkış açılım gününden `cikis` gün sonra açılışta. Açık olayların brüt toplamı 3x'i aşarsa yeni olay kırpılır (kural 6).

Izgara (6 deneme): giriş −30 / −14 / −7 gün × çıkış 0 / +7 gün.

## Maliyet (aleyhte, koşudan önce sabit)

Binance USDT-M taker %0,05 her bacak her yönde; kayma token %0,1, BTC %0,01; funding gerçek (kısa bacak pozitif
funding'i alır, negatifte öder; uzun BTC öder). Stres: ücret ve kaymalar 2 kat.

## Karar ölçütü

Dalga 4 ile aynı: yılların ≥ %60'ı pozitif, en kötü hafta ≥ −%10, en kötü düşüş ≥ −%30, 2 kat maliyette pozitif, kör
dönem pozitif ve düşüşü ≥ −%30; A ayrıca DSR ≥ 0,95 (6 deneme). Çıta 0.

## Bilinen sınırlar

- DefiLlama geçmiş olayları sonradan düzeltmiş olabilir (takvimler önceden yayımlanır, yine de PIT değil).
- Boyut azami arza göre (dolaşımdaki arz o günkü değil, sonradan değişir).
- Kısa pozisyonun borsa riski (ADL, likidasyon) modellenmedi; %10 nominal ve piyasa nötr yapı bu riski küçültür.
- Gerçek parada perp kullanımı Türkiye'de lisanslı platformlarda yok; paper'da sorun yok (Arastirma-2 §7).

## Sonuç (2026-09-29, koşu `dalga6`, ön kayıt e088b94)

**Bir kol A: `kilit(giris=-7, cikis=0)` — açılımdan 7 gün önce token perp kısa + BTC perp uzun, açılım günü kapat.
Plasebo sınaması etkinin açılımdan geldiğini doğruluyor. İlk gerçek ikinci getiri kaynağı; BTC/ETH trendiyle korelasyonu
negatif.**

| Varyant | Karar | Sharpe | Yıllık | En kötü düşüş | DSR | Kör yıllık | 2x maliyet | Olay başına (t) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| **−7 / 0** | **A** | 0,93 | +%15,6 | −%20 | 0,97 | +%52 | +%11,9 | +%2,08 (2,5) |
| −7 / +7 | KALDI (DD −%31) | 1,08 | +%28,9 | −%31 | 0,99 | +%104 | +%24,8 | +%3,82 (3,4) |
| −14 / 0 | KALDI (DSR 0,93) | 0,78 | +%19,0 | −%26 | 0,93 | +%71 | +%15,2 | +%2,77 (2,6) |
| −14 / +7 | KALDI (DD) | 0,98 | +%32,5 | −%39 | 0,98 | +%132 | +%28,6 | +%4,78 (3,5) |
| −30 / 0 | KALDI (DD) | 0,82 | +%28,9 | −%49 | 0,95 | +%105 | +%25,3 | +%5,52 (3,4) |
| −30 / +7 | KALDI (DD) | 0,97 | +%39,5 | −%48 | 0,98 | +%161 | +%36,1 | +%7,98 (4,1) |

Olay: 840 nitelikli, −7/0'da 443'ü kuruldu (271'inde perp yok, 126'sında fiyat eksik: perp listelenmeden önce).

**Plasebo (tanı, betimsel):** aynı token'da, ±30 gün içinde ekip/yatırımcı açılımı olmayan, ±60–180 gün kaydırılmış
günlerde aynı pencere (kısa token − uzun BTC):

| Pencere | Dönem | Olay ort. | Plasebo ort. | Fark (t) |
| --- | --- | --- | --- | --- |
| −7 / 0 | 2021–24 | +%1,42 (n 125) | −%3,26 (n 159) | **+%4,68 (2,6)** |
| −7 / 0 | 2025–26 | +%2,92 (n 318) | +%0,01 (n 225) | **+%2,91 (2,1)** |
| −30 / +7 | 2021–24 | +%4,41 | −%0,93 | +%5,33 (1,2) |
| −30 / +7 | 2025–26 | +%7,68 | +%8,84 | −%1,16 (−0,4) |

Okuma:
- **Son hafta etkisi gerçek:** −7/0 penceresinde olay getirisi plasebodan her iki dönemde de anlamlı yüksek; Keyrock'un
  "son hafta hızlanıyor" bulgusu ve yayımından sonra da sürüyor.
- **Uzun pencerenin getirisi açılımdan değil:** 2025–26'da plasebo olay kadar kazanıyor (altcoin'lerin BTC karşısında
  genel düşüşü + beta > 1). Bu varyantların yüksek getirisi yanıltıcı; DD kapısında kalmaları doğru.
- Funding katkısı ihmal edilebilir; getiri fiyattan.

**Çekinceler (A için):**
- Performansın çoğu son iki yılda: örneklem içi (2021–24) yıllık +%2,9, Sharpe 0,33 (2021 −%11); kör dönem (2025–26)
  yıllık +%52, Sharpe 1,69. Sebep kısmen olay sayısı (125 → 318: perp'li token ve açılım arttı, para daha az nakitte).
- Kör dönemin en kötü haftası −%9,2 (kapı −%10'a yakın); azami brüt 2,2x, ortalama 0,5x.
- BTC/ETH trend koluyla haftalık korelasyon **−0,21**: portföy açısından çeşitlendirici.
- DefiLlama geçmiş olayları düzeltmiş olabilir; canlıda olaylar yayımlandıkları anki takvimle alınmalı (paper bunu sınar).

**Sonraki adım:** kol paper turnuvasına girer (Final Doküman: A → paper; gerçek para ancak paper kanıtıyla). Gerekenler:
günlük takvim çekimi (anlık görüntü dondurulur: PIT), Binance USDT-M perp canlı veri, sandbox yürütme, risk motoru
(kural 5), kısa pozisyon ve kaldıraç denetimleri.
