---
proje: TradeBot
created: 2026-09-26
type: turnuva-ara-sonuc
durum: dalga 1 günlük + kripto gün içi tamam; Dukascopy 1h/4h ve dalga 1c veri bekliyor
---
# Turnuva Dalga 1: Ara Sonuç (2026-09-26)

Ön kayıt: `docs/turnuva/Dalga-1.md`. Ölçüt değişmedi. Kod: 15a90cb (kripto, ABD), 7eda906 (BIST, FX, endeks),
4942f24 (Dukascopy emtia/hepsi). Denemeler (defter, tarama): trend 498, ortalamaya dönüş 70, kesitsel 42, takvim 12,
carry 9.

## Özet

- **66 kol + carry: A yok, B yok.**
- **En güçlü sonuç: BTC+ETH trendi.**
  - %20 oynaklıkta Sharpe 0,95–1,11, yıllık ~%20; walk-forward OOS yıllık +%12–17, OOS düşüş −%21 ile −%25.
  - Stres testlerinden geçiyor (2x maliyet, 1 bar gecikme).
  - Takıldığı yer DSR: ailede ~500 deneme var, bu da yıllık Sharpe ~1,6 gerektiriyor. Kolların çoğu ayrıca bir kez
    acil durdurma (−%25) tetikliyor.
  - DSR dışındaki bütün koşulları geçen 2 kol: `ma_yon@kripto_btc_eth@1h`, `tsmom@kripto_btc_eth@4h`.
- **Genişleyen sepet kötüleşiyor.**
  - Kripto ilk 30 < ilk 10 < BTC+ETH.
  - Altcoinler çöküşte birlikte düşüyor ve maliyetleri yüksek.
- **CFD ile kaldıraçlı trend ekonomik değil (bu maliyet modelinde).**
  - FX, endeks ve emtia CFD'lerinde %20 hedefe ~2–3x brüt maruziyetle ulaşılıyor.
  - Yıllık %2–6 finansman × 2–3x maruziyet, getiriyi siliyor: dk_hepsi Sharpe −0,56.
  - FX trendi 2010 sonrası maliyetten önce de negatif.
- **Oynaklık hedefi sakin dönemde kaldıraç şişiriyor.**
  - Nisan 2019'da 30 günlük oynaklık ~%8'di; kol altı ilişkili endekste ~3x long'a çıktı.
  - Mayıs'ta −%20 ile sonuçlandı.
- **Ortalamaya dönüş hiçbir piyasada çalışmadı.** BIST hisselerinde −%90'a varan düşüş.
- **Carry (funding) kaldı.** Getiri yalnız 2020–21'den geliyor; 2022'den beri funding eşiğin altında.
- **Motor doğrulaması.** ABD ETF sepetinde ders kitabı TSMOM (bağımsız hesap) Sharpe 0,60, motor 0,52 verdi.
  Düzey tutarlı.

## Dalga 2 için öğrenilenler (ön kayıtla sınanacak, dalga 1'e sonradan eklenmez)

1. Daha yavaş oynaklık tahmini (ör. 90 gün ya da karışım) ve varlığın doğal oynaklığına yakın hedef.
2. CFD yerine düşük finansmanlı araç: spot/ETF ya da vadeli (CME, ücretli veri: roadmap dalga 3).
3. Kripto büyüklerde odak; perp ile short (ayrı karar).

## Puan tablosu (koşu anı DSR'ı; nihai DSR dalga sonunda `sonlandir` ile)

| Karar | Kol | En iyi varyant | Puan %/hf | Yıllık | Sharpe | DD | Kötü hf | DSR | Plato | OOS yıllık | OOS DD | Yıl + | 2x maliyet | Gecikme |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| KALDI | donchian_ls@kripto_btc_eth@4h | donchian_ls(cikis_gun=20,giris_gun=20) | 0.376 | 21.7% | 1.08 | -28% | -8.8% | 0.48 | var | 13.1% | -24% | 62% | 20.6% | 20.3% |
| KALDI | donchian_ls@kripto_btc_eth@1h | donchian_ls(cikis_gun=20,giris_gun=20) | 0.375 | 21.6% | 1.11 | -28% | -7.9% | 0.52 | var | 13.8% | -23% | 62% | 20.8% | 21.3% |
| KALDI | tsmom@kripto_btc_eth@4h | tsmom(ufuk_gun=60) | 0.357 | 20.5% | 1.05 | -24% | -7.7% | 0.44 | var | 14.6% | -24% | 75% | 16.3% | 17.0% |
| KALDI | donchian_ls@kripto_ilk10@4h | donchian_ls(cikis_gun=10,giris_gun=55) | 0.346 | 19.8% | 1.01 | -26% | -7.9% | 0.42 | var | 14.1% | -26% | 75% | 18.2% | 19.8% |
| KALDI | tsmom@kripto_btc_eth@1d | tsmom(ufuk_gun=20) | 0.343 | 19.6% | 0.97 | -32% | -9.9% | 0.36 | var | 16.5% | -21% | 75% | 15.9% | 21.0% |
| KALDI | donchian_ls@kripto_btc_eth@1d | donchian_ls(cikis_gun=20,giris_gun=20) | 0.338 | 19.3% | 0.95 | -27% | -10.7% | 0.33 | var | 13.1% | -21% | 62% | 18.2% | 19.5% |
| KALDI | ma_yon@kripto_btc_eth@1h | ma_yon(hizli_gun=10,yavas_gun=50) | 0.338 | 19.3% | 1.02 | -25% | -9.2% | 0.43 | var | 14.3% | -25% | 75% | 17.3% | 18.7% |
| KALDI | ma_yon@kripto_btc_eth@4h | ma_yon(hizli_gun=10,yavas_gun=50) | 0.336 | 19.2% | 0.99 | -26% | -13.4% | 0.37 | var | 15.2% | -26% | 75% | 18.2% | 18.8% |
| KALDI | ma_yon@kripto_btc_eth@1d | ma_yon(hizli_gun=10,yavas_gun=50) | 0.330 | 18.8% | 0.95 | -30% | -11.4% | 0.34 | var | 12.6% | -24% | 75% | 17.8% | 18.6% |
| KALDI | donchian_ls@kripto_ilk10@1h | donchian_ls(cikis_gun=10,giris_gun=55) | 0.324 | 18.4% | 0.96 | -26% | -10.0% | 0.35 | var | 11.1% | -27% | 75% | 16.6% | 19.6% |
| KALDI | tsmom@kripto_ilk10@1d | tsmom(ufuk_gun=20) | 0.288 | 16.2% | 0.79 | -40% | -8.6% | 0.17 | var | 9.3% | -40% | 62% | 10.1% | 16.1% |
| KALDI | tsmom@kripto_btc_eth@1h | tsmom(ufuk_gun=60) | 0.287 | 16.1% | 0.87 | -26% | -7.4% | 0.24 | var | 11.8% | -24% | 75% | 9.6% | 15.0% |
| KALDI | donchian_ls@kripto_ilk10@1d | donchian_ls(cikis_gun=10,giris_gun=100) | 0.278 | 15.6% | 0.93 | -38% | -7.9% | 0.31 | var | 6.4% | -35% | 75% | 13.8% | 17.7% |
| KALDI | ma_yon@kripto_ilk10@1d | ma_yon(hizli_gun=10,yavas_gun=50) | 0.226 | 12.5% | 0.65 | -38% | -9.6% | 0.09 | var | 6.6% | -45% | 62% | 10.2% | 13.2% |
| KALDI | ma_yon@kripto_ilk10@4h | ma_yon(hizli_gun=10,yavas_gun=50) | 0.214 | 11.8% | 0.63 | -38% | -8.4% | 0.08 | var | 9.2% | -40% | 75% | 9.9% | 12.4% |
| KALDI | tsmom@kripto_ilk10@4h | tsmom(ufuk_gun=20) | 0.207 | 11.4% | 0.60 | -41% | -8.1% | 0.07 | yok | 7.7% | -42% | 62% | -1.5% | 11.0% |
| KALDI | ma_yon@kripto_ilk10@1h | ma_yon(hizli_gun=10,yavas_gun=50) | 0.203 | 11.2% | 0.62 | -36% | -8.2% | 0.07 | var | 8.5% | -39% | 75% | 9.3% | 11.2% |
| KALDI | donchian_ls@kripto_ilk30@4h | donchian_ls(cikis_gun=10,giris_gun=55) | 0.195 | 10.7% | 0.59 | -47% | -8.0% | 0.05 | var | -1.8% | -53% | 62% | 7.5% | 10.0% |
| KALDI | kesitsel_momentum@abd_sektor@1d | kesitsel_momentum(geriye_gun=180,haftalik=True,mutlak=True,ust_n=5) | 0.192 | 10.5% | 0.60 | -48% | -19.1% | 0.61 | var | 11.7% | -31% | 74% | 10.1% | 11.0% |
| KALDI | kesitsel_momentum@abd_etf@1d | kesitsel_momentum(geriye_gun=180,haftalik=True,mutlak=True,ust_n=3) | 0.189 | 10.4% | 0.64 | -57% | -18.4% | 0.67 | var | 10.7% | -52% | 75% | 9.8% | 10.4% |
| KALDI | donchian_ls@kripto_ilk30@1h | donchian_ls(cikis_gun=10,giris_gun=55) | 0.177 | 9.7% | 0.54 | -49% | -7.9% | 0.04 | var | 1.5% | -46% | 62% | 6.7% | 10.2% |
| KALDI | donchian_ls@kripto_ilk30@1d | donchian_ls(cikis_gun=10,giris_gun=55) | 0.163 | 8.8% | 0.50 | -48% | -8.1% | 0.04 | var | -5.2% | -58% | 62% | 6.5% | 8.8% |
| KALDI | ma_yon@abd_etf@1d | ma_yon(hizli_gun=25,yavas_gun=200) | 0.139 | 7.5% | 0.53 | -42% | -13.7% | 0.00 | var | 4.8% | -43% | 66% | 7.6% | 8.5% |
| KALDI | tsmom@abd_etf@1d | tsmom(ufuk_gun=250) | 0.136 | 7.4% | 0.52 | -53% | -12.0% | 0.00 | var | 4.3% | -60% | 69% | 6.6% | 8.1% |
| KALDI | tsmom@kripto_ilk30@1d | tsmom(ufuk_gun=20) | 0.134 | 7.2% | 0.42 | -52% | -8.2% | 0.02 | yok | -1.6% | -54% | 62% | 1.1% | 6.7% |
| KALDI | ma_yon@kripto_ilk30@1d | ma_yon(hizli_gun=10,yavas_gun=50) | 0.126 | 6.8% | 0.41 | -44% | -8.9% | 0.02 | var | 0.4% | -47% | 62% | 4.3% | 7.4% |
| KALDI | donchian_ls@dk_emtia_metal@1d | donchian_ls(cikis_gun=10,giris_gun=55) | 0.121 | 6.5% | 0.43 | -42% | -9.7% | 0.00 | yok | 3.3% | -51% | 71% | 6.2% | 4.0% |
| KALDI | ma_yon@kripto_ilk30@1h | ma_yon(hizli_gun=10,yavas_gun=50) | 0.121 | 6.5% | 0.40 | -40% | -7.6% | 0.01 | var | -1.5% | -49% | 62% | 3.8% | 6.2% |
| KALDI | ma_yon@kripto_ilk30@4h | ma_yon(hizli_gun=10,yavas_gun=50) | 0.118 | 6.4% | 0.39 | -41% | -8.2% | 0.01 | var | -1.9% | -49% | 62% | 3.8% | 5.7% |
| KALDI | tsmom@kripto_ilk10@1h | tsmom(ufuk_gun=250) | 0.115 | 6.2% | 0.40 | -46% | -10.0% | 0.02 | yok | 1.5% | -50% | 50% | 2.2% | 5.7% |
| KALDI | donchian_ls@abd_etf@1d | donchian_ls(cikis_gun=20,giris_gun=100) | 0.092 | 4.9% | 0.37 | -49% | -11.3% | 0.00 | yok | 3.2% | -57% | 56% | 4.0% | 5.3% |
| KALDI | rsi_donus@abd_etf@1d | rsi_donus(alt=5,cikis_ma=5,n=2,trend=200) | 0.091 | 4.9% | 0.47 | -37% | -13.8% | 0.08 | var | 3.8% | -51% | 78% | 2.7% | 4.9% |
| KALDI | rsi_donus@abd_hisse_endeks@1d | rsi_donus(alt=10,cikis_ma=5,n=2,trend=200) | 0.088 | 4.7% | 0.59 | -24% | -12.6% | 0.17 | var | 4.3% | -20% | 75% | 3.6% | 3.9% |
| KALDI | kesitsel_momentum@dk_hepsi@1d | kesitsel_momentum(geriye_gun=180,haftalik=True,mutlak=True,ust_n=3) | 0.080 | 4.3% | 0.31 | -71% | -15.5% | 0.11 | yok | -6.0% | -72% | 43% | 3.7% | 5.6% |
| KALDI | donchian_ls@bist_endeks@1d | donchian_ls(cikis_gun=10,giris_gun=20) | 0.067 | 3.6% | 0.50 | -15% | -7.5% | 0.00 | yok | 2.8% | -16% | 36% | 3.4% | 2.7% |
| KALDI | kesitsel_momentum@bist_hisse@1d | kesitsel_momentum(geriye_gun=90,haftalik=True,mutlak=True,ust_n=3) | 0.058 | 3.1% | 0.26 | -63% | -13.2% | 0.03 | yok | -0.3% | -69% | 28% | 0.8% | 3.6% |
| KALDI | ay_donumu@abd_hisse_endeks@1d | ay_donumu(ilk_gun=2,son_gun=4) | 0.048 | 2.5% | 0.33 | -31% | -11.8% | 0.93 | var | 1.1% | -39% | 59% | 1.6% | 2.0% |
| KALDI | tsmom@bist_endeks@1d | tsmom(ufuk_gun=20) | 0.043 | 2.3% | 0.29 | -28% | -11.2% | 0.00 | yok | 1.6% | -34% | 32% | 1.8% | 1.3% |
| KALDI | zskor_donus@abd_hisse_endeks@1d | zskor_donus(cikis=0.5,giris=2.0,pencere=20) | 0.031 | 1.6% | 0.20 | -33% | -11.6% | 0.00 | yok | 1.3% | -32% | 62% | 0.7% | 0.8% |
| KALDI | rsi_donus@dk_endeks@1d | rsi_donus(alt=10,cikis_ma=5,n=2,trend=200) | 0.030 | 1.6% | 0.20 | -42% | -14.9% | 0.01 | yok | 0.3% | -26% | 43% | 0.9% | -0.6% |
| KALDI | ay_donumu@bist_endeks@1d | ay_donumu(ilk_gun=2,son_gun=4) | 0.026 | 1.4% | 0.29 | -13% | -6.9% | 0.85 | var | 1.2% | -19% | 44% | 0.9% | 1.1% |
| KALDI | ma_yon@bist_endeks@1d | ma_yon(hizli_gun=10,yavas_gun=100) | 0.024 | 1.3% | 0.18 | -37% | -9.4% | 0.00 | yok | 0.8% | -44% | 28% | 0.5% | 0.5% |
| KALDI | kesitsel_momentum@kripto_ilk30@1d | kesitsel_momentum(geriye_gun=90,haftalik=True,mutlak=True,ust_n=3) | 0.020 | 1.0% | 0.15 | -44% | -7.9% | 0.07 | yok | -7.0% | -56% | 75% | -0.9% | -1.3% |
| KALDI | zskor_donus@abd_etf@1d | zskor_donus(cikis=0.5,giris=2.5,pencere=20) | 0.010 | 0.5% | 0.11 | -59% | -11.1% | 0.00 | yok | 0.4% | -66% | 50% | -1.4% | 0.6% |
| KALDI | tsmom@dk_emtia_metal@1d | tsmom(ufuk_gun=20) | 0.006 | 0.3% | 0.12 | -58% | -11.8% | 0.00 | yok | 0.7% | -52% | 57% | -2.1% | -3.5% |
| KALDI | ma_yon@dk_emtia_metal@1d | ma_yon(hizli_gun=25,yavas_gun=50) | 0.001 | 0.1% | 0.11 | -58% | -12.2% | 0.00 | yok | -7.7% | -70% | 57% | -0.5% | 0.1% |
| KALDI | ma_yon@bist_hisse@1d | ma_yon(hizli_gun=10,yavas_gun=100) | 0.001 | 0.0% | 0.11 | -65% | -18.1% | 0.00 | yok | -1.3% | -71% | 24% | -1.8% | -0.7% |
| KALDI | donchian_ls@bist_hisse@1d | donchian_ls(cikis_gun=20,giris_gun=20) | -0.002 | -0.1% | 0.10 | -60% | -17.9% | 0.00 | yok | -0.3% | -63% | 28% | -2.8% | -1.6% |
| KALDI | tsmom@kripto_ilk30@4h | tsmom(ufuk_gun=120) | -0.002 | -0.1% | 0.09 | -61% | -8.7% | 0.00 | yok | -7.7% | -65% | 62% | -7.5% | -0.8% |
| KALDI | zskor_donus@dk_endeks@1d | zskor_donus(cikis=0.5,giris=2.5,pencere=20) | -0.008 | -0.4% | 0.02 | -29% | -11.7% | 0.00 | yok | -4.6% | -53% | 50% | -0.8% | 1.0% |
| KALDI | tsmom@bist_hisse@1d | tsmom(ufuk_gun=250) | -0.012 | -0.6% | 0.08 | -76% | -19.9% | 0.00 | yok | -4.1% | -82% | 20% | -2.6% | -1.1% |
| KALDI | rsi_donus@dk_fx@1d | rsi_donus(alt=10,cikis_ma=5,n=2,trend=100) | -0.018 | -1.0% | -0.09 | -32% | -6.0% | 0.00 | yok | -0.2% | -25% | 29% | -2.8% | -3.9% |
| KALDI | ay_donumu@dk_endeks@1d | ay_donumu(ilk_gun=2,son_gun=4) | -0.023 | -1.2% | -0.06 | -36% | -9.1% | 0.06 | yok | -2.6% | -41% | 57% | -1.6% | -3.2% |
| KALDI | zskor_donus@dk_fx@1d | zskor_donus(cikis=0.5,giris=2.5,pencere=50) | -0.034 | -1.7% | -0.11 | -44% | -11.5% | 0.00 | yok | -3.6% | -54% | 50% | -2.0% | -1.9% |
| KALDI | tsmom@kripto_ilk30@1h | tsmom(ufuk_gun=250) | -0.095 | -4.8% | -0.16 | -58% | -8.2% | 0.00 | yok | -8.6% | -66% | 50% | -12.2% | -5.1% |
| KALDI | ma_yon@dk_hepsi@1d | ma_yon(hizli_gun=25,yavas_gun=200) | -0.097 | -4.9% | -0.27 | -72% | -9.1% | 0.00 | yok | -9.3% | -74% | 29% | -5.1% | -5.7% |
| KALDI | rsi_donus@bist_hisse@1d | rsi_donus(alt=5,cikis_ma=5,n=2,trend=100) | -0.100 | -5.1% | -0.29 | -77% | -13.1% | 0.00 | yok | -6.7% | -83% | 20% | -8.2% | -4.8% |
| KALDI | tsmom@dk_endeks@1d | tsmom(ufuk_gun=120) | -0.116 | -5.9% | -0.19 | -73% | -11.3% | 0.00 | yok | -15.5% | -89% | 36% | -6.7% | -8.1% |
| KALDI | ma_yon@dk_endeks@1d | ma_yon(hizli_gun=25,yavas_gun=200) | -0.124 | -6.3% | -0.21 | -77% | -15.4% | 0.00 | yok | -9.6% | -81% | 36% | -6.3% | -7.6% |
| KALDI | ma_yon@dk_fx@1d | ma_yon(hizli_gun=25,yavas_gun=200) | -0.124 | -6.3% | -0.41 | -70% | -7.4% | 0.00 | yok | -7.8% | -68% | 36% | -6.5% | -6.6% |
| KALDI | donchian_ls@dk_hepsi@1d | donchian_ls(cikis_gun=10,giris_gun=100) | -0.128 | -6.4% | -0.28 | -76% | -9.3% | 0.00 | yok | -9.7% | -80% | 21% | -7.5% | -6.3% |
| KALDI | donchian_ls@dk_endeks@1d | donchian_ls(cikis_gun=20,giris_gun=100) | -0.128 | -6.4% | -0.33 | -71% | -9.4% | 0.00 | yok | -8.7% | -76% | 29% | -6.8% | -6.6% |
| KALDI | donchian_ls@dk_fx@1d | donchian_ls(cikis_gun=10,giris_gun=100) | -0.131 | -6.6% | -0.53 | -69% | -9.3% | 0.00 | yok | -7.6% | -69% | 29% | -6.9% | -4.8% |
| KALDI | tsmom@dk_fx@1d | tsmom(ufuk_gun=250) | -0.131 | -6.6% | -0.45 | -72% | -8.0% | 0.00 | yok | -10.5% | -77% | 29% | -7.4% | -7.8% |
| KALDI | zskor_donus@bist_hisse@1d | zskor_donus(cikis=0.5,giris=2.5,pencere=20) | -0.146 | -7.3% | -0.44 | -90% | -18.0% | 0.00 | yok | -10.3% | -93% | 16% | -9.4% | -5.5% |
| KALDI | tsmom@dk_hepsi@1d | tsmom(ufuk_gun=250) | -0.170 | -8.5% | -0.56 | -83% | -8.3% | 0.00 | yok | -12.7% | -84% | 21% | -9.1% | -7.1% |

Carry (dalga 1b): KALDI; yıllık %3,2, Sharpe 1,78, DD −%1, OOS yıllık +%0,2, DSR 0,00 (yılların %60'ı pozitif değil).
