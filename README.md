# TradeBot

Scryne'ın kendi hesabı için kurumsal kalitede, tamamen otonom trade sistemi. İlk aşama yalnız paper.
**2026-10-18'den beri odak Nasdaq (ABD hisseleri):** point-in-time Nasdaq-100 evreni, günlük kesitsel kol ve QQQ gün içi
kolu, Alpaca paper (anahtar yoksa iç simülasyon). Kripto/forex kolları emekli. Etrafındaki katmanlar bize ait: araştırma
/turnuva (ön kayıt, deneme defteri, DSR), beş katmanlı risk, zekâ (Jev), operasyon (gözetmen, Telegram, pano).

| Soru | Belge |
| --- | --- |
| Ne yapıyoruz, neden? | `docs/Proje-Fikri.md` · `docs/Final-Dokuman.md` (bağlayıcı) |
| Nerede kaldık? | `docs/Roadmap.md` |
| Araştırma ve kanıtlar | `docs/Arastirma.md` · `docs/spikes/` |
| Host (ev bilgisayarı) kurulumu | `docs/host/Kurulum.md` |
| Değişmez kurallar | `.claude/CLAUDE.md` |

## Geliştirme

```bash
uv sync                      # bağımlılıklar
uv run pytest                # testler
uv run ruff check src tests  # stil
cp .env.example .env         # sırları doldur (git'e girmez)
docker compose up -d --build # postgres + göç + sağlık izleyici
docker compose run --rm --no-deps saglik tradebot saglik   # sağlık raporu
```

## Komutlar

| Komut | Ne yapar |
| --- | --- |
| `tradebot saglik [--dongu SN] [--json]` | DNS, saat kayması (NTP + Binance), veritabanı + denetim izi zinciri, disk, sırlar |
| `tradebot db yukselt` | Alembic göçlerini uygular |
| `tradebot db denetim-dogrula` | Denetim izinin hash zincirini doğrular |
| `tradebot veri nasdaq [--guncel]` | Nasdaq-100 PIT üyelik + bütün tarihî üyelerin Yahoo günlük barları |
| `tradebot arastirma turnuva --dosya config/turnuva/dalga19_nasdaq.yaml` | Ön kayıtlı dalgayı koşar (her varyant deneme defterine) |
| `tradebot paper nasdaq` · `tradebot paper nasdaq-gun-ici` | Nasdaq günlük ve gün içi paper düğümleri (compose `nasdaq`, `nasdaq-gun-ici`) |
| `tradebot paper alpaca-kontrol` | Alpaca PAPER hesabını salt okur (anahtar: `tools/host/alpaca_anahtar.ps1`) |

> Kişisel araştırma yazılımıdır; yatırım tavsiyesi değildir, para kaybettirebilir. Yalnız sahibinin kendi
> hesabında ve kendi sermayesiyle çalışır.
