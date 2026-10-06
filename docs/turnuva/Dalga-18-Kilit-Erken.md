---
proje: TradeBot
created: 2026-10-06
type: turnuva-plani
durum: sonuçlandı — −30 B, −14 KALDI; canlı d13 değişmez (2026-10-06)
---
# Turnuva — Dalga 18: kilit açılımı, erken giriş (ön kayıt)

Dosya: `config/turnuva/dalga18_kilit_erken.yaml`. Motor, veri ve maliyet dalga 13 ile aynı (`arastirma/kilit.py` →
`cekirdek/kilit.py`). Koşu: `tradebot arastirma kilit --dosya config/turnuva/dalga18_kilit_erken.yaml`.

## Neden

Dalga 16 (OI temizlenmesi sonrası dönüş) ve 17/17b (kesitsel funding) 2026-10-06'da kaldı. Kapıyı geçen tek aile kilit
açılımı. Keyrock'un 16.000+ açılım çalışması (Aralık 2024) baskının ortalama ~30 gün önce fiyatlanmaya başladığını,
ekip/yatırımcı açılımlarının en zararlı olduğunu söylüyor. Dalga 6'da −30/0 kolu Sharpe 0,82, −30/+7 kolu 0,97 idi, ama
ikisi de %10 nominal ve 3x brütle düşüş kapısında kaldı (−%48/−%49). Canlı kolun tavanlarıyla bu girişler ölçülmedi.

## Kural

d13 kolu aynen (eşik %0,5, nominal %5, brüt ≤ 1x, BTC ≤ 0,5, token perp kısa + BTC perp uzun, çıkış açılım günü), tek
fark giriş günü: −30 ya da −14. Tavan doluysa yeni olay kurulmaz: erken girişte açık olay sayısı artar, tavan daha sık
bağlar (raporlanır).

## Izgara (2 deneme, aile `kilit_kisa`)

giriş {−30, −14} × çıkış {0} × eşik {%0,5}. DSR dalga 6 (6) + 6b (1) + 13 (3) + bu (2) = 12 deneme.

## Önsel (dürüst, koşudan önce)

- Aynı veri, aynı dönem: kör dönem (2025+) d13 seçiminde de görüldü, bağımsız kanıt değil. Asıl sınama paper.
- Erken giriş 30 gün funding taşır; kısa bacak yükselişte funding alır, düşüşte ödeyebilir.
- Geçerse canlı d13 koluna dokunulmaz: ayrı paper kol olarak girer, ikisi paper'da kıyaslanır.

## Sonuç (2026-10-06, ön kayıt 78b1eb3)

| Kol | Karar | Sharpe | Yıllık | En kötü düşüş | DSR (12) | Kör (2025+) | Stres 2x | Kurulan / tavana takılan |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| giriş −30 | B | 0,75 | +%15,7 | −%22 | 0,90 | +%34,8 | +%13,7 | 471 / 346 |
| giriş −14 | KALDI (yıl pozitif 0,5) | 0,62 | +%10,0 | −%21 | 0,83 | +%27,4 | +%7,2 | 689 / 138 |
| (karşılaştırma) d13, giriş −7 | A | 0,99 | +%12,2 | −%17 | 0,98 | +%28,9 | +%9,0 | 802 / 28 |

Yıllar: −30 → 2021 −%16, 2022 +%7, 2023 +%10, 2024 +%41, 2025 +%51, 2026 +%9; −14 → 2021 −%11, 2022 −%1, 2023 −%2,
2024 +%33, 2025 +%33, 2026 +%13.

**Karar (Claude):** canlı d13 (−7) kalır. −30 olay başına daha çok kazandırıyor (+%4,4, t 3,5) ama riske göre daha
zayıf ve aynı tavan için d13 ile yarışır (korelasyonlu aynı sinyal); ayrı kol açılmaz.
