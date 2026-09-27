---
proje: TradeBot
created: 2026-09-27
type: olcum
plan: 2026-09-27-c1-veto-etkisi
---
# C1 — Jev vetolarının koruma değeri (olay çalışması)

Betik: `research/olcum/c1_veto_etkisi.py` (b9f59e6). Plan koşudan önce deneme defterine yazıldı (kural 10).
Çıktı: host `data/olcum/c1_veto_etkisi.json`.

**Soru:** veto verilen enstrümanı tutan biri, veto olmasaydı ne kaybederdi? Giriş = vetonun motora görünür olduğu
andan (`gecerli_ms`) sonraki ilk barın açılışı. Anormal getiri = enstrüman − kıyas. Kıyas: A1 için BTCUSDT (1h), A2 için
aynı penceredeki BIST kesitinin medyanı (1d). Onaylı `kaldir` olayıyla kapatılan (yanlış) vetolar çıkarıldı.

**Ön kayıtlı ölçüt:** 7 gün anormal getiri medyanı < −%5 → koruma VAR; −%5…0 → ZAYIF; ≥ 0 → YOK. Duyurudan önceki
7 günde medyan |x| ≥ %2 → SIZINTI işareti.

## Sonuç

| Rol | n | Önceki 7 g | 1 g | 7 g | 30 g | 7 g negatif | Karar |
| --- | --- | --- | --- | --- | --- | --- | --- |
| A1 Binance | 162 | −%20,4 | −%4,4 | **−%21,1** | −%45,3 | %83 | **VAR** (sızıntı işareti) |
| A2 KAP (kısmi) | 300 | +%4,6 | −%0,6 | −%1,0 | −%0,3 | %56 | **ZAYIF** (sızıntı işareti) |

Etikete göre (keşif amaçlı; kural değişikliği yapılmadı, yapılırsa yeni denemedir):

| Rol · etiket | n | Önceki 7 g | 7 g | 30 g |
| --- | --- | --- | --- | --- |
| A1 `token_delist` | 132 | −%23 | −%28 | −%58 (131'i fiilen delist) |
| A1 `usdt_pair_removed` | 25 | ~0 | −%3,6 | −%15 |
| A2 `pazar_tedbiri` | 168 | +%16,5 | −%2,1 | −%2,4 |
| A2 `olumsuz_esasli` | 119 | ~0 | −%0,4 | +%2,0 |

## Yorum

- **A1'in koruma değeri güçlü.** Veto olmasa pozisyon sahibi 7 günde tipik olarak beşte birini, delist'e kadar yarısından
  fazlasını kaybederdi.
- **Sızıntı işaretleri sistem sızıntısı değil, seçim etkisi.**
  - A1: Binance zaten düşüşteki, hacmi erimiş coinleri delist ediyor. Duyurunun kendisi yine haber: ilk gün ek −%4,4.
  - A2: pazar tedbiri anormal yükselen hisselere konuyor (önceki 7 gün +%16,5).
  - Temiz kanıt `usdt_pair_removed`: öncesinde hareket yok, sonrasında kayıp var.
- **A2 zayıf:** `olumsuz_esasli` vetosu ortalamada ne koruyor ne maliyet getiriyor. Veto süreleri (30/20 gün) keyfi
  başlangıçtı, A/B'de ölçülecekti. KAP geçmişi tamamlanınca (~2026-10-07) tam örneklemle **yeni bir planla** yeniden
  ölçülür: süre ve etiket bazında. Bu sonuca bakıp mevcut kuralı değiştirmek yeni denemedir.
- Sınır: olay çalışması tek tek vetoların ortalama etkisini ölçer; portföydeki kolun Jev'li/Jev'siz farkı paper A/B'de
  ölçülüyor (BTC/ETH'de veto çok nadir).
