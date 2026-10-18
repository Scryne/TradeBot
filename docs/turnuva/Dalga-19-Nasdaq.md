---
proje: TradeBot
created: 2026-10-18
type: turnuva-plani
durum: ön kayıt (koşudan önce commit edildi)
---
# Turnuva — Dalga 19: Nasdaq-100 hisseleri, günlük (ön kayıt)

Dosya: `config/turnuva/dalga19_nasdaq.yaml`. Çekirdek: `src/tradebot/cekirdek/hisse.py` (saf, nedensel;
`tests/test_nasdaq.py`). Evren: `src/tradebot/veri/nasdaq100.py`, `config/nasdaq.yaml`.

## Neden

Scryne 2026-10-18'de yönü değiştirdi: TradeBot "Nasdaq gibi borsalarda çalışan bir trade bot" olacak, günlük ve gün
içi kollarla, host'ta 7/24 paper. Önceki ABD ölçümleri ETF ve endeks düzeyindeydi (dalga 1–2 ABD ETF sepeti, dalga 11
endeks takvimi; hiçbiri geçmedi, al-tut aynı boyutta Sharpe 0,63). Bu dalga ilk kez **tek hisselerde** ölçer:
belgelenmiş kesitsel primler (momentum, kısa vadeli dönüş, düşük oynaklık) ancak hisse kesitinde vardır.

| Strateji | Hipotez | Kaynak | Yayın sonrası kanıt (dürüst önsel) |
| --- | --- | --- | --- |
| `hisse_momentum` | 6–12 ay kazananları (son ay atlanır) kazanmaya devam eder | Jegadeesh-Titman (1993) | Prim 1994–2015'te yarıya indi (Swedroe 2016); Hou-Xue-Zhang (2020) büyük hisselerde küçük ama ayakta |
| `kisa_donus` | Son 1–2 haftanın kaybedenleri geri döner (likidite sağlama primi) | Lehmann (1990), Nagel (2012) | Hou-Xue-Zhang (2020): değer ağırlıklı yapıda ayakta kalmıyor; büyük hisselerde zayıf |
| `dusuk_oynaklik` | Düşük oynaklıklı hisseler risk ayarlı olarak fazla getiri verir | Ang ve ark. (2006), Blitz-van Vliet (2007) | Novy-Marx-Velikov: primin çoğu küçük hisselerden; maliyet kârı ~%60 azaltıyor |
| `esit_agirlik` + filtre | Sepet kendi 100/200 gün ortalamasının üstündeyken tutulur | Faber (2007) | ETF'lerde dalga 1–2'de KALDI (al-tutu geçmedi) |

Genel önsel: McLean-Pontiff (2016) yayımlanmış primlerin yayın sonrası ~%58 küçüldüğünü ölçtü. Nasdaq-100 en büyük ve en
likit 100 hissedir; kesitsel primlerin en zayıf olduğu evrendir. Beklenti düşüktür, ölçüm bunun için yapılır.

## Evren (point-in-time) ve veri

- **Üyelik:** `jmccarrell/n100tickers` (MIT; Nasdaq duyurularından, 2007-02-01 → 2026-10-11), sabit commit
  `2d7be39`. Yıllık dosyalar ham depoya (hash kimlik), ayrıştırıcı her yıl başının değişikliklerle tutarlı olduğunu
  doğrular. Bar t'nin evren satırı t gününün üyeliğidir (ekleme/çıkarma yürürlükten günler önce duyurulur).
- **Fiyat:** Yahoo günlük, `adj_close` ile bölünme + temettü düzeltmeli toplam getiri.
- **Hayatta kalma yanlılığı (bilinen sınır):** 285 tarihî üyenin 81'inin Yahoo'da verisi yok (satın alınan/kapanan:
  ATVI, CELG, XLNX, YHOO, SGEN, SPLK…). Sembolü değişen 9 şirket eşlendi (`sembol_esleme`: FB→META, PCLN→BKNG…).
  Sembolü başka şirkete geçmiş olanlar dönem kapsamıyla dışlanır: üyelik dönemi yalnız fiyat serisi o dönemin başından
  (≤ 10 seans) varsa evrene girer (FB = bugün bir ETF, LIFE = başka şirket, EA ve WBD'nin eski geçmişi Yahoo'da yok).
  Kapsam oranı (verisi olan üye-gün / bütün üye-gün) yıl yıl raporlanır. Bu yüzden grup **en fazla B**: Alpaca'nın
  2016+ verisiyle (kapanan sembolleri de tutuyor) yeniden ölçülmeden A olamaz.
- Dönem: 2006-01 fiyat (ısınma), üyelik 2007-02 →, ölçüm 2025-12-31'e kadar; **2026-01 → 10 kör** (seçilen varyant
  sonradan ölçülür, bilgi).

## Kural

- Yalnız uzun, ağırlık toplamı ≤ 1, kalan nakit (faiz geliri yok sayılır; aleyhte). Karar gün kapanışında, dolum
  ertesi günün açılışında (kural 4); canlıda Alpaca açılış emri ya da açılıştan sonraki ilk dakika.
- `hisse_momentum` (8): geriye {126, 252} gün × ilk {10, 20} × piyasa filtresi {yok, 200 gün}; son 21 gün atlanır,
  ayın ilk işlem günü yenilenir, getirisi negatif olan seçilmez.
- `kisa_donus` (4): geriye {5, 10} gün, en çok düşen 10, hisse trendi {yok, 200 gün}; haftanın ilk günü yenilenir.
- `dusuk_oynaklik` (4): pencere {60, 250} gün, en düşük 20, piyasa filtresi {yok, 200 gün}; aylık.
- `esit_agirlik` (2): bütün üyeler eşit, piyasa filtresi {100, 200} gün; aylık, filtre kapanınca hemen nakit.
- Piyasa filtresi: evrenin eşit ağırlıklı endeksi kendi ortalamasının altındaysa nakit (dış seri yok).
- Boyut: kol %20 yıllık oynaklık hedefi (60 gün, ex-ante), **1x brüt tavan** (nakit hesap), hisse başı ≤ 0,5, bant
  0,25, frenler açık (günlük −%3, haftalık −%8, acil −%25).

## Maliyet (aleyhte, koşudan önce sabit)

`NASDAQ:hisse`: ücret 0,5 bps (Alpaca komisyonu 0; SEC 20,6 $/milyon satışta, FINRA TAF, CAT), yarım spread 2 bps,
kayma 3 bps → taraf başı 5,5 bps, gidiş-dönüş 11 bps. Kayma açılış dolumu içindir: Alpaca paper açılış emrini müzayede
fiyatıyla değil anlık bid/ask'tan dolduruyor (2021 kullanıcı ölçümü 12–43 bps sapma). Stres: maliyet 2 kat, bir gün
gecikme.

## Karar ölçütü

Önceki dalgalarla aynı huni (`turnuva.karar`): A = DSR ≥ 0,95 + plato + tam dönem kapıları + walk-forward OOS yıllık
> **%4,5 (T-bill çıtası)** + yılların ≥ %60'ı pozitif + rejim + stres; B = DSR şartı yok. Grup en fazla B (yukarıda).
DSR aile başına, ailenin bütün denemeleriyle (momentum, ortalamaya dönüş ve trend aileleri önceki dalgalarla ortak).
Kıyas (bilgi, deneme değil): evrenin eşit ağırlıklı al-tutu ve QQQ.

## Paper'a ne girer (sonuçtan önce yazıldı)

- B çıkan her ailenin en iyi varyantı Nasdaq paper düğümünde (`canli/nasdaq.py`) gözlem kolu olarak çalışır.
- **Hiçbiri geçmezse:** Scryne'ın yön kararı gereği Nasdaq botu yine çalışır; walk-forward OOS Sharpe'ı en yüksek
  varyant "gözlem kolu" etiketiyle paper'a girer ve haftalık raporda backtest sonucuyla birlikte gösterilir. Gerçek
  para kapısı değişmez (Final Doküman: DSR ≥ 0,95 + plato ya da paper PSR(0) ≥ 0,95; kural 7 onayı).
- Sonuca bakıp ızgara ya da ölçüt değiştirilmez (kural 10); ek fikir yeni dalgadır.
