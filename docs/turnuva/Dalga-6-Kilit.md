---
proje: TradeBot
created: 2026-09-29
type: turnuva-plani
durum: ön kayıt (koşudan önce commit edildi)
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
