---
proje: TradeBot
created: 2026-10-24
type: turnuva-plani
durum: ön kayıt (koşudan önce commit edildi)
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
