---
proje: TradeBot
created: 2026-10-06
type: turnuva-plani
durum: ön kayıt (koşudan önce commit edildi)
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
