---
proje: TradeBot
created: 2026-09-28
type: turnuva-plani
durum: ön kayıt (koşudan önce commit edildi)
---
# Turnuva — Dalga 3: çok varlıklı vadeli trend (ön kayıt)

Dosya: `config/turnuva/dalga3.yaml`. Araştırma planının 2. sırası (`Arastirma-Plani.md`). Kurallar dalga 1–2 ile aynı;
çıta 0 (seriler vadeli fazla getirisi, Dalga-1 ek 4).

## Neden

Paper'daki beş kolun hepsi aynı fikir: BTC/ETH trendi. İkinci, bağımsız bir getiri kaynağı gerekiyor. Yönetilen
vadeli fonların klasik kaynağı çok varlıklı zaman serisi trendidir; kriz dönemlerinde (2008, 2022) pozitif, hisse ve
kriptoyla korelasyonu düşük olması beklenir.

**Önsel (dürüst):** Dalga 2'deki ABD ETF sepeti (endeks, sektör, tahvil, altın, gümüş, petrol ETF'leri) trendde
Sharpe 0,29–0,51 ile kaldı. Dalga 3'ün farkları: (1) altı majör döviz eklenir, (2) kısa pozisyon taşımayı kazanır
(ETF'de açığa satış ödünç maliyeti öder), (3) endeks tarafı gerçek vadeli fazla getirisidir. Buna karşılık trendin
tarihsel olarak en güçlü iki piyasası, tahvil ve enerji, bu dalgada yok (aşağıda). Sıfır hipotezinin ayakta kalması
şaşırtıcı olmaz.

## Seriler (`veri/vadeli.py`, `tradebot veri vadeli`)

| Kimlik | Kaynak | Yöntem |
| --- | --- | --- |
| `VADELI:ES`, `NQ`, `YM` | NCM `ES!`, `NQ!`, `YM!` (ön ay, ayarsız) + Dukascopy spot endeks | CME geçiş penceresi (3. Cuma −3 … +2 iş günü) spot getirisiyle değiştirilir |
| `VADELI:XAU`, `XAG` | Dukascopy spot | spot getiri − ABD kısa faizi (kira oranı 0) |
| `VADELI:EURUSD`, `GBPUSD`, `USDJPY`, `AUDUSD`, `USDCAD`, `USDCHF` | Dukascopy spot | spot getiri + (taban faiz − kote faiz) |

- Faiz: OECD aylık 3 aylık bankalar arası (IR3TIB), **iki ay gecikmeli** (o gün kesin yayımlanmış değer, kural 9).
  FRED bu ağdan erişilemiyor.
- Geçiş ayarı ölçüldü (2026-09-28): ES'de 59 geçiş, sıçramaların toplamı 14,7 yılda %13,9 (yılda ~%0,9 ≈ dönemin
  faiz − temettü farkı). Ham seri +%496, ayarlı +%419.
- Dönem: vadeli serilerde 2012 (ES) / 2013 (NQ, YM) → 2025-12-31; döviz ve metal 2010 → 2025-12-31. Dukascopy'nin
  günlük dosyaları yıllık yayımlanıyor, 2026 yok: endeks serileri spotun kapsadığı aralığa kırpıldı (ayıklanmamış
  geçiş kalmaz).
- **Kör bekletme:** 2026-01 → 2026-09 hiçbir koşuda kullanılmadı. Dalga sonucu yazıldıktan sonra, seçilen varyant bu
  dönemde bir kez sınanır (seçim değişmez; yalnız rapor).

**Yok:** tahvil ve enerji. İkisinde de uzun geçmiş yalnız ayarsız ön ay CFD'sinde var (Dukascopy `LIGHTCMDUSD`,
NCM `CL!`; oran 1,000: aynı kaynak) ve geçişi ayıklayacak bağımsız bir spot referansı yok. Ayarsız seriyle koşmak
sahte getiriyi kâr sayardı (Dalga 3 veri notu).

## Aileler ve ızgara (16 deneme, dalga 2 ile aynı)

`tsmom` (ufuk 20/60/120/250 gün), `ma_yon` (hızlı 10/25 × yavaş 50/100/200), `donchian_ls` (giriş 20/55/100 × çıkış
10/20). Tek grup `vadeli_sepet`, iki yönlü, günlük, oynaklık hedefi %20 (90 günlük pencere), kaldıraç tavanı 3x, bant
0,25, frenler açık.

## Maliyet (aleyhte, koşudan önce sabit)

Uygulama NCM'de olur: endeks için vadeli CFD'si (ES6Z…), metal ve döviz için spot CFD (swap ≈ faiz farkı + kurum payı).

| Sınıf | Komisyon | Yarım spread | Kayma | Yıllık finansman (kurum payı) |
| --- | --- | --- | --- | --- |
| endeks | 0,5 bps | 0,5 bps | 1 bps | %0,5 (devir) |
| döviz | 0 | 1 bps | 1 bps | %1 |
| metal | 0 | 1 bps | 1 bps | %1,5 (GOLD swap'ından: uzun −%5,1, kısa +%1,9; adil ±%4,3) |

Stres: maliyet 2 kat, bir bar gecikme.

## Karar ölçütü

Dalga 1–2 ile aynı: A için DSR ≥ 0,95 + walk-forward OOS + stres; B (sermayesiz paper gözlemi) için DSR şartı yok.
B çıkarsa: MT5 canlı bar akışı paper düğümüne bağlanır (Faz 8'in kalan işi), kol paper'a girer.

## Raporlanacak (kapı değil, bilgi)

- En iyi varyantın paper kollarıyla (BTC/ETH trend backtest'i) haftalık korelasyonu ve 50/50 karışımın Sharpe'ı.
- Sınıf kırılımı: endeks, metal, döviz ayrı katkı.
- 2022 (faiz şoku) ve 2020 Mart ayrı.
