---
proje: TradeBot
created: 2026-10-06
type: turnuva-plani
durum: sonuçlandı — 12/12 KALDI (2026-10-06)
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

## Sonuç (2026-10-06, ön kayıt 657ce76, veri 1h + OI kaldırılanlar dahil): **12/12 KALDI**

| Kol | Sharpe | Yıllık | En kötü düşüş | Kör (2025+) | Olay | Olay ort. (maliyet dahil) |
| --- | --- | --- | --- | --- | --- | --- |
| kontrol (OI yok), 4 s | −1,73 | −%42 | −%92 | −%57 | 10.208 | −%0,46 |
| OI ≤ −%5, 4 s | −0,93 | −%11 | −%42 | −%18 | 2.501 | −%0,42 |
| OI ≤ −%10, 4 s | −0,29 | −%2,6 | −%24 | −%14 | 829 | −%0,31 |
| **OI ≤ −%10, 24 s (en iyi)** | **−0,07** | **−%2,0** | **−%23** | **−%6,4** | **815** | **−%0,14** |
| OI ≤ −%10, 24 s, BTC hedge | −0,50 | −%6,1 | −%27 | −%8,1 | 685 | −%0,83 |

Okuma: sert düşüşten sonra fiyat dönmüyor, sürüyor (kontrol kolu maliyet öncesi de eksi). OI düşüşü koşulu kaybı
küçültüyor, yani zorunlu kapanış bilgisi bir şey söylüyor, ama işaret değişmiyor: en iyi kolda olay başına brüt ~+%0,16,
maliyet ~%0,30. Hedge'li kollar daha kötü: kaskattan sonra token BTC'nin de gerisinde kalıyor. Yıllar (en iyi kol):
2022 −%22, 2023 +%13, 2024 +%15, 2025 +%2, 2026 −%13. Aile kapanır; tersi (kaskattan sonra kısa) olay başına brüt
~%0,16 ile maliyeti karşılamaz.
