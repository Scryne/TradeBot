---
proje: TradeBot
created: 2026-10-05
type: iddia-olcumu
---
# Stopsuz "TP'ye kadar bekle" altın botu (BorsaWorkout Otobot yapısı)

Betik ve ön kayıt: `research/altin/stopsuz.py` (c52ad75; ek deneme `--yon uzun` fcb9793, ilk koşudan sonra ayrı ön
kayıt). Sonuçlar: `research/altin/sonuc/stopsuz_{yazitura,uzun}_2026-10-05.json`. Veri Dukascopy XAUUSD 1 dk,
2023-09-01 → 2026-10-02. 31 başlangıç (her ay başı), 26 hafta; 1.000 $, 1:1000, stop-out %20, TP 1,5 $, stop yok,
30 dk'da bir giriş, en çok 10 açık işlem, swap yok (bot lehine).

| Giriş | Lot / 1.000 $ | Spread | Hesabı biten | Bitene kadar (ortanca) | İşlem başı kazanma |
| --- | --- | --- | --- | --- | --- |
| yazı-tura | 0,01 | 0,35 | 31 / 31 | 5 hafta | %97,7 |
| yazı-tura | 0,02 | 0,35 | 31 / 31 | 3 hafta | %96,4 |
| yazı-tura | 0,05 / 0,10 | 0,35 | 31 / 31 | 2 / 1 hafta | |
| yalnız alış | 0,01 | 0,35 | 27 / 31 | 9 hafta | %99,3 |
| yalnız alış | 0,01 | 0,70 | 29 / 31 | 7 hafta | %99,0 |
| yalnız alış | 0,02 | 0,35 | 31 / 31 | 5 hafta | %98,7 |

- İşlemlerin %97–99'u kârla kapanıyor; kapanmayan birkaç işlem hesabı bitiriyor.
- Yalnız alışta (2023–26 altın yükselişi) haftalık getiri ortancası +%11, en uzun kazançlı hafta serisi 14; örnek
  2025-09 başlangıcı: +26, +15, +28, +18, +32, +29, −44, −100 (%). Hayatta kalan 4 başlangıç (2023-10/11/12, 2024-05)
  26 haftayı geçti; 2024-05 başlangıcı 14.698 $ ile bitirdi, arada −%62 ve −%64'lük haftalar yaşadı.
- Kanalın tanımıyla "%100 hafta" (hafta sonunda açık işlem yok) bu kuralda seyrek, çünkü giriş cuma 21:00'e kadar
  sürüyor; bu, hesabın bitme sonucunu değiştirmez.
- Sınır: kanalın giriş sinyali bilinmiyor (yazı-tura ve yalnız alış iki uç). Doğrulanmış kayıt olmadan daha iyi bir
  sinyal varsayılamaz.
