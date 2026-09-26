---
proje: TradeBot
created: 2026-09-26
type: paper-listesi
---
# Paper Giriş Listesi

Ölçüt: `docs/Final-Dokuman.md` §Puan ve kapılar ve `docs/turnuva/Dalga-1.md` ek 3.
- **B:** sermayesiz gözlem.
- **A:** sermayeli paper.

**Parametre kuralı:** Paper'da walk-forward'ın SON penceresinin seçtiği varyant koşar (bugün elde olan son 3 yılla
seçilecek olan). Paper boyunca yılda bir, aynı walk-forward kuralıyla yeniden seçilir. Seçim değişikliği bir yeni
deneme sayılmaz, çünkü kural önceden yazılıdır. Kural değişikliği yeni denemedir.

| Kol | Sınıf | Paper varyantı | Backtest (tam dönem) | Walk-forward OOS | Kaynak |
| --- | --- | --- | --- | --- | --- |
| `ma_yon@kripto_btc_eth@1h` | B | hızlı 10 gün, yavaş 50 gün; long; %20 oynaklık | Sharpe 1,02, DD −%25, yıllık %19 | yıllık +%14,3, DD −%25 | dalga 1, 15a90cb |
| `tsmom@kripto_btc_eth@4h` | B | ufuk 250 gün; long; %20 oynaklık | Sharpe 1,05, DD −%24, yıllık %21 (ufuk 60) | yıllık +%14,6, DD −%24 | dalga 1, 15a90cb |
| `d2:donchian_ls@kripto_btc_eth@4h` | B | giriş 55, çıkış 20 gün; long; %20 oynaklık, **90 gün** oynaklık penceresi | Sharpe 1,20, DD −%17, yıllık %18 (çıkış 10) | yıllık +%12,3, DD −%22 | dalga 2, 47096bf |
| `d2:donchian_ls@kripto_btc_eth@1d` | B | giriş 55, çıkış 10 gün; long; 90 gün pencere | Sharpe 1,06, DD −%19, yıllık %15,5 | yıllık +%11,9, DD −%18 | dalga 2, 47096bf |
| `d2:tsmom@kripto_btc_eth@4h` | B | ufuk 250 gün; long; 90 gün pencere | Sharpe 1,03, DD −%22, yıllık %18 (ufuk 60) | yıllık +%15,4, DD −%24 | dalga 2, 47096bf |

**Not:**
- Beş kolun hepsi BTC+ETH trendi, yani aynı fikir. Aralarındaki korelasyon ~0,79. Faz 7 dağıtıcısı bunları tek risk
  olarak ele alır.
- Walk-forward OOS'ta (2021→) birlikte Sharpe 0,55. 1x'te yıllık %6,6; yarım Kelly (~2x) ile yıllık %12, düşüş −%32
  (`arastirma portfoy`).
- 2017–2020'deki güçlü kripto trendi sonrasında zayıfladı. Paper bunun bugün de sürüp sürmediğini ölçecek.
- Gözlemde her kol Jev vetolu ve vetosuz iki kopya olarak koşar (Faz 6–7).

**Bekleyen (Faz 5 kuyruğu, veri geldikçe koşar):**
- Dukascopy 1h/4h kolları.
- Dalga 1c (açılış aralığı kırılımı).
- Nihai `sonlandir`.

Yeni B/A çıkarsa bu listeye eklenir.
