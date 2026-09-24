# TradeBot

Scryne'ın kendi hesabı için kurumsal kalitede, çok piyasalı, tamamen otonom trade sistemi. İlk aşama yalnız paper.
Motor NautilusTrader v2. Etrafındaki katmanlar bize ait: zekâ (Jev), araştırma/turnuva, risk ve operasyon.

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

> Kişisel araştırma yazılımıdır; yatırım tavsiyesi değildir, para kaybettirebilir. Yalnız sahibinin kendi
> hesabında ve kendi sermayesiyle çalışır.
