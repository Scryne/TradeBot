---
proje: TradeBot
created: 2026-10-06
type: turnuva-plani
durum: ön kayıt (koşudan önce commit edildi)
---
# Turnuva — Dalga 16: OI temizlenmesi sonrası dönüş (ön kayıt)

Dosya: `config/turnuva/dalga16_oi_donus.yaml`. Motor `src/tradebot/arastirma/um_dalga.py` (dalga16), çekirdek
`src/tradebot/cekirdek/oi_donus.py`. Koşu: `tradebot arastirma um --dosya config/turnuva/dalga16_oi_donus.yaml`.

## Neden

Scryne (2026-10-06): "kârlı bir sinyalin olması için ne gerekiyorsa yap." Ölçülen ~900 denemeden kapıyı geçen tek aile
kilit açılımı: fiyat deseni değil, **zorunlu akış** (ekip/yatırımcı satışı). Aynı mekanizmanın sık tekrarlanan biçimi
kaldıraçlı perp'lerde zorunlu kapanış: likidasyon motoru pozisyonu piyasa emriyle kapatır, satış bilgiden değil
kaldıraçtan gelir. Fiyat-tek-başına dönüş (ScryneQuant 15m/1h dönüş ızgarası) maliyette kaldı; burada fark, düşüşün
zorunlu olduğunu OI düşüşüyle ayırt etmek.

Kanıt durumu (dürüst): Seuma (arXiv 2608.03616, 2026) 2022–2025'te 7 Binance kaskadında OI'nin %25–70 temizlendiğini ve
zorunlu satışın %88'inin ilk 30 dakikada geldiğini gösteriyor; dönüş getirisini raporlamıyor. İşlem edilebilir dönüş
için hakemli kanıt yok. Önsel zayıf-orta.

## Kural

- Evren: Binance USDT-M perp'lerin tamamı (kaldırılanlar dahil, `data/um/`), olay anında önceki 30 günün ortalama
  günlük quote hacmi ≥ 20 M USDT ve ≥ 720 saat geçmiş.
- Olay (saat `t`, kapanmış bar): z = log(kapanış/açılış) / σ ≤ −4; σ = önceki 720 saatin saatlik log getiri std'si.
  OI koşulu: saatin son OI ölçümü / önceki saatinki − 1 ≤ eşik (ızgarada; "yok" = kontrol kolu).
- Giriş `t+1` açılışı, çıkış `t+1+tut` açılışı. Perp uzun; hedge'li kolda aynı nominal BTC perp kısa.
- Olay başına bacak nominali özkaynağın %5'i; açık brüt ≤ 1x (hedge'li olay 2 bacak). Aynı saatte çok olay: en sert z
  önce; tavan doluysa olay kurulmaz. Aynı sembolde açık pozisyon varken yeni olay alınmaz.
- Funding tutulan nominal üzerinden (uzun öder, kısa alır). Maliyet: ücret %0,05 + kayma %0,10 (token) / %0,01 (BTC),
  giriş ve çıkışta; stres 2x. Kaskad saatinde kayma bunun üstünde olabilir: giriş kaskad saatinin değil sonraki saatin
  açılışında, stres 2x de raporlanır.

## Izgara (12 deneme, yeni aile `oi_donus`)

OI eşiği {yok, −%5, −%10} × tutma {4 s, 24 s} × BTC hedge {yok, var}. Dönem 2022-01 → 2026-09; örneklem içi 2022–2024,
kör 2025-01 → 2026-09 (2025-10-10 kaskadı kör dönemde). Ölçüt dalga 13 ile aynı (A: DSR ≥ 0,95).

## Önsel (dürüst, koşudan önce)

- Kaskad sonrası düşüş sürebilir (Kasım 2022 FTT, Mayıs 2022 LUNA: kaldırılan perp'ler veride, hayatta kalan yanlılığı
  yok). Hedge'siz kol piyasa betası taşır; asıl soru hedge'li kolun ve OI'li/OI'siz farkının işareti.
- Saatlik karar kaskadın içindeki dönüşü kaçırır (fitil aynı saatte kapanır); yakalanan yalnız sonraki saatlerin devamı.
- Ücretsiz likidasyon akışı 2024-03'ten sonra arşivde yok; OI düşüşü vekildir (kapanan uzun da kısa da OI'yi düşürür:
  fiyat düşüşüyle birlikte uzun kapanışı ağır basar).
