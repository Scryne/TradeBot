---
proje: TradeBot
created: 2026-09-27
type: olcum
plan: 2026-09-27-c2-fomc-ton
---
# C2 — FOMC karar metninin tonu (Jev)

Betik: `research/olcum/c2_fomc_ton.py` (e87e455). Spike: `research/spikes/06_c2/`. Plan koşudan önce deneme defterine
yazıldı (kural 10). Çıktı: host `data/olcum/c2_fomc_ton.json`. Ham HTML'ler ham depoda (`fed/fomc/<tarih>`), Jev
yargıları `jev_yargi`'da dondurulmuş (rol `C2_fomc`).

## Tasarım

- Jev yalnız metni yargılar (kural 8). State'te yalnız açıklama metni var, **tarih yok**: model metni tanıyıp piyasa
  tepkisini hatırlamasın. Yine de örneklemin tamamı modelin eğitim kesiminden önce olabilir (sızıntı riski işaretli).
- Sorular: `ton` (Score, 0 güçlü gevşetici … 4 güçlü sıkılaştırıcı; her seviye somut durumla tanımlı) ve `karar`
  (Choice: artış / sabit / indirim; metni doğru okuduğunun sağlaması).
- Spike (sonuca bakmadan yazılan beklentiyle): 2022-06 → 4,0 · 2020-03-15 → 0,0 · 2012-09 QE3 → 0,0 (faiz sabitken
  metnin anlamını okudu) · 2015-12 → 3,63 (güven 0,69; gerçekten iki seviye arası). Karar 4/4.
- Özellik: Δton = ton − önceki kararın tonu (sürprizin yaklaşık ölçüsü).
- Ön kayıtlı testler: doğrulama Spearman t(Δton, TLT aynı gün) ≤ −2; işlem yapılabilirlik: sonraki 5 gün TLT/SPY/GLD/BTC
  için |t| ≥ 2,5.

## Sonuç

- 173 karar (2006 → 2026). Ton dağılımı (0…4): 58 / 34 / 20 / 36 / 25. Karar: 25 artış, 129 sabit, 19 indirim
  (dönemin gerçeğine yakın: ~24 artış, ~21 indirim): **Jev metni doğru okuyor.**

| Test | n | Spearman r | t | Eşik | Geçti |
| --- | --- | --- | --- | --- | --- |
| Doğrulama: Δton ↔ TLT aynı gün | 170 | −0,054 | −0,70 | ≤ −2 | ✗ |
| Δton ↔ SPY aynı gün | 170 | +0,099 | +1,29 | — | — |
| Δton ↔ TLT sonraki 5 gün | 170 | −0,038 | −0,49 | \|t\| ≥ 2,5 | ✗ |
| Δton ↔ SPY sonraki 5 gün | 170 | +0,037 | +0,48 | \|t\| ≥ 2,5 | ✗ |
| Δton ↔ GLD sonraki 5 gün | 170 | −0,027 | −0,35 | \|t\| ≥ 2,5 | ✗ |
| Δton ↔ BTC sonraki 5 gün | 77 | +0,088 | +0,76 | \|t\| ≥ 2,5 | ✗ |

**Karar: ÖZELLİĞE GİRMEZ.**

## Yorum

- Sorun Jev'in okuması değil, özelliğin tanımı. Fed kararlarını önceden işaret eder; tondaki değişim çoğunlukla piyasanın
  zaten beklediği şeydir. Piyasayı hareket ettiren, beklentiye göre sürprizdir. Beklentiyi ölçmek fed funds vadeli
  verisi ister (elde yok, ücretli).
- Bu sonuca bakıp özelliği yeniden tanımlamak yeni bir denemedir (kural 10). Beklenti verisi gelirse ayrı bir planla
  açılır. Donmuş ton yargıları o ölçümde yeniden kullanılabilir (Jev çağrısı gerekmez).
- Global not (TypeSafe.md) ile uyumlu: Jev metnin ne dediğini doğru söylüyor; bunun piyasaya ne yapacağını söylemiyor.
