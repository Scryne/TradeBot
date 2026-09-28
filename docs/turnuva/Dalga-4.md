---
proje: TradeBot
created: 2026-09-29
type: turnuva-plani
durum: sonuçlandı — KALDI (2026-09-29)
---
# Turnuva — Dalga 4: opsiyon oynaklık primi (ön kayıt)

Dosya: `config/turnuva/dalga4.yaml`. Gerekçe: `docs/Arastirma-2-Genis.md` (fiyat deseni yerine farklı getiri kaynağı).

## Neden

Paper'daki beş kol tek fikir (BTC/ETH trendi). Opsiyon satışı farklı bir risk primidir: piyasa oynaklığa karşı
sigortaya bedel öder. Trend uzun oynaklık gibi davranır (çöküşte kazanır), opsiyon satışı kısa oynaklıktır (çöküşte
kaybeder): birbirinin kötü dönemini kısmen dengeleyen iki kaynak.

**Önceden görülen (dürüst kayıt):** ön ölçümde BTC DVOL − sonraki 30 gün gerçekleşen oynaklık 2021-04 → 2023 ortalama
+11,7 puan, günlerin %74'ü pozitif (`Arastirma-2-Genis.md` §5.4). Haftalık yüzeyde yıllık medyan oynaklık seviyeleri
görüldü (veri kontrolü). Hiçbir yapının getirisi koşudan önce hesaplanmadı.

## Veri (`veri/deribit.py`)

- Deribit herkese açık tarihsel işlem kayıtları (anahtarsız): her Cuma 08:05–09:05 UTC, bir sonraki Cuma vadesinin
  işlemleri; Black-Scholes deltasıyla kova medyanı: ATM, %25 ve %10 delta put/call. Ham sayfalar ham depoda.
- BTC 329 hafta, ETH 325 hafta (2020-06 → 2026-09). Kovası eksik haftada yapı kurulmaz (0 getiri, nakitte).
- Uzlaşma: Deribit'in 08:00 UTC teslim fiyatı.

## Yapılar (6 kol, her biri tek varyant)

| Yapı | Bacaklar |
| --- | --- |
| iron_condor | %25 delta put ve call satılır, %10 delta put ve call alınır |
| put_spread | %25 delta put satılır, %10 delta put alınır |
| call_spread | %25 delta call satılır, %10 delta call alınır |

× BTC, ETH. Giriş Cuma 08:05, vadeye kadar tutulur (gün içi yönetim yok).

## Maliyet ve boyut (aleyhte, koşudan önce sabit)

- Satılan bacak `iv − yarım spread`, alınan `iv + yarım spread`: %25 delta 1,5, %10 delta 2,0 oynaklık puanı.
- Deribit işlem ücreti bacak başına min(%0,03 × dayanak, %12,5 × prim); teslim ücreti min(%0,015 × dayanak, %12,5 ×
  içsel değer). Stres: hepsi 2 kat.
- Boyut: haftalık azami kayıp (en geniş kanat − net prim + ücretler) özkaynağın %2'si; açığa satılan nominal 3x'i
  aşamaz (kural 6). En kötü hafta tasarımı gereği ~−%2.
- Faiz 0; USD'li doğrusal sözleşme varsayımı (Deribit USDC opsiyonları). BTC'li ters sözleşme farkı ihmal.

## Karar ölçütü

Tam dönem: yılların ≥ %60'ı pozitif, en kötü hafta ≥ −%10, en kötü düşüş ≥ −%30, 2 kat maliyette pozitif. Kör dönem
(2025-01 → 2026-09): pozitif ve düşüşü ≥ −%30. A: ayrıca DSR ≥ 0,95 (6 deneme). B: DSR şartı yok (sermayesiz paper).

## Raporlanacak (kapı değil)

Paper'ın trend kolu (`d2:donchian_ls@kripto_btc_eth@4h` backtest'i) ile haftalık korelasyon; yıllık kırılım; ortalama
prim ve nominal.

## Bilinen sınırlar

- Oynaklık işlemlerin medyanı (orta fiyata yakın); gerçek spread kovaya göre değişir (varsayım aleyhte, stres 2 kat).
- Hafta içi yönetim (erken kapatma, delta hedge) yok: en basit, en şeffaf sürüm.
- Kullanım fiyatı Deribit'in fiyat ızgarasına yuvarlanmaz (etkisi küçük, iki yönlü).

## Sonuç (2026-09-29, koşu `dalga4`, ön kayıt ae6130e)

**Altı kolun hepsi kaldı ve hepsi negatif. Haftalık, tanımlı riskli opsiyon satışı 2020–2026'da maliyet sonrası prim
vermiyor; sıfır hipotezi ayakta.**

| Kol | Sharpe | Yıllık | En kötü düşüş | Kör yıllık (2025+) | 2x maliyet | Trend korelasyonu |
| --- | --- | --- | --- | --- | --- | --- |
| put_spread BTC | −0,42 | −%2,0 | −%17 | −%5,2 | −%5,5 | +0,09 |
| put_spread ETH | −0,54 | −%2,8 | −%20 | −%4,3 | −%5,5 | +0,09 |
| call_spread BTC | −1,22 | −%6,3 | −%34 | −%3,6 | −%9,4 | −0,18 |
| call_spread ETH | −1,25 | −%6,4 | −%37 | +%0,9 | −%8,8 | −0,13 |
| iron_condor BTC | −1,34 | −%8,5 | −%44 | −%9,5 | −%14,1 | −0,09 |
| iron_condor ETH | −1,25 | −%8,0 | −%43 | −%5,8 | −%12,3 | −0,03 |

DSR hepsinde ~0. En kötü hafta tasarım gereği −%2 (tanımlı risk çalıştı).

**Tanı** (betimsel, strateji değil): bacak türü başına orta fiyattan ortalama prim ile vadede ödenen içsel değerin
oranı (1'in altı = opsiyon pahalı satılmış):

| Bacak | BTC ödeme/prim | ETH ödeme/prim | İçsel değerli bitme |
| --- | --- | --- | --- |
| %25 delta put | 0,78 (±0,26) | 0,87 (±0,28) | %21 |
| %10 delta put | 0,72 (±0,41) | 0,85 (±0,47) | %6–8 |
| ATM call | 1,13 (±0,20) | 1,17 (±0,22) | %55–56 |
| %25 delta call | 1,27 (±0,39) | 1,41 (±0,43) | %21–22 |
| %10 delta call | 1,59 (±0,71) | 1,17 (±0,53) | %10–11 |

Okuma:
- **Call'lar ucuzdu:** 2020–2026 yükselişi (BTC ~10 bin → ~85 bin $) call alıcısına kazandırdı; call satan her yapı
  (call spread, condor) kaybetti.
- **Put'lar biraz pahalıydı ama anlamlı değil** (güven aralığı 1'i kapsıyor). Koruma kanadı (%10 delta put) da pahalı:
  put spread elde ettiği fazlalığı kanada geri veriyor; aleyhte spread (primin %6–14'ü) ve ücretler kalanını siliyor.
- Ön ölçümdeki DVOL − gerçekleşen farkı (30 günlük varyans primi) haftalık, OTM, tanımlı riskli satışa dönüşmüyor:
  yönlü sürüklenme ve kanat maliyeti primi yiyor.

Sonuca bakıp yapı, delta ya da vade değiştirilmedi (kural 10). Akla gelen varyantlar (çıplak put satışı, 30 günlük vade,
delta hedge) yeni bir ön kayıtla, yeni deneme sayılarak sınanabilir; bugünkü tanı onlar için güçlü bir gerekçe vermiyor
(put fazlalığı anlamlı değil, çıplak satış kuyruk riskini sınırsız bırakır).
