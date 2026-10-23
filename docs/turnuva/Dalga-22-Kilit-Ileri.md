---
proje: TradeBot
created: 2026-10-24
type: turnuva-plani
durum: sonuçlandı — uyumlu (kural ayakta, paper'a döndü; 2026-10-24)
---
# Turnuva — Dalga 22: kilit açılımı kolunun ileri testi (ön kayıt)

Dosya: `config/turnuva/dalga22_kilit_ileri.yaml`. Karar: Claude, 2026-10-24 gecesi (Scryne: "amacım para kazanmak",
"herşeyi sana bırakıyorum", "hiçbir sınırın yok").

## Neden

2026-10-23 analizinin bulgusu: projede ölçülmüş tek gerçek kenar kilit açılımı kolu (dalga 13 A: Sharpe 0,99, DSR 0,98,
802 olay). Nasdaq kollarının hiçbiri QQQ al-tutu geçmiyor; funding taşıması 2025'ten beri T-bill'in altında (BTCUSDT
yıllık funding 2024 %12,0 → 2025 %5,1 → 2026 yılbaşından bu yana %2,2; taban oranda geçen sürenin payı %42 → %7).
Kilit kolu 2026-10-09 dondurmasında, kuralına bağlı olmayan bir yön kararıyla durdu; kuralın kendisi hiç çürütülmedi.

Kural 2026-10-01'de donduruldu (canlı d13). O tarihten sonra gerçekleşen açılımlar kuralın seçiminde kullanılmadı: gerçek
bir örneklem dışı. Bu dalga yeni kural aramaz, ızgara tek noktadır (d13'ün kendisi).

## Kural

Dalga 13'ün A kolu, birebir: `config/paper.yaml` `kilit` bloğu ile aynı parametreler (giriş −7, çıkış 0, eşik %0,5,
nominal %5, BTC ≤ %50, brüt ≤ 1x, maliyet ücret 5 bps + token kayma 10 bps + BTC kayma 1 bps, stres 2x). Veri
2026-10-24'te yeniden indirilir (`data/ileri/kilit/`; mevcut `data/kilit/` değişmez).

## Önsel (dürüst, koşudan önce)

- Dondurmadan bu yana ~3 hafta geçti. Olay başına ortalama +%1,77, σ ≈ %16 (Canli-Kontrol-2026-10-07): ~20 olayla
  ortalamanın standart hatası ~%3,6. Bu koşu kuralı **kanıtlayamaz**; yalnız kaba bir çürütme yapabilir (ör. olay
  başına ortalama belirgin negatifse).
- DefiLlama geçmiş olayları sonradan düzeltebilir (Dalga-6.md). Dondurma öncesi dönem yeniden indirilen tabloyla küçük
  farklar gösterebilir; dalga 13 sonuçlarıyla fark ayrıca raporlanır.
- Canlı paper kol 2026-10-02 → 10-09 arasında −%3,5 kapattı (kilit paper 96.535). Bu ileri testin içinde kalan
  olaylardır.

## Karar ölçütü (sonuçtan önce yazıldı)

- **Çürütme:** dondurma sonrası olay başına ortalama < 0 ve t < −2 → kilit kolu kapanan fikirlere eklenir.
- **Uyumlu:** dondurma sonrası olay başına ortalama ≥ 0 ya da |t| < 2 → kural ayakta kalır; ileri kanıt biriktirmek için
  kilit paper kolu yeniden açılır (iç simülasyon; Binance Demo kolu ve gerçek para yine Scryne'ın kararı, kural 7).
- Tam dönem kapıları (DSR, yıl, stres, en kötü hafta/düşüş) dalga 13 ile aynı; bilgi olarak raporlanır.

## Sonuç (2026-10-24, koşu `tradebot-d22`, ön kayıt 6b6e5c1)

**Uyumlu: dondurma sonrası olaylar kuralı çürütmedi.** Kilit paper kolu yeniden açıldı. Binance Demo kolu (sahte para) Scryne'ın 2026-10-24 gecesi verdiği yetkiyle ("tüm yetkileri veriyorum", "hiçbir sınırın yok") yeniden açıldı; ana ağa geçiş (`onay`) yine onun açık kararıdır.

| Dilim | Kurulan olay | Olay başına ort. | Medyan | İsabet | t |
| --- | --- | --- | --- | --- | --- |
| **İleri: giriş dondurmadan sonra (açılım 10-08 → 10-23)** | 17 | **+%4,01** | +%6,33 | %59 | 0,69 |
| Dondurma penceresine taşan (açılım 10-01 → 10-07) | 4 | −%2,97 | −%3,13 | %50 | −1,30 |
| Eylül 2026 (karşılaştırma, örneklem içi) | 27 | −%1,44 | −%2,44 | %41 | −0,48 |
| Tam dönem 2021-01 → 2026-10 (yeniden indirilen veri) | 833 | +%1,70 | +%2,48 | %61 | 3,06 |

- Tam dönem (taze veri): yıllık +%11,9, Sharpe 0,90, en kötü düşüş −%17,2, en kötü hafta −%7,7; maliyet 2x stres +%8,6.
  Yıllar: 2021 −%4,7, 2022 +%0,1, 2023 +%6,9, 2024 +%23,5, 2025 +%29,8, 2026 (10-23'e kadar) +%18,0. Dalga 13'teki
  sonuçla (Sharpe 0,99) uyumlu; fark DefiLlama'nın sonradan düzelttiği olaylardan ve 1 aylık ek veriden.
- Motorun kendi kararı KALDI, çünkü kör dilim 3 hafta (özet ≥ 10 hafta ister; OOS kapısı boş). Ön kayıttaki karar ölçütü
  olay başınadır: ortalama ≥ 0 → uyumlu.
- Portföy (özkaynak) 2026-10-01 → 10-23: +%3,74.
- **Kuyruk riski gerçek:** STRK (açılım 10-14) −%72,6 (perp 10-07 0,0516 → 10-11 0,1231, short squeeze; veri doğrulandı).
  Olay başına nominal %5 olduğundan özkaynağa etkisi ~−%3,6. Kural zarar kes içermez (dalga 13 böyle seçti).
- İleri kanıtın gücü (dürüst): 17 olayla t 0,69. Kuralın kenarı bu örneklemle kanıtlanamaz; yalnız çürütülmedi.
