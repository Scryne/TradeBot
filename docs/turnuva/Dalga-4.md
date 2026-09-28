---
proje: TradeBot
created: 2026-09-29
type: turnuva-plani
durum: ön kayıt (koşudan önce commit edildi)
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
