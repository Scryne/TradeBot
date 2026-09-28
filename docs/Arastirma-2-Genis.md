---
proje: TradeBot
created: 2026-09-28
type: arastirma
---
# Araştırma 2 — Dışarıya bakış: popüler botlar, piyasalar, gerçek getiri kaynakları

Scryne'ın sorusu (2026-09-28): "Proje boşluğa düşmüş gibi, sürekli tekrarlanıyor. İnternette çok kullanılan, güvenilen
trade botları var; onları araştırıp bir şey yakalayamaz mıyız? Biz yalnız BTC'ye bakıyoruz; meme coin, altın, EURUSD
gibi çok şey var."

Bu belge `Arastirma.md`'yi tekrar etmez (strateji aileleri, mevzuat, mimari orada). Burada üç şey var: dış dünyada
gerçekten kullanılan botların kanıtı, piyasa piyasa neyin işe yaradığı ve bugün yapılan ön ölçümler.

## 1. Neden "tekrarlanıyor" hissi var — ve neden bu bir arıza değil

Bugüne kadar sınanan (hepsi deneme defterinde, 800+ deneme): kripto trend (BTC/ETH ✅, geniş sepet ❌), kripto kesitsel
momentum ❌, funding carry ❌ (2022'den beri eşik altı), ortalamaya dönüş aileleri ❌, ABD ETF trend ve dönüş ❌, BIST
hisse ❌, FX/altın/endeks CFD trendi ❌, VİOP BIST30 trend ❌, TL taşıma ❌, altın M15 gün içi (EA) ❌, çok varlıklı vadeli
trend ❌. Yani BTC dışında da çok bakıldı; yalnız BTC/ETH trendi kapıdan geçti.

Dış kanıt bu sonucun sistemimize özgü olmadığını gösteriyor:

- **Herkese açık bot stratejileri:** Bağımsız bir denetim 895 herkese açık Freqtrade stratejisini yazarın hiç görmediği
  yıllarda, gerçekçi maliyetle yeniden koştu: 895 → 158 pozitif → 72 sapma kontrolünden geçen → **2 hayatta kalan; ikisi
  de al-tut'u geçemedi** (en iyisi +%107, al-tut +%346). Stratejilerin %65'i birkaç orijinalin test edilmeden
  kopyalanmışı. ([strategy-audit](https://github.com/Apex-prim/strategy-audit))
- Başka bir topluluk testinde 42 herkese açık Freqtrade stratejisinin 33'ü 8 yıllık BTC verisinde para kaybetti.
- **Profesyonel trend fonları:** SG Trend endeksi 2023'te −%3,3, 2024'te yatay, 2025 başında son 12 ayda −%12,5.
  ([SG CTA](https://content.sgmarkets.com/CTA_UPDATE_KEEPING_UP_WITH_THE_TRENDFOLLOWERS_2025),
  [The Full FX](https://thefullfx.com/ctas-tough-start-to-2025-continues/)) Dalga 3'ün sonucu bu dönemle uyumlu.

Sonuç: sistemimiz yapması gerekeni yapıyor, aşırı uydurulmuş fikirleri eliyor. Sorun süreçte değil hedefte: hep
**fiyat deseni** (gösterge, kırılım, dönüş) aradık. Fiyat desenleri herkese açık, kolay kopyalanıyor ve maliyete gidiyor.
Kalıcı getiri başka yerden gelir (bölüm 3).

## 2. Popüler botlar gerçekte ne yapıyor

| Platform / tür | Ne yapar | Kanıt ve gerçek |
| --- | --- | --- |
| 3Commas, Cryptohopper, Bitsgap, Gunbot | DCA, grid, sinyal takibi, "akıllı" emirler | Platform kalitesi puanlanıyor, kârlılık değil. Toplanan kullanıcı verisinde medyan getiri ~%12/yıl (aynı dönemde BTC tutmanın çok altında). ([Koinly](https://koinly.io/blog/best-crypto-trading-bots/), [BotVerdict](https://botverdict.com/articles/are-crypto-trading-bots-profitable-in-2026-an-honest-analysis-of-real-returns/)) |
| Pionex (16 hazır bot) | Grid, DCA, "sonsuz grid" | Yatay piyasada %5–15/yıl; yükselişte al-tut'un gerisinde; sert düşüşte grid malı biriktirir. Grid = gizli **oynaklık satışı** (dar aralıkta küçük kazanç, aralık kırılınca büyük kayıp). ([Pionex](https://www.pionex.com/blog/grid-bot/)) |
| DCA botları | Düştükçe ekleme | Ortalama maliyet düşer ama kayıpta pozisyon büyür: **martingale türü, kural 6 yasaklar**. |
| Freqtrade, Jesse, OctoBot | Açık kaynak çatı; stratejiyi kullanıcı yazar | Çatılar sağlam, stratejiler değil (bölüm 1'deki denetim). |
| Hummingbot | Piyasa yapıcılığı, arbitraj | Kârlılık karışık; ücret iadesi (rebate) ve düşük ücret kademesi şart. Borsalar ve projeler piyasa yapıcılığına yılda ~3 milyar $ ödüyor, ama bu para ölçeği olan yapıcılara gidiyor. ([Hummingbot](https://hummingbot.org/blog/does-community-based-market-making-work/)) |
| MQL5 sinyalleri, kopya işlem | Başkasının hesabını kopyalama | Sinyal sağlayıcıların çoğu eğriyi güzel göstermek için lot oynatıyor; aboneler eğriye ve abone sayısına bakıyor. Bağımsız kalıcılık istatistiği yayımlanmıyor. ([MQL5](https://www.mql5.com/en/articles/1838)) |
| Meme coin "sniper" botları (pump.fun) | Yeni tokeni ilk saniyelerde alma | Token'ların ~%1'i büyük borsaya "mezun" oluyor, çoğu saatler içinde ölüyor, meme işlemlerinin %70–85'i para kaybediyor; oyun hız (MEV) ve içeriden bilgi oyunu. ([CoinMarketCap](https://coinmarketcap.com/academy/article/meme-coin-recap-2025-pumpfun-trump-doge-wall-street)) |
| Satılan EA'lar (ör. altın EA) | Çok strateji + risk katmanları | Bizim ölçümümüz: EA yapısının profesyonel karşılığı maliyet sonrası zararda (`turnuva/Altin-M15.md`). |

Ortak desen: popüler botların çoğu ya **al-tut'un gerisinde kalan** bir otomasyon ya da **kuyruk riskini gizleyen** bir
yapı (grid, DCA). "Çok kazanan bot" iddialarının neredeyse hepsi hayatta kalan yanlılığı ve kaldıraçtır.

## 3. Getiri nereden gelir — küçük bir oyuncunun oynayabileceği alanlar

| Kaynak | Örnek | Neden kalıcı | Bizim için |
| --- | --- | --- | --- |
| **Risk primi** (başkasının istemediği riski taşımak) | Trend/momentum, taşıma (carry), **oynaklık satışı (VRP)**, likidite sağlama | Birisi sigorta ya da hız için bedel ödüyor | Trend: BTC/ETH'de çalışıyor. **VRP: bugün ölçüldü, güçlü (bölüm 5.4)** |
| **Yapısal akış** (zorunlu alıcı/satıcı) | Endeks dengelemeleri, **token kilit açılımları**, borsa listelemeleri, ay sonu fix | Karşı taraf zaman ya da kural gereği işlem yapmak zorunda | Kilit açılımı güçlü kanıtlı (bölüm 4.1); listeleme etkisi artık önceden fiyatlanıyor |
| Hız / altyapı | HFT, MEV, sniping | Teknoloji yarışı | Bizim için değil |
| Bilgi | Haberi daha hızlı/doğru anlamak | Metin okumak pahalı | Jev bu işi yapıyor ama kural 8: yalnız riski azaltır (veto). Bu doğru bir kısıt |

Fiyat deseni (gösterge, formasyon, seans kırılımı) bu tabloda yok: herkes aynı veriye bakıyor.

## 4. Piyasa piyasa

### 4.1 Kripto
- **BTC/ETH trend:** çalışıyor, paper'da (5 kol).
- **Oynaklık primi (opsiyon satışı):** bölüm 5.4. Deribit ve Binance Options'ta; tanımlı riskli yapılarla (spread,
  iron condor) kuyruk sınırlanabilir.
- **Token kilit açılımı:** Keyrock 16.000+ açılımı inceledi: ~%90'ı fiyatı düşürüyor. Düşüş açılımdan ~30 gün önce
  başlıyor, son hafta hızlanıyor, sonra ~14 günde nötrleşiyor. Dolaşımın %5'inden büyük açılımlarda medyan −%8–15;
  ekip açılımlarında −%25 ve üstü. ([Keyrock](https://keyrock.com/from-locked-to-liquidity-what-16000-token-unlocks-teach-us/))
  Kural koddan (açılım takvimi), Jev'den değil: kural 8'e uygun. Gerekenler: kısa pozisyon (perp), açılım takvimi verisi
  (DefiLlama artık ücretli; Tokenomist/CryptoRank ücretli).
- **Listeleme etkisi:** Eski çalışmalarda Binance listeleme gününde +%17,5 anormal getiri; 2026 analizleri etkinin
  artık duyurudan önce fiyatlandığını söylüyor. Listelenen coin henüz Binance'te olmadığı için başka borsada işlem
  gerekir. Operasyonel olarak zor, öncelik düşük. ([Blockchain Research Lab](https://www.blockchainresearchlab.org/wp-content/uploads/2019/10/Exploring-Market-Reactions-to-Exchange-Listings-of-Cryptocurrencies-BRL-working-paper3.pdf), [The Tie](https://www.thetie.io/insights/what-does-an-exchange-listing-actually-deliver-in-2026))
- **Funding uç değerleri:** Aşırı pozitif funding kalabalık longu gösteriyor; ama tek başına sinyal olarak test edildiğinde
  beklendiği gibi çalışmıyor. ([Backtesting Arena](https://tradingstrategies.work/blog/funding-rate-signal-btc-backtest))
- **Meme coin'ler:** Binance'te listelenmiş olanlar (DOGE, SHIB, PEPE, FLOKI, BONK, WIF…) trendle sınanabilir, ucuz.
  Önsel zayıf: bizim ölçümümüzde kripto sepeti genişledikçe trend kötüleşti. Sniper/pump.fun oyunu bizim için değil.
- **Saat etkisi:** bölüm 5.2.

### 4.2 Altın
Trend (CFD) finansmanda boğuldu, gün içi EA yapısı zararda, vadeli trend (Dalga 3) metal sınıfında Sharpe 0,25 ile −%58
düşüş. Bilinen "Asya'da yükselir, Batı'da düşer" deseni ön ölçümde tutarlı değil (bölüm 5.1).

### 4.3 EURUSD ve majör dövizler
Dalga 3'te döviz trendi negatif (Sharpe −0,10); majör döviz trendinin 2012 sonrası zayıflığı literatürde de var. Ay sonu
Londra fix akışı akademik olarak belgeli (Melvin & Prins) ama ön ölçümde anlamsız (bölüm 5.3).

### 4.4 Endeksler
Gece kayması (overnight drift) ve FOMC öncesi kayma belgeli; maliyet sonrası Sharpe'ları belirgin düşüyor.
([NY Fed](https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr917.pdf), [Quantseeker](https://www.quantseeker.com/p/trading-the-fed-the-pre-fomc-drift))
Endeks trendi Dalga 3'te 0,47 (büyük olasılıkla hisse yükselişinin uzun tarafı).

### 4.5 Türkiye piyasaları
VİOP BIST30 trend ve TL taşıma kaldı; BIST hisse verisi yanlı. VİOP opsiyonları var ama likiditesi düşük.

## 5. Ön ölçümler (2026-09-28, betimsel, yalnız eski yıllar)

Parametre araması yok. Sonraki yıllar kör: gerçek sınama ön kayıtla oradan yapılır.

### 5.1 Altın — Asya saatleri (NCM GOLD saatlik, 2018–2021)
Saat başına ortalamalarda tek belirgin nokta 21:00 UTC (+1,8 bps, t 3,0): kurumun günlük kapanış/devir anı, spread
etkisi olabilir. Asya (22–07 UTC) ile Londra+NY (07–21 UTC) yıllara göre tutarsız: 2021'de Asya +%11 / Batı −%19, 2019'da
Asya +%1 / Batı +%11. **Kalıcı bir Asya etkisi görünmüyor.**

### 5.2 BTC — saat ve gün (Binance saatlik, 2018–2021)
21:00 UTC saati +7 bps (t 3,1), literatürdeki ABD kapanış sonrası etkiyle uyumlu; 02–03 UTC negatif (t −2,1/−2,7). Ama
Binance spot'ta bir al-sat ~26 bps: günlük tek saatlik işlemde **maliyet etkiyi siliyor**. "Pazartesi Asya açılışı" zayıf
(+12'ye karşı +8 bps/gün).

### 5.3 EURUSD — ay sonu fix (Dukascopy saatlik, 2010–2017)
Son iş günü 14–16 UTC getirisi, o ayki ABD–Avrupa hisse farkıyla: 51 ay, isabet %53, t +1,0. **Anlamsız.**

### 5.4 BTC opsiyon oynaklık primi (Deribit DVOL, 2021-04 → 2023)
Her gün piyasanın beklediği 30 günlük oynaklık (DVOL) ile sonraki 30 günde gerçekleşen oynaklık:

- 1.006 gün; ortalama örtük 69,9, gerçekleşen 58,3.
- **Örtük − gerçekleşen: ortalama +11,7 oynaklık puanı, medyan +12,4, günlerin %74'ünde pozitif, her yıl pozitif**
  (2021 +14, 2022 +8, 2023 +5 puan varyans-swap satıcısı getirisi).
- En kötü: Nisan–Mayıs 2021 çöküşünden önce başlayan pencereler (−52 puan). Kuyruk riski büyük ve gerçek.

Akademik çalışmalar da BTC varyans primini pozitif ve kalıcı buluyor.
([SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6771170), [Deribit Insights](https://insights.deribit.com/industry/bitcoin-options-finding-edge-in-four-years-of-volatility-regimes/))

**Neden önemli:** Trend uzun oynaklık gibi davranır (çöküşlerde kazanır); opsiyon satışı kısa oynaklıktır (çöküşlerde
kaybeder). İkisi birlikte, birbirinin kötü dönemini kısmen dengeleyen iki farklı getiri kaynağıdır. Bu, BTC/ETH trendine
eklenebilecek ilk gerçekten farklı kaynak.

## 6. Öneri

Fiyat deseni aramayı bırakıp **farklı getiri kaynakları** eklemek:

1. **Dalga 4 — BTC/ETH opsiyon oynaklık primi (öncelik 1).** Tanımlı riskli yapı (put spread / iron condor), küçük
   boyut, haftalık/aylık vade. Önce ön kayıtlı backtest: DVOL + çarpıklık varsayımıyla (aleyhte) fiyatlama, 2024+ kör.
   Deribit'in ücretsiz testnet'i gerçek emir akışıyla paper verir. Trend kollarıyla korelasyon ve birleşik portföy
   raporlanır.
2. **Dalga 5 — token kilit açılımı kısa (öncelik 2).** Açılımdan 30 gün önce perp kısa, açılımdan sonra kapat; kural
   koddan. Açılım takvimi verisi ücretli; önce ücretsiz kaynak aranır, yoksa bütçe kararı.
3. **Hızlı kontrol — meme sepeti trendi.** Mevcut hattı kullanır, maliyeti düşük; önsel zayıf, bir koşuda kapanır ya
   da açılır.
4. Paper'daki BTC/ETH trendi aynen sürer.

## 7. Scryne'ın kararları

1. **Türev kullanımı:** Opsiyon (Deribit / Binance Options) ve perp (Binance global). Paper'da sorun yok; gerçek parada
   Türkiye'deki lisanslı platformlarda kaldıraç yasak, yurt dışı borsalar Türkiye'ye yönelik tanıtım yapmıyorsa
   erişilebilir. ([Haberler.com](https://www.haberler.com/yazarlar/av-ahmet-karaca/turkiyede-kripto-varliklarda-kaldiracli-islemler-yasak-mi-av-ahmet-karaca-6595/)) Kaldıraç tavanı (3x, kural 6) opsiyonlarda delta ve azami kayıp üzerinden uygulanır.
2. **Veri bütçesi:** Kilit açılım takvimi (aylık ücret) ve gerekirse tarihsel opsiyon fiyatları (Tardis.dev vb.).
3. **Sıra:** önerilen 1 → 3 → 2.

## Kaynaklar

- Freqtrade denetimi: https://github.com/Apex-prim/strategy-audit
- Freqtrade backtest/canlı farkı: https://github.com/freqtrade/freqtrade/issues/5222
- Bot karşılaştırmaları: https://koinly.io/blog/best-crypto-trading-bots/ · https://botverdict.com/articles/are-crypto-trading-bots-profitable-in-2026-an-honest-analysis-of-real-returns/
- Pionex grid: https://www.pionex.com/blog/grid-bot/
- Hummingbot: https://hummingbot.org/blog/does-community-based-market-making-work/
- MQL5 sinyal seçimi: https://www.mql5.com/en/articles/1838
- Meme coin 2025: https://coinmarketcap.com/academy/article/meme-coin-recap-2025-pumpfun-trump-doge-wall-street
- Token kilit açılımı: https://keyrock.com/from-locked-to-liquidity-what-16000-token-unlocks-teach-us/
- Listeleme etkisi: https://www.blockchainresearchlab.org/wp-content/uploads/2019/10/Exploring-Market-Reactions-to-Exchange-Listings-of-Cryptocurrencies-BRL-working-paper3.pdf · https://www.thetie.io/insights/what-does-an-exchange-listing-actually-deliver-in-2026
- BTC gün içi mevsimsellik: https://quantpedia.com/are-there-seasonal-intraday-or-overnight-anomalies-in-bitcoin/ · https://concretumgroup.com/seasonality-in-bitcoin-intraday-trend-trading/
- Altın Asya/Batı deseni: https://www.fxstreet.com/analysis/a-strange-dichotomy-gold-up-on-the-year-in-asian-markets-down-big-in-the-west-202607131959
- Ay sonu fix: https://www.ecb.europa.eu/events/pdf/conferences/131216/Third_FX_Workshop_MELVIN_PRINS_Equity%20hedging%20and%20exchange%20rates%20Nov%202013.pdf
- FOMC öncesi ve gece kayması: https://www.quantseeker.com/p/trading-the-fed-the-pre-fomc-drift · https://www.newyorkfed.org/medialibrary/media/research/staff_reports/sr917.pdf
- SG CTA: https://content.sgmarkets.com/CTA_UPDATE_KEEPING_UP_WITH_THE_TRENDFOLLOWERS_2025 · https://thefullfx.com/ctas-tough-start-to-2025-continues/
- BTC opsiyon primi: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=6771170 · https://insights.deribit.com/industry/bitcoin-options-finding-edge-in-four-years-of-volatility-regimes/
- Funding sinyali testi: https://tradingstrategies.work/blog/funding-rate-signal-btc-backtest
- Türkiye kaldıraç düzenlemesi: https://www.haberler.com/yazarlar/av-ahmet-karaca/turkiyede-kripto-varliklarda-kaldiracli-islemler-yasak-mi-av-ahmet-karaca-6595/
