---
proje: TradeBot
belge: Arastirma
surum: 1
tarih: 2026-09-24
durum: taslak (planlama girdisi)
---

# TradeBot — Kapsamlı Araştırma

Bu belge planlamadan önce trade bot alanında bilinmesi gerekenleri toplar: neyin işe yaradığı, neyin
yaramadığı, Türkiye'de nelerin yasal ve pratik olduğu, bir botun parçaları, nasıl doğrulandığı ve Jev'in
(TypeSafe) nereye oturduğu. Kaynaklar sonda listelenmiştir. **"Doğrulanmalı"** işareti olan bilgiler ikincil
kaynaktandır; gerçek parayla ilgili bir karardan önce birincil kaynaktan teyit edilir.

> Bu belge yatırım tavsiyesi değildir. Burada anlatılan her strateji para kaybettirebilir.

---

## 0. Yönetici özeti — 12 bulgu

1. **Maliyet, stratejiden önce gelir.** Spot kriptoda gidiş-dönüş maliyet (iki taraf ücret + spread + kayma)
   ~%0,15–0,30'dur. Günde 5 gidiş-dönüş yapan bir bot, daha tek bir doğru tahmin yapmadan yılda sermayesinin
   birkaç katı kadar maliyet öder. Sık işlem, ancak işlem başına brüt üstünlük bu eşiği güvenle aştığında
   anlamlıdır ve perakende yatırımcı için bu nadirdir.
2. **En güçlü akademik kanıt trend/zaman serisi momentumundadır** (günlük–haftalık ufuk, oynaklığa göre
   boyutlanmış). Kriptoda çok sayıda çalışma bunu destekler. Bu kanıt maliyetten sonra da ayakta kalır, çünkü
   işlem sıklığı düşüktür.
3. **Oynaklık hedefleme (volatility targeting) tek başına en değerli risk aracıdır.** Pozisyon boyutunu
   oynaklığın tersine göre ayarlamak düşüşleri yarıya indirebilir ve getiriyi az etkiler.
4. **Funding carry ve basis işlemi rejime bağlıdır.** Kaldıraçlı boğa piyasalarında yıllık çift haneli getiri
   verir. 2025–26'da funding oranları normalleşince getiri sıkıştı ve bazı kurallar hiç tetiklenmedi.
5. **Grid botları yatay piyasada kazanır, trendde kaybeder.** Düşüşte "düşen bıçağı" toplar. Bu bir üstünlük
   değil, oynaklık satmaktır.
6. **Market making ve arbitraj perakende için zordur.** Düşük ücret kademesi, düşük gecikme ve ters seçilime
   (adverse selection) karşı koruma ister. Bu alanda kurumsal oyunculara karşı rekabet edilir.
7. **Perakende botların çoğu para kaybeder.** Sektör tahminlerine göre %70–80'i 12 ayda zarardadır. "AI bot"
   diye satılanların büyük kısmı kural tabanlı betiklerdir. Kazananları ayıran şey strateji fikri değil,
   **doğrulama disiplini ve risk yönetimidir.**
8. **Backtest aşırı uyumu (overfitting) bir numaralı tuzaktır.** Parametre ne kadar çok denenirse "kazanan"ın
   şans eseri olma olasılığı o kadar artar. Deflated Sharpe ve PBO gibi yöntemler bunu ölçer.
9. **Türkiye (2026):** 7518 sayılı Kanun ile yerli platformlar SPK lisansına tabidir ve **kaldıraç, türev,
   açığa satış yasaktır.** Yurt dışı platformu kişinin kendi inisiyatifiyle kullanması tebliğ kapsamı
   dışındadır. Kaldıraçlı FX/CFD lisanslı kurumda en az 50.000 TL teminat ve en fazla 1:10 kaldıraç ister.
10. **Vergi:** %10 stopaj ve on binde 3 işlem vergisi teklifi 27.03.2026'da geri çekildi. Rejim beyan
    esaslıdır. Ayrıntılar mali müşavirle doğrulanmalıdır.
11. **Jev ile yapılmış açık kaynak trade botlarının hiçbiri kâr/zarar ya da backtest yayınlamadı.** Hepsinde
    ortak kalıp aynıdır: *"Jev yargılar, kod uygular."* Jev'in kanıtlı gücü metin yargısındadır: haber ve duyuru
    sınıflandırma, risk vetosu, doğal dil komutu. Piyasa yönünde güçlü değildir (global TypeSafe notu).
12. **"Maksimum kazanç stratejisi: kaldıraçlı trend/kırılım botu" iddiası kısmen doğru, büyük ölçüde
    tehlikeli.** Trend/kırılım gerçek bir etkidir. Ancak kendi sınamamızda (BTC/ETH günlük Donchian,
    2017–2026, maliyet + funding dahil) **5x ve üstü kaldıraç her yapılandırmada hesabı sıfırladı.** 2–3x,
    son değeri bazen artırdı ama düşüşü −%82 ile −%99 arasına çıkardı. Büyümeyi maksimize eden kaldıraç, en
    iyimser varsayımla bile ~2x'tir (Kelly) ve bu değer geriye dönük bakışla bulunur (§5.11).
13. **TensorTrade** (RL tabanlı trading kütüphanesi) araştırma oyuncağıdır, canlı bot altyapısı değildir.
    Kendi README'si, %0,1 komisyonda PPO ajanının al-tut'un gerisinde kaldığını ve komisyonun tahmin kârını
    aştığını yazıyor. Canlı işlem desteği yok (§8.5).
14. **Önerilen genel yön:** önce düşük frekanslı, kanıtı güçlü bir çekirdek (trend + oynaklık hedefi, spot,
    kaldıraçsız) ve sağlam bir altyapı (backtest = canlı kod, paper → küçük gerçek para). Jev, çekirdeğin
    etrafında **risk vetosu ve olay katmanı** olarak girer. Sık işlem ve kaldıraç ancak kendi verimizde ölçülüp
    geçerse açılır.

---

## 1. Trade bot nedir — anatomi

Bir trade bot, önceden tanımlı kurallarla piyasa verisinden emir üreten ve bu emirleri insan müdahalesi
olmadan borsaya ileten yazılımdır. Hangi strateji kullanılırsa kullanılsın parçaları aynıdır:

```
 veri ──► özellik/sinyal ──► hedef pozisyon ──► risk motoru ──► emir yürütme ──► borsa
   ▲                                               │                 │
   │                                               ▼                 ▼
   └──────────── durum / muhasebe / mutabakat ◄──── izleme & alarm ◄──┘
```

| Katman | Görevi | Tipik hata |
| --- | --- | --- |
| **Veri** | Mum (OHLCV), emir defteri, funding, haber; tarihsel + canlı | Eksik bar, saat dilimi karışıklığı, sonradan düzeltilmiş veri |
| **Sinyal** | Veriden "ne kadar pozisyon istiyorum" üretir | Geleceği görme (look-ahead), aşırı uyum |
| **Risk motoru** | Boyut, kaldıraç tavanı, günlük kayıp limiti, kill switch | Sinyalin risk motorunu atlayabilmesi |
| **Yürütme** | Emir tipi (limit/market), parçalama, yeniden deneme | Çift emir, kısmi dolumun unutulması |
| **Muhasebe/mutabakat** | Botun "sandığı" pozisyon = borsadaki gerçek pozisyon mu? | Sessiz sapma: bot yanlış pozisyonla aylarca çalışır |
| **İzleme** | Sağlık, PnL, alarm (Telegram vb.), pano | Bot durdu ama kimse fark etmedi |

**Temel ilke:** backtest'te çalışan karar kodu ile canlıda çalışan karar kodu **aynı fonksiyon** olmalıdır. İki
ayrı implementasyon zamanla ayrışır. Canlı sonuç backtest'ten sapınca sebebin kod mu, piyasa mı olduğu
anlaşılamaz.

### Bot türleri

| Tür | Mantık | Kazanç kaynağı | Perakende için |
| --- | --- | --- | --- |
| Trend/momentum | Yükselen alınır, düşen satılır/boşaltılır | Trendlerin sürmesi (davranışsal) | ✅ En iyi kanıt |
| Ortalamaya dönüş | Aşırı sapma tersine oynanır | Kısa vadeli aşırı tepki | ⚠️ Brüt var, maliyet yiyor |
| Grid | Aralıkta kademeli al-sat | Yatay piyasada oynaklık | ⚠️ Trendde büyük kayıp |
| DCA | Düzenli alım | Üstünlük yok, disiplin | ✅ Basit, alfa değil |
| Carry (funding/basis) | Spot al + perp sat | Kaldıraç talebinin primi | ⚠️ Rejime bağlı, türev gerekir |
| Market making | İki taraflı kote | Spread | ❌ Ücret/gecikme/ters seçilim |
| Arbitraj | Borsalar/araçlar arası fark | Fiyat verimsizliği | ❌ Hız yarışı |
| Olay/haber | Duyuru, listeleme, hack | Bilgiye hızlı tepki | ⚠️ Veri ve hız ister; Jev burada |
| ML tahmin | Model fiyat yönü tahmin eder | İddia edilen örüntü | ⚠️ Aşırı uyuma en açık tür |

---

## 2. Piyasa seçimi (Türkiye'den erişim dahil)

| Piyasa | Erişim | Kaldıraç/short | Ücret | Veri | Değerlendirme |
| --- | --- | --- | --- | --- | --- |
| **Kripto spot — yurt dışı (Binance.com vb.)** | Kendi inisiyatifle mümkün; TRY çiftleri 13.11.2025'ten beri yalnız Binance TR üzerinden | Spot'ta yok | ~%0,10 (BNB ile %0,075) | Mükemmel, ücretsiz (yıllarca 1 dk) | ✅ Başlangıç için en uygun |
| **Kripto spot — yerli (Binance TR, BtcTurk, Paribu, OKX TR)** | SPK geçici listesinde; API var (BtcTurk kesin; Binance TR — doğrulanmalı) | **Yasak** (7518) | BtcTurk TRY: maker %0,12, taker %0,20 | Daha kısa geçmiş, TRY bazlı | ✅ TL ile giriş/çıkış kolay, ücret daha yüksek |
| **Kripto vadeli/perp — yurt dışı** | Hukuken gri: platformun TR'ye yönelik türev sunması yetkisiz faaliyet sayılabilir (6362 m.99/A) | Var | VIP0 ~%0,02 maker / %0,05 taker (doğrulanmalı) + funding | Mükemmel | ⚠️ Likidasyon ve hukuki risk; ertelenmeli |
| **Borsa İstanbul (pay + VİOP)** | Aracı kurum API'si (ör. Deniz Yatırım **Algolab**) | VİOP'ta var | Aracı kurum komisyonu + BSMV | Seans saatli; iyi veri ücretli | ⚠️ Mümkün ama ikinci aşama |
| **FX/CFD (EURUSD, endeksler)** | Lisanslı kurum: **min. 50.000 TL teminat, maks. 1:10** (SPK III-37.1, 2017) | Var | Spread + swap | MT5 üzerinden | ⚠️ Küçük sermayeyle yasal yoldan olmaz |

**Sonuç:** İlk faz için en mantıklı alan **kripto spot**. Veri ücretsiz ve derin, piyasa 7/24 açık, API
olgun. Kaldıraç ve short gerekmez ve hukuki olarak en temiz alandır. Borsa seçimi (yurt dışı ↔ yerli) bir
planlama kararıdır. Yerli platform TL giriş-çıkışı ve hukuki kesinlik sağlar, karşılığında daha yüksek ücret
ve daha az çift sunar.

---

## 3. Mevzuat ve vergi (Türkiye, Eylül 2026)

### 3.1 Kripto — 7518 sayılı Kanun ve SPK tebliğleri

- **7518 sayılı Kanun** (RG 02.07.2024): kripto varlık hizmet sağlayıcıları (KVHS) SPK izni ve lisansına
  tabidir. Çerçeve AB'nin MiCA düzenlemesine paraleldir.
- **SPK geçici listesi (Ağustos 2026):** 55 kuruluş (Binance TR, BtcTurk, Paribu, KuCoin TR, OKX TR…) ve
  saklama için 9 banka. SPK'ya göre listede olmak **izin almış olmak anlamına gelmez**. Liste geçiş dönemi
  için bilgilendirme amaçlıdır.
- **Yerli platformlarda yasak:** kaldıraçlı işlem, türev sözleşme, kredili alım, açığa satış, ödünç.
- **Yurt dışı platformlar:** Türkiye'de yerleşik kişinin **tamamen kendi inisiyatifiyle** yurt dışı KVHS'den
  aldığı hizmet tebliğ kapsamı dışındadır. Platform Türkiye'ye yönelik faaliyet gösterirse (Türkçe site,
  pazarlama, iş yeri) mevzuat uygulanır. Bu yüzden Binance.com Türkçe desteği ve pazarlamayı kaldırdı. Erişim
  ve para yatırma/çekme sürüyor. TRY çiftleri Binance TR'ye taşındı.
- **Yurt dışı türev:** yurt dışı bir platformun Türkiye'deki kişilere kaldıraçlı/vadeli hizmet sunması
  6362 m.99/A kapsamında **yetkisiz faaliyet** sayılabilir. Yaptırım platformu hedefler ama hesap erişimi
  riski kullanıcıya da yansır. Vadeli işlemler bu yüzden ertelenmelidir.
- **Kişisel sınır (öneri):** bot yalnız sahibinin kendi hesabında, kendi parasıyla çalışır. Başkası adına
  işlem, sinyal satışı ya da copy trading **yatırım danışmanlığı/portföy yönetimi** sayılabilir ve lisans
  gerektirir. Bu kapsam dışında tutulmalıdır.

### 3.2 Vergi

- Mart 2026'da TBMM'ye sunulan teklif şunları getiriyordu: SPK lisanslı platformlarda **%10 stopaj**, FIFO
  maliyet ve satış/transfer tutarı üzerinden **on binde 3 işlem vergisi**. Teklif **27.03.2026'da Genel
  Kurul'da geri çekildi**, yasalaşmadı.
- 2026 ortası itibarıyla kriptoya özgü otomatik stopaj ya da işlem vergisi yoktur. Rejim **beyan esaslıdır**.
  Kazancın hangi gelir unsuru sayılacağı, istisna tutarı ve beyan eşiği kaynaklar arasında tutarsızdır.
  **Gerçek para dönemine geçmeden mali müşavirle netleştirilmelidir.**
- **Bot için sonuç:** her işlem tarih, fiyat, miktar, ücret ve TL karşılığıyla kalıcı olarak kaydedilir.
  FIFO maliyet raporu baştan tasarımda yer alır. Vergi rejimi değişirse (teklif yeniden gelebilir) bot
  gerekli raporu üretebilir durumda olur.

---

## 4. Maliyet — sık işlemin görünmez duvarı

### 4.1 Bileşenler

| Bileşen | Tipik değer (kripto spot, büyük çiftler) | Not |
| --- | --- | --- |
| Borsa ücreti (taraf başı) | Binance VIP0 %0,10 · BNB ile %0,075 · BtcTurk TRY maker %0,12 / taker %0,20 | Limit (maker) emir daha ucuz ama dolmayabilir |
| Spread (yarım) | BTC/ETH ~%0,005–0,01 · küçük altcoin %0,05–0,5 | Oynak anlarda açılır |
| Kayma (slippage) | Küçük emirde düşük, oynak anda yüksek | Backtest'te hep **aleyhte** varsayılmalı |
| Funding (perp) | 8 saatte bir; ± | Long taraf boğada öder |
| Çekim/transfer | Ağ ücreti | Sık transferde önemli |

### 4.2 Hesap: yıllık maliyet sürüklenmesi

Gidiş-dönüş maliyeti ≈ %0,2 (taker, BNB'siz, küçük kayma dahil) varsayılırsa:

| İşlem sıklığı | Yıllık gidiş-dönüş | Yıllık maliyet (sermayeye oran, tam pozisyon) |
| --- | --- | --- |
| Günde 10 | 3.650 | **%730** |
| Günde 1 | 365 | **%73** |
| Haftada 1 | 52 | %10,4 |
| Ayda 1 | 12 | %2,4 |
| Günlük küçük ayarlama (oynaklık hedefi, bant ile) | ~ağırlık değişimi kadar | %1–4 |

**Okuma:** günde bir gidiş-dönüş yapan bir strateji, maliyeti karşılamak için bile her işlemde ortalama
%0,2'den fazla brüt kazanmak zorundadır. Bu, piyasayı sistematik olarak yenmek demektir. Sık işlem
stratejileri çoğunlukla **brüt pozitif, net negatif** çıkar. Bu yüzden maliyet modeli backtest'in ilk günden
parçasıdır ve **hep kötü yönde** yuvarlanır.

**Maliyeti düşürme kolları:** maker (limit) emir, BNB ile ücret, VIP kademesi (yüksek hacim ister), daha az
ama daha büyük karar, bant (ağırlık küçük değiştiyse işlem yapma), likit çiftlerle sınırlanma.

---

## 5. Strateji aileleri — kanıt ve gerçekçilik

### 5.1 Trend / zaman serisi momentumu (TSMOM) — **en güçlü aday**

- **Mekanizma:** geçmiş getirinin işareti (ya da hareketli ortalama filtresi) ileriki getiriyi kısmen tahmin
  eder. Açıklama davranışsaldır: yavaş bilgi yayılımı, sürü davranışı. Kriptoda içsel değerin belirsizliği
  "gürültü tüccarı" oranını artırır. Momentum dönemleri daha uzun ve daha güçlüdür (Springer 2025, ScienceDirect).
- **Kanıt:** 2018–Mart 2026, altı varlık, oynaklık ölçekli, aylık dengeleme. Yıllık getiri ETF öncesi %18,
  sonrası %28,6. Sharpe 0,82'den 1,22'ye çıkıyor (Zenodo 2026). En likit 20 coinde ücret sonrası Sharpe
  1,5'in üzerinde, BTC'ye göre yıllık alfa %10,8 (Zarattini ve ark., SSRN 5209907). Klasik literatür:
  Moskowitz-Ooi-Pedersen (2012), 58 vadeli piyasada TSMOM.
- **Nerede kaybeder:** yatay "testere" piyasası (sık yanlış sinyal), ani V dönüşleri. Tek varlıkta çoğunlukla
  al-tut'la benzer Sharpe verir. Asıl katkısı **büyük düşüşlerden kaçınmaktır** (2018, 2022 gibi).
- **Pratik şekli:** günlük karar, 50–200 günlük filtreler ya da çoklu ufuk sinyali, oynaklık hedefli boyut,
  bantlı dengeleme. Haftada ≤ 1–2 anlamlı işlem.

### 5.2 Oynaklık hedefleme ve risk paritesi

- Pozisyon = hedef_oynaklık / gerçekleşen_oynaklık. Oynak dönemde pozisyon küçülür, sakin dönemde büyür.
- Kripto oynaklığı kümelenir (yüksek oynaklığı yüksek oynaklık izler). Bu yüzden oynaklık hedeflemesi
  kriptoda özellikle etkilidir: düşüşleri azaltır, Sharpe'ı artırır.
- Tek başına strateji değildir, **her stratejinin boyutlandırma katmanıdır.**

### 5.3 Kesitsel momentum (coinler arası sıralama)

- En çok yükselen N coin alınır. Literatür karışıktır: bazı dönemlerde güçlüdür, başka dönemlerde
  çöküşleri ağırdır ("momentum has (not) its moments").
- Riskler: hayatta kalma yanlılığı (bugünkü listeden geriye backtest, batmış coinleri dışarıda bırakır),
  düşük likidite, yüksek maliyet. Geniş altcoin evreni getiriyi çoğu zaman **düşürür**.

### 5.4 Ortalamaya dönüş (RSI, Bollinger dönüşü vb.)

- Kısa vadede (15 dk–1 saat) brüt dönüş etkisi sıkça görülür. İşlem sayısı çok yüksek olduğu için
  **spot maliyeti genellikle bu etkiyi tamamen yer.**
- Maker emir ve çok düşük ücret kademesiyle yeniden değerlendirilebilir. Varsayılan beklenti negatiftir.

### 5.5 Funding carry / basis (cash-and-carry)

- **Mekanizma:** spot long + perp short. Fiyat riski sıfırlanır, gelir perp'in ödediği funding'dir. Vadeli
  sözleşmede ise basis'in vadede sıfıra yakınsamasıdır.
- **Kanıt:** 2021 ve 2024 boğalarında yıllık çift haneli getiri ve çok düşük düşüş. 2025–26'da funding
  normalleşti (8 saatte ~0,4 bps). Bazı kurallar hiç tetiklenmedi, getiri sıkıştı. Kaynaklar 2026 için yıllık
  %10–30 ile neredeyse sıfır arasında değişiyor; çok **rejime bağlı**.
- **Engel:** perp gerektirir (§3.1 hukuki gri alan), karşı taraf ve likidasyon riski taşır (short bacak
  teminatı), borsalar arası cüzdan yönetimi ister. İkinci/üçüncü faz adayıdır.

### 5.6 Grid

- Aralık içinde eşit kademeli al-sat. Yatay piyasada küçük kârlar toplar.
- **Bir numaralı kayıp nedeni trend:** yükselişte erken satar, düşüşte sürekli alıp zararlı pozisyon
  biriktirir. Ekonomik olarak "oynaklık satmak"tır: sık küçük kazanç, seyrek büyük kayıp. Tek başına
  önerilmez. Rejim filtresiyle (yalnız yatay rejimde açık) denenebilir.

### 5.7 DCA

- Düzenli alım. Üstünlük üretmez, zamanlama riskini dağıtır. Platformların "DCA botu yıllık %18,7"
  istatistiği, o dönemdeki kripto yükselişini ölçer. Bu bir strateji becerisi değildir. Kıyas (benchmark)
  olarak faydalıdır.

### 5.8 Market making, arbitraj, HFT

- Market making spread'den kazanır ama bilgili akışa karşı **ters seçilim** ile kaybeder. Kârlılık ücret
  iadesi (rebate), gecikme ve envanter yönetimine bağlıdır. Hummingbot gibi araçlar vardır. Perakende
  kademesinde (VIP0 maker %0,10) spread'i kazanmak neredeyse imkânsızdır.
- Borsalar arası arbitraj kurumsal hız yarışıdır. Kalan fırsatlar çoğunlukla transfer süresi, çekim limitleri
  ve karşı taraf riski yüzünden vardır.
- **Kapsam dışı önerilir.**

### 5.9 ML/AI ile fiyat tahmini

- Sinyal/gürültü oranı çok düşük. Çok özellik ve çok parametre, aşırı uyum riskini hızla büyütür.
- Doğru kullanım: az sayıda anlamlı özellik, sıkı zaman serisi çapraz doğrulaması (purged/embargoed k-fold),
  deneme sayısının kaydı, Deflated Sharpe.
- "AI trading bot" pazarlamasının büyük kısmı kural tabanlı betiklerdir. Yayınlanmış, bağımsız doğrulanmış
  perakende AI kârı yok denecek kadar azdır.

### 5.10 Olay/haber odaklı

- Listeleme, delist, hack, düzenleyici karar ve ETF haberleri fiyatı hızla hareket ettirir.
- Perakende için gerçekçi olan **hızlı kazanç değil, hızlı korunmadır.** Hack ya da delist duyurusunda
  pozisyonu kapatmak ve alımı durdurmak mümkündür. Haberden önce davranan kurumlarla hız yarışına girmek
  gerçekçi değildir.
- **Jev'in en doğal yeri burasıdır** (§10).

### 5.11 Kaldıraçlı trend/kırılım botu — "maksimum kazanç" iddiasının sınaması

İnternette ve eğitim içeriklerinde sık geçen iddia: *"Maksimum kazanç stratejisi, kaldıraçlı trend/kırılım
botudur."* İddia iki parçadan oluşur ve iki parçanın kanıtı çok farklıdır.

**Parça 1: trend/kırılım: ✅ gerçek etki.** Donchian/Turtle tipi kırılım, trend takibinin en eski
biçimidir (§5.1). Kriptoda günlük BTC Donchian 20/55 sistemi 2017'den beri boğa ve ayı dönemlerinde pozitif
getiri gösteriyor. Tipik profil: kazanma oranı %30–40, ortalama kazanç ortalama kaybın 3–5 katı, uzun
düz/kayıplı dönemler. **Zaman dilimi kritik:** aynı kural BTC 30 dakikalıkta 618 işlemde −%55 verdi
(CoinQuant). Maliyet ve gürültü kısa ufukta etkiyi yok ediyor.

**Parça 2: kaldıraç: ❌ büyüme değil, iflas olasılığı çarpanı.**

*(a) Matematik.* Bileşik (geometrik) büyüme yaklaşık `g(L) = L·μ − L²·σ²/2` formülüyle hesaplanır. Getiri
kaldıraçla **doğrusal**, oynaklık kaybı **karesel** büyür. Büyümeyi maksimize eden kaldıraç Kelly
oranıdır: `L* = μ/σ²`. Trend stratejisinin σ ≈ %40 olduğu varsayımıyla:

| Kaldıraç | İyimser (μ = %30) yıllık geometrik | Temkinli (μ = %15) |
| --- | --- | --- |
| 1x | +%22 | +%7 |
| **2x** | **+%28** (Kelly L* ≈ 1,9) | −%2 (Kelly L* ≈ 0,9) |
| 3x | +%18 | −%27 |
| 5x | −%50 | −%125 → iflas |
| 10x | iflas | iflas |

İyimser senaryoda bile tepe ~2x'tedir. Gerçek μ bilinmediği ve backtest'ler iyimser olduğu için pratikte
Kelly'nin yarısı ya da çeyreği kullanılır. Bu formül henüz likidasyonu hesaba katmaz: sürekli fiyat varsayar.

*(b) Likidasyon ve fitil riski.* 10 Ekim 2025'te 24 saatte **19 milyar $** kaldıraçlı pozisyon tasfiye
edildi ve 1,6 milyondan fazla hesap likide oldu (kripto tarihinin en büyük olayı, önceki rekorun ~9 katı).
Hasarın çoğu 40 dakikada oldu. BTC ~%14, ETH ~%12 düştü, altcoinlerde fitiller çok daha derindi. Borsalar
kârlı pozisyonları da zorla kapattı (ADL). Tasfiye edilen pozisyonların ortalama kaldıracı 10–25x'tir.
Stop emri böyle bir anda istenen fiyattan dolmaz.

*(c) Kendi sınamamız.* `research/spikes/01_kaldirac_kirilim.py`. Binance public günlük veri, 2017-08 →
2026-09. Kural önceden sabitlendi, tarama yapılmadı: giriş 20 günlük kanal kırılımı, çıkış 10 günlük ters
kırılım, dolum sonraki gün açılışında. Maliyet taraf başı %0,05 + %0,02 kayma, funding yıllık ~%10. Tüm
özkaynak izole teminat. Gün içi en kötü fiyat likidasyon eşiğini aşarsa hesap sıfırlanır.

| | Kaldıraç | Son değer | Yıllık | En kötü düşüş | Likidasyon |
| --- | --- | --- | --- | --- | --- |
| **BTC long** (al-tut: 18,0 kat) | 1x | 22,7 kat | +%41 | −%55 | 0 |
| | 2x | 55,8 kat | +%56 | **−%82** | 0 |
| | 3x | 39,7 kat | +%50 | **−%95** | 0 |
| | 5x / 10x / 20x | **0** | −%100 | −%100 | **1 (hesap bitti)** |
| **BTC long+short** | 1x | 12,9 kat | +%33 | −%59 | 0 |
| | 2x | 8,0 kat | +%26 | −%92 | 0 |
| | ≥ 3x | **0** | −%100 | −%100 | 1 |
| **ETH long** (al-tut: 8,1 kat) | 1x | 10,3 kat | +%29 | −%69 | 0 |
| | 2x | 10,1 kat | +%29 | −%92 | 0 |
| | 3x | 2,3 kat | +%10 | −%99 | 0 |
| | ≥ 5x | **0** | −%100 | −%100 | 1 |
| **ETH long+short** | 1x | 4,2 kat | +%17 | −%79 | 0 |
| | 2x | 0,14 kat | −%19 | −%98 | 0 |
| | ≥ 3x | **0** | −%100 | −%100 | 1 |

**Okuma:**
- 12 kaldıraçlı (≥ 5x) yapılandırmanın **12'si** hesabı sıfırladı. 10x ve 20x çoğunlukla ilk birkaç işlemde
  bitti.
- Kaldıracın son değeri artırdığı tek bölge BTC long'da 2–3x. Bu da **geriye bakarak** seçilmiş bir sonuçtur
  (BTC'nin 9 yılda 18 kat çıktığını bilerek). −%82…−%95 düşüş gerçek hayatta "sistemi kapatıp gitme"
  noktasıdır. Böyle bir düşüşten sonra başa dönmek için 5–20 kat kazanç gerekir.
- Short bacak her iki varlıkta da değer **eksiltti** (uzun vadeli yükseliş eğilimi + short squeeze'ler).
- Kaldıraçsız kırılım bile −%55…−%79 düşüş yaşadı, çünkü tüm özkaynak her işlemde içerideydi. Bunun ilacı
  kaldıraç değil, **oynaklık hedefli boyut** (§5.2): risk sabit tutulur, düşüş küçülür.

**Hüküm:** "Kaldıraçlı trend/kırılım botu" doğru bir fikri (trend) yanlış bir boyutlandırmayla (yüksek
kaldıraç) birleştirir. Doğru sürümü: **günlük ufukta trend/kırılım + oynaklık hedefli boyut + kaldıraçsız
ya da en fazla ~1,5–2x.** 2x ancak aylarca paper/mikro canlıda ölçüldükten ve hukuki alan (perp, §3.1)
netleştikten sonra düşünülür. 5x ve üstü TradeBot'ta **hiçbir modda** kullanılmaz: veride hesap sıfırlıyor.

> Sınırlar: tek kural ailesi, iki varlık, günlük barla likidasyon kontrolü (gerçek fitiller daha derin
> olabilir, bu sonuçları iyimser yapar). Funding sabit ortalama kabul edildi. Amaç strateji seçmek değil,
> kaldıracın etkisini göstermektir.

### 5.12 Özet tablo

| Aile | Kanıt gücü | Maliyete dayanıklılık | Gereken araç | TradeBot fazı |
| --- | --- | --- | --- | --- |
| Trend + oynaklık hedefi (BTC/ETH) | Yüksek | Yüksek (az işlem) | Spot | **Faz 1 çekirdek** |
| Çoklu varlık trend (top 10–20) | Orta-yüksek | Orta | Spot | Faz 2 |
| Olay/haber risk vetosu (Jev) | Mantıksal (koruma) | — | Spot + haber akışı | **Faz 1–2** |
| Funding carry | Orta, rejime bağlı | Yüksek | Spot + perp | Faz 3 (hukuki karar sonrası) |
| Ortalamaya dönüş (kısa vade) | Brüt var, net zayıf | Düşük | Spot | Ölç, beklenti düşük |
| Grid (rejim filtreli) | Zayıf | Orta | Spot | Opsiyonel deney |
| Market making / arbitraj / HFT | Perakende için zayıf | — | Düşük gecikme | Kapsam dışı |
| Kaldıraç ≥ 5x (kırılım dahil) | Negatif: sınamada 12/12 hesap sıfırlandı | — | Perp | **Hiçbir modda** |
| Trend + düşük kaldıraç (≤ 2x) | Geriye bakışta kısmen; düşüş −%80+ | Orta | Perp | Faz G, ölçümle |

---

## 6. Doğrulama metodolojisi — bir stratejiye ne zaman güvenilir?

### 6.1 Backtest'i yalan söyleten hatalar

| Hata | Nasıl olur | Önlem |
| --- | --- | --- |
| **Geleceği görme (look-ahead)** | Kapanmamış barın kapanışıyla karar, gelecekteki veriyle normalizasyon | Karar t anına kadar kesilmiş veriyle; dolum **sonraki barın açılışında**; "t sonrası veriyi boz, sonuç değişmemeli" testi |
| **Hayatta kalma yanlılığı** | Bugünkü coin listesiyle geçmişi test etmek | O tarihte listelenmiş olan evren (point-in-time) |
| **Maliyet ihmali** | Ücretsiz, kaymasız dolum | Aleyhte kayma + gerçek ücret + spread |
| **Veri madenciliği (data snooping)** | 500 parametre dene, en iyisini raporla | Deneme sayısını kaydet, Deflated Sharpe/PBO |
| **Gerçekçi olmayan dolum** | Limit emrin mutlaka dolduğunu varsaymak | Dokunma değil, geçme şartı; kısmi dolum |
| **Rejim tekliği** | Yalnız boğa döneminde test | Boğa, ayı ve yatay dönemler ayrı ayrı raporlanır |
| **Uygulama farkı** | Backtest ile canlı kod ayrı | Tek karar fonksiyonu; canlı-backtest mutabakatı |

### 6.2 İstatistiksel hijyen

- **Örneklem dışı (OOS) ve walk-forward:** parametreler geçmiş pencerede seçilir, sonraki pencerede test
  edilir, pencere ilerletilir. OOS'a bakıp parametre değiştirmek OOS'u yakar.
- **Deflated Sharpe Ratio (Bailey & López de Prado, 2014):** raporlanan Sharpe'ı deneme sayısına, çarpıklığa
  ve basıklığa göre düzeltir. 100 deneme yapılmışsa Sharpe 1,0 anlamlı olmayabilir.
- **Probability of Backtest Overfitting (PBO, Bailey ve ark. 2015):** IS'te en iyi olanın OOS'ta medyanın
  altında kalma olasılığı.
- **Plato testi:** iyi bir strateji tek bir parametre noktasında değil, bir **bölgede** iyidir. Komşu
  parametreler de benzer sonuç vermelidir.
- **Ön kayıt (hafif sürüm):** testten önce "neyi, hangi ölçütle" test edeceğimizi bir satır olarak yazmak.
  Bürokrasi değil, kendimizi kandırmamak için ucuz bir araç.

### 6.3 Aşamalı canlıya geçiş

1. **Backtest** (maliyet dahil, çoklu rejim).
2. **Paper/dry-run:** canlı veri, simüle dolum. Kod ve operasyon hatalarını yakalar.
3. **Canlı–backtest mutabakatı:** aynı dönemi backtest'le yeniden üret; kararlar birebir aynı mı?
4. **Mikro gerçek para:** kaybedilmesi sorun olmayan küçük tutar, sabit tavan. Gerçek kayma ve ücret ölçülür.
5. **Kademeli büyütme:** önceden yazılmış sayısal ölçütle ve açık onayla.

Riski **azaltan** otomatik olabilir (kill switch, pozisyon küçültme). İzni **artıran** (sermaye büyütme,
kaldıraç, yeni strateji canlıya) her zaman insan onayı ister.

---

## 7. Risk yönetimi

### 7.1 Pozisyon boyutu

- **Oynaklık hedefli boyut** (önerilen varsayılan): `ağırlık = hedef_vol / gerçekleşen_vol`, tavanlı.
- **Sabit kesirli risk:** işlem başına özkaynağın %0,5–1'i risk (stop mesafesine göre boyut).
- **Kelly:** teorik optimum ama tahmin hatasına çok duyarlı. Pratikte en fazla ¼–½ Kelly. Kripto için
  ¼ Kelly bile agresif kalabilir.

### 7.2 Portföy seviyesinde frenler

| Fren | Örnek değer | Davranış |
| --- | --- | --- |
| Günlük kayıp limiti | Özkaynağın %3'ü | Yeni giriş yok, gün dönene kadar |
| Haftalık/aylık limit | %8 / %15 | Pozisyonları küçült, insana alarm |
| Maksimum düşüş (kill switch) | %25–30 | Her şeyi kapat, elle yeniden başlat |
| Varlık başı tavan | %50 | Tek varlığa yoğunlaşma yok |
| Toplam brüt maruziyet | ≤ %100 (kaldıraçsız) | Spot'ta zaten doğal sınır |
| Bayat veri | Son bar > 2 periyot eski | Karar yok, alarm |
| Borsa sağlık | API hatası, bakım | Emir yok, mevcut durumu koru |

### 7.3 Kaldıraç ve likidasyon matematiği

L kat kaldıraçta, bakım teminatı düşülünce, yaklaşık **1/L aleyhte hareket** pozisyonu sıfırlar:

| Kaldıraç | Likidasyona yakın aleyhte hareket | BTC'de bu hareketin sıklığı |
| --- | --- | --- |
| 2x | ~%45–50 | Nadir (büyük çöküşler) |
| 3x | ~%30 | Yılda birkaç kez gün içi mümkün |
| 5x | ~%18–20 | Sık |
| 10x | ~%9 | Olağan günlük/haftalık hareket |
| 20x+ | ~%4 | Neredeyse kesin, zaman meselesi |

Kriptoda gün içi %5–10'luk fitiller olağandır. Yüksek kaldıraçta stop'a varmadan likidasyon olur. Kaldıraç
getiriyi değil, **iflas olasılığını** çarpar. Oynaklık kaybı (volatility drag) da vardır: aynı ortalama
getiride daha oynak seri daha az bileşik büyür.

### 7.4 Karşı taraf ve operasyon riski

- **Borsa riski:** FTX (2022) gibi çöküşler. Bota ayrılan sermaye dışındaki varlık borsada tutulmaz.
- **API riski:** bakım, rate limit, bağlantı kopması, websocket sessizce donması. Her birinin davranışı
  tanımlanır.
- **Yazılım riski:** çift emir, sonsuz döngü, yanlış ondalık (0.01 yerine 1). Emir öncesi akıl kontrolü
  (boyut tavanı, fiyat bandı) kodda sabittir.

---

## 8. Mimari ve teknoloji

### 8.1 Framework karşılaştırması (2026)

| Araç | Dil / lisans | Güçlü | Zayıf | Uyum |
| --- | --- | --- | --- | --- |
| **Freqtrade** | Python · GPL-3.0 · ~53k★ · v2026.7 | Sinyal tabanlı spot/vadeli, backtest + hyperopt + dry-run, FreqUI, Telegram, lookahead/recursive analiz araçları, FreqAI, 30+ borsa | Kripto odaklı; stratejiyi kendi kalıbına sokar; hyperopt aşırı uyumu kolaylaştırır | Hızlı başlangıç ve kıyas için güçlü |
| **NautilusTrader** | Rust çekirdek + Python · LGPL-3.0 | Kurumsal event-driven motor, deterministik backtest = canlı kod, emir yönetimi, 18 adaptör, çoklu varlık | Öğrenme eğrisi dik; düşük frekans için ağır | Uzun vadede çoklu piyasa için |
| **Hummingbot** | Python · Apache-2.0 · v2.13 | Market making, 50+ CEX/DEX konektörü | Yön stratejisi için değil | Kapsam dışı (MM yok) |
| **Jesse** | Python | Look-ahead'siz backtest, sade API | Daha küçük topluluk | Alternatif |
| **CCXT** | Python/JS · MIT | 100+ borsa için birleşik API (Binance, BtcTurk…) | Yalnız bağlantı katmanı, motor değil | Kendi çekirdeğimizde bağlantı katmanı |
| **vectorbt / pandas / polars** | Python | Hızlı vektörel araştırma, parametre taraması | Canlı yürütme yok | Araştırma katmanı |
| **TensorTrade** | Python · Apache-2.0 · ~7,2k★ | RL ajanı eğitimi için modüler ortam | Canlı işlem yok; kendi README'sinde komisyon sonrası al-tut'un gerisinde | Temel olarak değil (§8.5) |

### 8.2 Kendi çekirdeğimiz mi, hazır framework mü?

| | Hazır (Freqtrade) | İnce kendi çekirdek (CCXT + Python) |
| --- | --- | --- |
| İlk çalışan bot | Günler | 1–2 hafta |
| Kontrol, öğrenme | Framework kalıbı içinde | Tam |
| Jev entegrasyonu + dondurulmuş özellik | Mümkün ama kalıba karşı | Doğal |
| Portföy seviyesi (oynaklık hedefli çok varlık) | Freqtrade işlem/pair odaklı, portföy ağırlığı zor | Doğal |
| Yerli borsa (BtcTurk/Binance TR) | Desteğe bağlı | CCXT desteği kadar |
| Bakım yükü | Topluluk taşır | Bize ait |

**Öneri (planlamada karar):** Çekirdek strateji **portföy ağırlığı** mantığında çalışır (her gün "BTC %x,
ETH %y" hedefi). Freqtrade'in giriş/çıkış sinyali kalıbına bu zor oturur. Jev ve dondurulmuş özellik
disiplini de kendi çekirdekte daha temiz kurulur. Bu yüzden **ince, kendi çekirdek** öneriyorum: bağlantı
CCXT, araştırma polars/pandas, backtest ve canlı için tek karar fonksiyonu. Freqtrade, bir spike'ta kıyas
olarak denenebilir.

### 8.3 Önerilen yığın (taslak)

| Katman | Seçim | Gerekçe |
| --- | --- | --- |
| Dil | Python 3.12+, `uv` | Ekosistem (CCXT, TypeSafe SDK, veri araçları) |
| Borsa bağlantısı | CCXT (+ gerekirse resmi SDK) | Tek arayüz, borsa değiştirmek kolay |
| Tarihsel veri | Binance public data (data.binance.vision) + CCXT; Parquet | Ücretsiz, derin, dosya hash'i = veri kimliği |
| Sorgu/depolama | DuckDB (analiz) + SQLite (canlı defter) | Sunucusuz, tek dosya |
| Araştırma | polars/pandas, numpy; kendi vektörel backtest | Hızlı tarama |
| Canlı döngü | Zamanlayıcı (günlük/saatlik), idempotent emir, mutabakat | Düşük frekans için yeterli |
| AI karar katmanı | TypeSafe SDK (`typesafe-sdk`), tek uzun ömürlü istemci | §10 |
| Alarm/kontrol | Telegram bot | Anında bildirim + komut |
| Pano | FastAPI + hafif web arayüzü (DESIGN.md ile) | PnL, pozisyon, sağlık |
| Test | pytest; look-ahead bozma testi, determinizm testi | Doğruluk şartı |
| Çalıştırma | Ev bilgisayarı ya da küçük VPS; Windows Görev Zamanlayıcı / systemd | 7/24 |

### 8.4 Canlı sistemde mühendislik gereksinimleri

- **Zaman:** her şey UTC. Bar zamanı = açılış zamanı. Saat senkronu (NTP), çünkü borsa imzalı isteklerde
  `recvWindow` dışındaki istekleri reddeder.
- **İdempotent emir:** her emre kendi `clientOrderId`'si verilir. Zaman aşımında "gitti mi?" sorgulanır,
  körlemesine yeniden gönderilmez.
- **Mutabakat:** her turda botun defteri ile borsa bakiyesi karşılaştırılır. Açıklanamayan fark varsa bot
  **durur** ve alarm verir, tahmin yürütmez.
- **Rate limit** ve websocket yeniden bağlanma. Düşük frekansta REST yoklaması çoğu zaman yeter.
- **Durum kalıcılığı:** çökmeden sonra bot, durumu borsadan ve defterden yeniden kurar.
- **Günlük (log):** her karar gerekçesi, girdi hash'i, emir ve dolum yapılandırılmış olarak kaydedilir.

### 8.5 TensorTrade ve pekiştirmeli öğrenme (RL) ile trading

**Ne:** TensorTrade, pekiştirmeli öğrenme ajanlarını trading için eğitmeye ve değerlendirmeye yarayan açık
kaynak bir Python çerçevesi (Apache-2.0, ~7,2k★). "Yeni" değil: 2019'dan beri var, bir dönem sahipsiz kaldı,
şimdi yeniden bakımda. Son PyPI sürümü 06.02.2026, Python 3.11–3.12 istiyor. Birleştirilebilir parçaları:

| Parça | Görev |
| --- | --- |
| `ActionScheme` | Ajanın çıktısını emre çevirir (varsayılan al/sat/bekle) |
| `RewardScheme` | Öğrenme sinyali (varsayılan pozisyon getirisi) |
| `Observer` | Pencereli özellik gözlemi |
| `Portfolio` / `Exchange` | Cüzdan ve **simüle** borsa (komisyon ayarlı) |

Eğitim için Ray/RLlib ve TensorFlow/Gym uyumlu ortam kullanılır. Ayrıca bir çatal var: TensorTrade-NG
(erhardtconsulting).

**Kendi README'sinin söylediği (BTC/USD, PPO ajanı):**

| | Ajan | Al-tut |
| --- | --- | --- |
| %0 komisyon | +$239 | +$594 |
| %0,1 komisyon | **−$650** | −$295 |

README'nin kendi ifadesi: *"The primary challenge is trading frequency — commission costs currently exceed
prediction profits."* Yani sıfır komisyonda bile al-tut'un gerisinde, gerçekçi komisyonda al-tut'tan daha
kötü. Bu, §4'teki maliyet duvarının RL'deki karşılığıdır.

**Değerlendirme:**

- **Canlı işlem yok.** Yalnız backtest/simülasyon. Borsaya emir gönderen, mutabakat yapan, risk freni olan
  bir bot altyapısı değildir.
- **RL'nin finans sorunu:** tek bir tarihsel yol vardır. Ajan bu yolu ezberler (aşırı uyum), ödül gürültülüdür,
  sonuç rastgele tohumdan (seed) güçlü biçimde etkilenir. Piyasa durağan değildir: eğitildiği rejim
  değişince davranışı bozulur. Deneme sayısı (hiperparametre × tohum × ödül tasarımı) çok büyüktür, bu yüzden
  Deflated Sharpe cezası (§6.2) da büyüktür.
- **Açıklanabilirlik düşük:** ajanın neden sattığını söylemek zordur. Risk motoru ve kill switch yine
  dışarıda, kodda olmak zorundadır.
- **Nerede işe yarayabilir:** yürütme optimizasyonu (büyük emri parçalama), market making envanter yönetimi
  gibi ödülü net ve sık olan dar problemler. TradeBot'un çekirdeği (günlük portföy ağırlığı) bu sınıfta değil.

**Hüküm:** TradeBot'un temeli olarak **önerilmez.** Faz G'de bir araştırma deneyi olabilir: ör. "oynaklık
hedefli trend çekirdeğini RL ajanı maliyet sonrası yenebiliyor mu?" sorusu, dondurulmuş veriyle ve sınırlı
deneme bütçesiyle sorulur. Varsayılan beklenti: yenemez.

---

## 9. Güvenlik

- **API anahtarı izinleri:** yalnız okuma + spot işlem. **Para çekme kapalı.** Vadeli açılana kadar vadeli
  izni de kapalı.
- **IP kısıtlaması:** anahtar yalnız botun çalıştığı IP'den kullanılabilir.
- **Alt hesap:** bot ana hesaptan ayrı bir alt hesapta, yalnız kendine ayrılan sermayeyle çalışır.
- **Sırlar:** `.env` git'e girmez. Windows'ta kullanıcı ortam değişkeni ya da Credential Manager kullanılır.
  Anahtar loglara ve panoya yazılmaz.
- **2FA** borsa hesabında zorunludur.
- **Pano:** yalnız yerel ağdan erişilir ya da kimlik doğrulama arkasında durur. İnternete açık bir pano
  emir veremez.
- **Telegram komutları:** yalnız sahibinin chat ID'si. Riski artıran komut (canlıya al, sermaye artır)
  ikinci bir onay adımı ister.

---

## 10. Jev (TypeSafe) — trade botta nerede, nasıl?

### 10.1 Jev nedir (kısaca)

Metin üretmeyen, yazılımın içine gömülen bir karar modeli. **State** (metin/JSON) ve tipli sorular alır:

- **Noul:** evet olasılığı (0–1)
- **Choice:** seçeneklerden biri + dağılım + güven
- **Score:** sıralı seviyeler üzerinde ağırlıklı değer + güven

Aynı state üzerindeki sorular tek istekte paralel çalışır. Türkiye'den gecikme ~0,26–0,7 sn (ilk bağlantı bu
makinede DNS yüzünden ~12 sn). Maliyet ihmal edilebilir: girdi $0,042/milyon token, çıktı ücretsiz. 2026-09-24
itibarıyla `jev-latest` → **`jev-1.13.0`** (canlı çağrıyla doğrulandı). Eski sürümler API'den kaldırılıyor.

### 10.2 Jev ile yapılmış trade botları — ne gösteriyor?

2026-09-20 tarihli bağımsız bir tarama (drillan gist) 14 finans/trading projesini inceledi:

| Proje | Jev'in rolü |
| --- | --- |
| jarrodwatts/jev-trader (★1,3k) | ~300 ms'de al/sat kararı (Monad/Kuru), post-only limit emir |
| aowang-ai/jev-trade | Hyperliquid, 5 izole varlık, long/short Choice |
| OpenByteInc/QuantDinger (★11,7k) | LLM kapısından önce "işlem öncesi karar kapısı" |
| buberlo/jev-trader | En sıkı mimari: 6 atomik yargı (rejim, yön, toksik akış, likidite stresi, kote ortamı, envanter baskısı) → politika motoru → risk vetoları |
| Spykoninho/trading-bot-jev | Haberleri sınıflandırır ("BTC hakkında 0,97", "kriptoyu destekliyor 0,93"). **Fiyat tahmini yapmaz**, trendi algoritma hesaplar |
| yasdelayu/jev-crypto-scout | Kantitatif tarama kodda, Jev aday başına **bir kez veto**: yakın zamanda yüksek güvenli olumsuz/düzenleyici haber varsa aday elenir |
| sosopop/jev_stock | Hong Kong hisse yönü (up/flat/down) + kalibrasyon |
| Gamma-Software/jev-signals-lab | 1 anlık görüntü → 12 soru → kural motoru |

**Kritik bulgu:** trading projelerinin **hiçbiri** canlı kâr/zarar ya da backtest getirisi yayınlamadı.
Hepsi paper/dry-run modunda. Ölçülmüş sonuç yalnız sınıflandırma projelerinde var: BANKING77'de BERT'e
yakın doğruluk (−1,26 puan, toplam $0,44), vergi belgesi sınıflandırmada %100 doğruluk (LLM hattından 34 kat
ucuz). "Jev ile çok daha iyi oluyor" iddiası **metin yargısı** için kanıtlı, **piyasa yönü** için değil.

Global TypeSafe notundaki ölçüm de aynı yönde: yön ekseninde isabet %49 (yazı-tura), maliyet sonrası
negatif. Jev **metnin ne dediği** konusunda güçlüdür, **dünyanın ne yapacağı** konusunda değil.

### 10.3 TradeBot'ta Jev'in önerilen rolleri (etkiden riske sıralı)

**R1 — Haber/duyuru risk vetosu (en yüksek değer).** Borsa duyuruları (delist, bakım, çekim durdurma),
kripto haber akışı ve düzenleyici açıklamalar sürekli okunur. Her metin için tek istekte paralel sorular:

- `varlik` (Choice): kod o anki portföy/evrenden aday sembolleri çıkarır, seçeneklere `hiçbiri` eklenir.
- `olay_tipi` (Choice): listeleme · delist · hack/istismar · çekim-yatırma durdurma · düzenleyici yaptırım ·
  ETF/kurumsal · token kilidi açılımı · makro · diğer.
- `resmi_kaynak` (Noul): borsa/proje/düzenleyicinin kendi açıklaması mı?
- `dogrulanmis_olay` (Noul): söylenti değil, gerçekleşmiş bir olay mı?
- `ciddiyet` (Score): varlık sahibine etkisi. Seviyeler somut durumlarla tanımlanır ("rutin güncelleme" …
  "borsadan çıkarılıyor / fonlar çalındı").

**Kod kararı:** portföydeki bir varlık için `olay_tipi ∈ {delist, hack, çekim durdurma}` ∧ `ciddiyet` yüksek ∧
güven ≥ eşik → o varlıkta **yeni alım durur**, pozisyon küçültülür ve Telegram'a alarm gider. Bu, riski
azaltan bir otomasyondur, bu yüzden otomatik olabilir. Belirsiz (düşük güven) sonuç insana gider. **Asla alım
tetiklemez.**

**R2 — Olay sınıflandırma → özellik.** Aynı yargılar sayısal özelliğe çevrilir ("son 24 saatte BTC hakkında
resmi düzenleyici olay sayısı"). Bu özellikler stratejiye ancak backtest'te **dondurulmuş** hâliyle girer ve
ölçülüp değer kattığı gösterilirse eklenir (autoresearch feature discovery kalıbı: soru → özellik → k-fold
doğrulama).

**R3 — Doğal dil komut → tipli fonksiyon (Telegram).** "BTC pozisyonu ne durumda", "bugünkü PnL",
"ETH'yi durdur", "tüm botları duraklat". Jev fonksiyonu ve kapalı kümeden argümanları seçer (function calling
cookbook'undaki trading örneği). En zayıf argümanın güveni tüm çağrının güvenidir. Okuma komutları düşük
eşikle, **riski azaltan** komutlar orta eşikle ve onayla çalışır. **Riski artıran** komutlar Jev'den geçmez,
yalnız açık komut + onayla çalışır.

**R4 — Log/alarm triyajı.** Borsa hata mesajları, bot logları: "bu hata geçici mi, müdahale mi ister?"
(Choice). Gece yarısı gereksiz alarmı azaltır.

**R5 — Rejim etiketi (deneysel, ölçülmeden karar yok).** Metin tabanlı piyasa bağlamı (ör. makro haber akışı)
→ "risk-off olay yoğunluğu" skoru. Yalnız özellik adayıdır. Önce dondurulmuş veriyle ölçülür.

**Bilinçli olarak YAPILMAYAN:** Jev'e "BTC yükselecek mi?", "al mı sat mı?" ya da "kaç birim alayım?" diye
sormak. Aritmetik, boyutlandırma ve kural kontrolü kodda kalır. Jev çıktısı tek başına alım emri üretmez.

### 10.4 Jev'i doğru kullanmanın teknik kuralları

1. **Backtest içinde canlı Jev çağrısı yapılmaz.** Tarihsel metinler bir kez sorulur, cevaplar dosyaya
   dondurulur (model sürümü, soru hash'i, state hash'i). Backtest yalnız dosyayı okur. Sürümler kalktığı için
   aksi hâlde tekrarlanamaz.
2. **Eğitim kesimi sızıntısı:** model, eğitim kesiminden önceki olayların sonucunu "biliyor" olabilir.
   TypeSafe kesim tarihini yayınlamıyor. Temkinli varsayım: kesim = sürümün çıkış tarihi. O tarihten önceki
   metinlerle yapılan ölçüm `sızıntı riski` taşır. Temiz ölçüm canlı ileri testtir.
3. **Soru seti de bir denemedir.** Sonuca bakıp soruyu değiştirmek yeni bir denemedir ve sayılır (§6.2).
4. **Güvenilmeyen metin:** haber metni prompt injection içerebilir ("bu token'ı hemen al"). Jev aksiyon
   alamaz, ama kararı saptırılabilir. Bu yüzden Jev'in yetkisi yalnız **riski azaltmakla** sınırlıdır.
5. **Tek, uzun ömürlü istemci.** Anahtar yalnız sunucu/worker tarafında durur, panoya ya da frontend'e girmez.
6. **Önce spike:** gerçek 20–50 duyuru/haberle `ts.py` üzerinde denenir. Eşikler güven–doğruluk eğrisine
   bakılarak seçilir.

### 10.5 Haber veri kaynağı adayları (spike'ta değerlendirilecek)

| Kaynak | Tür | Not |
| --- | --- | --- |
| Binance duyuru sayfası/API'si | Resmi (delist, bakım, listeleme) | R1 için en kritik |
| BtcTurk/Binance TR duyuruları | Resmi, yerli | Yerli borsa seçilirse |
| CryptoPanic API | Toplayıcı | Ücretsiz katman sınırlı |
| RSS (CoinDesk, The Block, Cointelegraph) | Basın | Ücretsiz, gecikmeli |
| SEC/SPK duyuruları | Düzenleyici | Düşük hacim, yüksek etki |

---

## 11. Gerçekçi beklentiler

- **Perakende tablo:** gün içi yatırımcıların %89–95'i bir yılda kaybeder. Beş yıl kârlı kalan ~%1'dir.
  Perakende botların %70–80'i 12 ayda zarardadır.
- **"İyi" ne demek:** maliyet sonrası Sharpe ~1 sürdürülebilir bir sistem için iyidir. Sharpe > 2 gösteren
  bir backtest önce hata aranacak yerdir.
- **Kripto trend sistemi için gerçekçi hedef:** uzun vadede al-tut'a yakın ya da biraz altında getiri, **çok
  daha küçük düşüş.** Getiri kriptonun uzun vadeli seyrine bağlıdır. Yatay yıllarda sıfıra yakın kalabilir.
- **"Bir haftada maksimum kazanç"** hedefi istatistiksel olarak maksimum kayıp hedefiyle aynı yoldan geçer:
  yüksek kaldıraç + yüksek işlem sıklığı. Kısa ufukta sonuç büyük ölçüde şanstır.
- **Asıl kazanım:** doğru kurulmuş bir bot, duygusal hataları (panik satış, FOMO alım, kayıp kovalamak) ortadan
  kaldırır ve risk kurallarını her gün eksiksiz uygular. Perakende yatırımcının en büyük kaybı çoğu zaman
  buradan gelir.

---

## 12. Planlama için sonuç ve açık kararlar

> **Güncelleme (2026-09-24):** Bu bölüm kripto odaklı ilk taslak içindi. Scryne aynı gün yönü
> değiştirdi: kurumsal, çok piyasalı, tamamen otonom. Bağlayıcı kararlar artık `docs/Final-Dokuman.md`'de.
> Çok piyasalı ek araştırma §13'te.

### 12.1 Önerilen yön

1. **Faz A — Temel ve veri:** proje iskeleti, veri indirici (Binance public data, PIT evren), kalite
   kontrolleri.
2. **Faz B — Araştırma/backtest motoru:** maliyet modeli, look-ahead testleri, walk-forward raporu, Deflated
   Sharpe.
3. **Faz C — Çekirdek strateji:** BTC+ETH (sonra top-N) trend + oynaklık hedefi. Çoklu rejimde ve maliyet
   dahil ölçüm.
4. **Faz D — Canlı altyapı (paper):** tek karar fonksiyonu, emir yürütme, mutabakat, risk frenleri, Telegram
   alarm, pano.
5. **Faz E — Jev katmanı:** haber/duyuru risk vetosu (R1) + Telegram komutları (R3). Spike → dondurulmuş
   ölçüm → gölge mod → aktif veto.
6. **Faz F — Mikro gerçek para:** önceden yazılmış ölçütle, sabit tavanlı, açık onayla.
7. **Faz G — Genişleme:** ek stratejiler (kesitsel, carry), ek piyasalar (BIST/Algolab), Jev özelliklerinin
   stratejiye girip girmeyeceği ölçümü.

### 12.2 Scryne'ın vermesi gereken kararlar

| # | Karar | Seçenekler | Öneri |
| --- | --- | --- | --- |
| 1 | Ana hedef | Uzun vadeli, riski yönetilen büyüme · kısa vadeli agresif kazanç | Uzun vadeli (kanıt burada) |
| 2 | İlk piyasa/borsa | Binance.com spot · yerli (Binance TR/BtcTurk) · ikisi | Araştırma: Binance verisi; canlı: karar |
| 3 | Kaldıraç/vadeli | Yok · ileride düşük (≤2–3x) · agresif | Faz F'ye kadar yok |
| 4 | İşlem sıklığı | Günlük/haftalık · saatlik · dakikalık | Günlük (maliyet §4) |
| 5 | Başlangıç sermayesi (gerçek para fazı) | — | Kaybı sorun olmayacak mikro tutar |
| 6 | Çalışma yeri | Bu bilgisayar · ikinci bilgisayar · VPS | 7/24 açık makine |
| 7 | Çekirdek yaklaşımı | İnce kendi çekirdek · Freqtrade · NautilusTrader | Kendi çekirdek (+ Freqtrade kıyas spike'ı) |
| 8 | Jev rolleri | R1 veto · R2 özellik · R3 komut · R4 triyaj · R5 rejim | R1 + R3 önce, R2 ölçümle |
| 9 | Arayüz | Yalnız Telegram · web pano · ikisi | İkisi (pano sonra) |

---

## 13. Ek: çok piyasalı genişleme (2026-09-24)

### 13.1 Türkiye'den piyasa erişimi

| Piyasa | Nasıl girilir | Engel |
| --- | --- | --- |
| Kripto | Binance / yerli borsa API'si | Düşük |
| BIST pay + VİOP | Aracı kurum API'si (ör. Deniz Yatırım Algolab) | Aracı kurum hesabı |
| ABD hisse, ETF, vadeli, opsiyon | Yurt dışı aracı kurum (Interactive Brokers vb.) | Hesap, vergi, hukuki durum (doğrulanmalı) |
| Forex/CFD | Yerli lisanslı kurum (MT5/API) | En az 50.000 TL teminat, en fazla 1:10 |

### 13.2 Motor karşılaştırması

| | NautilusTrader | QuantConnect LEAN | Kendi çekirdek |
| --- | --- | --- | --- |
| Çekirdek | Rust + Python kontrol düzlemi | C# + Python köprüsü | Python |
| Backtest = canlı | ✅ aynı çalışma ortamı ve zaman modeli | ✅ | Bizim sorumluluğumuzda |
| Bağlantılar | 22 kararlı: IB, Binance, Coinbase, Bybit, OKX, Kraken, Databento, Tardis… | IB, OANDA, Binance, Kraken, Coinbase, Tradier… | CCXT |
| BIST / MT5 | Yok (kendimiz yazarız) | Yok | Yok |
| Durum | v1.231.0 (Ağustos 2026) son v1. v2 (Rust + PyO3) sürüm adayı | Olgun | — |
| Karar | **Seçildi** (Faz 0 spike koşuluyla) | Yedek | Elendi (kurumsal parçalar aylarca iş) |

### 13.3 Ücretsiz veri kaynakları

| Kaynak | Kapsam | Not |
| --- | --- | --- |
| Binance public data | Kripto, 1 dk'dan itibaren, funding | Anahtarsız |
| Dukascopy | FX, metaller, emtia, endeks CFD; tick + spread, 2006→ | Anahtarsız, hesapsız HTTP; Python indiricileri var |
| Tiingo | ABD günlük, onlarca yıl | Ücretsiz katman |
| Massive (Polygon, Ekim 2025'te ad değişti) | ABD; ücretsiz: dakikada 5 çağrı, 2 yıl, gün sonu + 15 dk gecikmeli | Canlı için yetersiz |
| Alpaca | ABD; ücretsiz planda IEX akışı | Paper hesap erişimi Türkiye'den doğrulanmalı |
| borsapy / Yahoo (.IS) | BIST günlük, KAP bildirimleri | Gün içi veri zor |
| KAP (MKK VYK API) | BIST resmi bildirimler | `pykap`, `borsapy`, `kapmcp` sarmalayıcıları |
| SEC EDGAR | ABD resmi bildirimler (8-K) | Ücretsiz resmi API |
| Databento | ABD hisse, CME vadelileri, opsiyon | 125 $ ücretsiz kredi, Nautilus'ta yerleşik bağlantı |
| Ücretli (sonraki dalga) | Batmış ABD hisseleri (EODHD, Norgate…) | Hayatta kalma yanlılığını çözer |

**Uyarı:** ücretsiz ABD tek hisse verisi çoğunlukla batmış hisseleri içermez. Bu yüzden ilk dalgada ABD
tarafı ETF'lerle sınırlı. Batmış hisseleri içermeyen veriyle yapılan backtest geçmişi olduğundan parlak
gösterir.

### 13.4 Yükseltme modeli: NVIDIA build.nvidia.com

- Barındırılan katalog, NVIDIA Developer Program üzerinden prototipleme için ücretsiz. Kredi kartı
  gerekmez.
- Varsayılan dakikada ~40 istek, başvuruyla 200'e çıkarılabilir. Kota ve şartlar hesaba göre değişebilir.
- API OpenAI uyumlu.
- Güçlü modeller (Eylül 2026 kataloğu): GLM-5 (753B MoE), Kimi K3, Nemotron-3 Ultra (550B), Nemotron-3
  Super (120B), Gemma-4-31B.
- Üretim için garanti yok. Gerçek para fazında şartlar yeniden değerlendirilir. Model seçimi Spike 04'te
  ölçümle yapılır.

## Kaynaklar

**Mevzuat ve vergi**
- [SPK — Kripto Varlık Hizmet Sağlayıcılar](https://spk.gov.tr/kurumlar/kripto-varlik-hizmet-saglayicilar)
- [SPK — KVHS'lere ilişkin iki tebliğ (2025)](https://spk.gov.tr/duyurular/basin-duyurulari/2025/kripto-varlik-hizmet-saglayicilarina-iliskin-iki-teblig-yayimlandi)
- [Fintechtime — SPK geçici listesi (Ağustos 2026)](https://fintechtime.com/2026/08/spk-kripto-varlik-hizmet-saglayicilari-gecici-listesini-acikladi/)
- [AA — Kripto varlıklara ilişkin ikincil düzenlemeler](https://www.aa.com.tr/tr/ekonomi/kripto-varliklara-iliskin-ikincil-duzenlemeler-resmi-gazetede-yayimlandi/3508292)
- [Mondaq — SPK KVHS faaliyet esasları](https://www.mondaq.com/turkey/fin-tech/1598514/spk-kripto-varl%C4%B1k-hizmet-sa%C4%9Flay%C4%B1c%C4%B1lar%C4%B1n-faaliyet-esaslar%C4%B1n%C4%B1-d%C3%BCzenlendi)
- [Haberler.com (Av. Ahmet Karaca) — Kripto kaldıraç yasağı](https://www.haberler.com/yazarlar/av-ahmet-karaca/turkiyede-kripto-varliklarda-kaldiracli-islemler-yasak-mi-av-ahmet-karaca-6595/)
- [Bilal Alyar — Yurt dışı kripto borsası ve Türk vatandaşı](https://bilalalyar.av.tr/yurt-disi-kripto-borsasi/)
- [SPK — 2017 III-37.1 değişikliği (1:10, 50.000 TL)](https://spk.gov.tr/duyurular/basin-duyurulari/2017/yatirim-hizmetleri-ve-faaliyetleri-ile-yan-hizmetlere-iliskin-esaslar-hakkinda-tebligde-iii-37-1-degisiklik-yapilmasina-dair-teblig-hakkinda)
- [Coin Mühendisi — TBMM kripto vergisi son karar](https://coinmuhendisi.com/blog/tbmm-kripto-vergisi-duzenlemesinde-son-karar-neler-degisti/)
- [Ventera — Vergi Sirküleri 2026/15](https://www.venterapartners.com/vergi-sirkuleri-2026-15-kripto-varliklarin-vergilendirilmesi-ve-diger-bazi-vergi-konularina-iliskin-kanun-teklifi/)
- [Sanayi Gazetesi — Yeni kripto yasası 2026](https://sanayigazetesi.com.tr/yeni-kripto-yasasi/)
- [DefiHukuk — Kripto vergilendirmesi 2026](https://defihukuk.com/en/turkiyede-kripto-para-vergilendirmesi-2026-yasal-cerceve-ve-beyan-rehberi/) (stopajı yürürlükte gösteriyor; geri çekilme kaynaklarıyla çelişir)

**Borsalar, ücretler, API**
- [Binance — Türkiye hizmet güncellemeleri](https://www.binance.com/en/support/announcement/updates-to-binance-s-services-in-turkey-under-the-new-crypto-regulations-653d43c0083047beab4e1f6efcc48b30)
- [Bitget Academy — Türkiye borsa kuralları 2026](https://www.bitget.com/academy/turkey-crypto-rules)
- [Binance Spot API resmi dokümantasyonu](https://github.com/binance/binance-spot-api-docs)
- [BitDegree — Binance ücretleri 2026](https://www.bitdegree.org/crypto/tutorials/binance-fees)
- [BTCHaber — Kripto komisyon oranları 2026](https://www.btchaber.com/kripto-komisyon-oranlari-2026/)
- [Algolab (Deniz Yatırım) — API hizmeti](https://www.algolab.com.tr/ApiService)

**Strateji literatürü**
- [Zenodo — TSMOM in crypto, pre/post spot ETF (2026)](https://zenodo.org/records/19671502)
- [Zarattini, Pagani, Barbon — Catching Crypto Trends (SSRN 5209907)](https://papers.ssrn.com/sol3/Delivery.cfm/5209907.pdf?abstractid=5209907&mirid=1)
- [Springer — Cryptocurrency momentum has (not) its moments (2025)](https://link.springer.com/article/10.1007/s11408-025-00474-9)
- [ScienceDirect — Dynamic time series momentum of cryptocurrencies](https://www.sciencedirect.com/science/article/abs/pii/S1062940821000590)
- [arXiv 2602.11708 — Systematic trend-following with adaptive portfolio construction](https://arxiv.org/pdf/2602.11708)
- [MDPI — Two-tiered structure of crypto funding rate markets](https://www.mdpi.com/2227-7390/14/2/346)
- [GitHub zwmjj/funding-rate-arb — walk-forward carry backtest](https://github.com/zwmjj/funding-rate-arb)
- [arXiv 2606.05882 — Market informedness and market-maker profitability](https://arxiv.org/pdf/2606.05882)
- [Bitsgap — Grid trading 2026](https://bitsgap.com/blog/grid-trading-strategy-explained-how-to-profit-in-any-market-in-2026)

**Doğrulama**
- [Bailey & López de Prado — The Deflated Sharpe Ratio](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)
- [Bailey ve ark. — The Probability of Backtest Overfitting](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253)
- [arXiv 2603.20319 — Implementation risk in portfolio backtesting](https://arxiv.org/pdf/2603.20319)

**Perakende performans**
- [algotrader.ch — Algorithmic trading profitability statistics 2026](https://algotrader.ch/blog/algorithmic-trading-profitability-statistics/)
- [Tradewink — Are trading bots profitable?](https://www.tradewink.com/learn/are-trading-bots-profitable)

**Kaldıraç, kırılım, likidasyon**
- [CoinQuant — Donchian breakout on crypto](https://www.coinquant.ai/blog/donchian-channel-breakout-on-crypto-backtest-vs-keltner) · [BTC Donchian 30m backtest](https://www.coinquant.ai/strategies/btc-donchian-channel-30m-backtest)
- [QuantifiedStrategies — Donchian trend-following](https://quantifiedstrategies.substack.com/p/donchian-trend-following-strategy)
- [QuantPedia — Beware of excessive leverage (Kelly, optimal f)](https://quantpedia.com/beware-of-excessive-leverage-introduction-to-kelly-and-optimal-f/)
- [Variance drag: the hidden cost of volatility](https://beyondpassive.substack.com/p/variance-drag-the-hidden-cost-of)
- [CoinGecko — 10 Ekim 2025 tasfiye olayı](https://www.coingecko.com/learn/october-10-crypto-crash-explained) · [FTI — Leverage met liquidity](https://www.fticonsulting.com/insights/articles/crypto-crash-october-2025-leverage-met-liquidity) · [edgeX — ADL riskleri](https://pro.edgex.exchange/en-US/news/article/crypto-auto-deleveraging-risks)
- [CryptoRank — 2025 vadeli tasfiye analizleri](https://cryptorank.io/news/feed/301fd-crypto-futures-liquidations-analysis-2025)
- Kendi sınamamız: `research/spikes/01_kaldirac_kirilim.py` (Binance public günlük veri)

**TensorTrade / RL**
- [TensorTrade GitHub](https://github.com/tensortrade-org/tensortrade) · [PyPI](https://pypi.org/project/tensortrade/) · [TensorTrade-NG](https://github.com/erhardtconsulting/tensortrade-ng)

**Framework'ler**
- [Gainium — Freqtrade vs Hummingbot 2026](https://gainium.io/compare/freqtrade-vs-hummingbot)
- [alexbobes — Freqtrade alternatifleri 2026](https://alexbobes.com/crypto/best-freqtrade-alternatives/)
- [Freqtrade releases](https://github.com/freqtrade/freqtrade/releases)
- [CCXT — alternatiflerle karşılaştırma](https://docs.ccxt.com/blog/ccxt-vs-alternatives)

**Jev / TypeSafe**
- [TypeSafe dokümantasyonu](https://docs.typesafe.ai/llms.txt) · [Function calling (trading örneği)](https://docs.typesafe.ai/cookbooks/function_calling.md) · [Autoresearch feature discovery](https://docs.typesafe.ai/cookbooks/autoresearch_feature_discovery.md)
- [drillan — Jev finans & trading projeleri taraması (2026-09-20)](https://gist.github.com/drillan/6916b16e8ea31a8ec36c8f59d6483150)
- [Spykoninho/trading-bot-jev](https://github.com/Spykoninho/trading-bot-jev) · [yasdelayu/jev-crypto-scout](https://github.com/yasdelayu/jev-crypto-scout) · [zadescoxp/Jev-Trades](https://github.com/zadescoxp/Jev-Trades)
- [Bitcoin.com News — Crypto traders putting Jev to work](https://news.bitcoin.com/technology/this-ai-cant-chat-but-crypto-traders-are-already-putting-it-to-work/)
- Global not: ScryneOS `🧠 500-Knowledge/TypeSafe.md` (Jev ölçümleri ve kullanım kuralları)

**Çok piyasalı ek (§13)**
- [NautilusTrader bağlantıları](https://nautilustrader.io/docs/latest/integrations/) · [NautilusTrader 1.231.0 (v2 geçişi)](https://github.com/nautechsystems/nautilus_trader/releases/tag/v1.231.0) · [NautilusTrader GitHub](https://github.com/nautechsystems/nautilus_trader)
- [LEAN GitHub](https://github.com/QuantConnect/Lean) · [LEAN motoru](https://www.lean.io/) · [LEAN CLI – Interactive Brokers](https://www.quantconnect.com/docs/v2/lean-cli/live-trading/brokerages/interactive-brokers)
- [Dukascopy tarihsel veri](https://www.dukascopy.com/swiss/english/marketwatch/historical/) · [duka-data](https://github.com/dela-99/duka-data)
- [Massive (Polygon) fiyatlandırma](https://qveris.ai/guides/polygon-pricing-optimized/) · [Tiingo vs Massive](https://pickuma.com/for-dev/tiingo-vs-polygon-market-data-apis-indie-quant-2026/) · [Alpaca tarihsel veri](https://docs.alpaca.markets/us/docs/historical-stock-data-1)
- [EODHD — hayatta kalma yanlılığı](https://eodhd.com/financial-academy/financial-faq/survivorship-bias-free-financial-analysis) · [Databento fiyatlandırma](https://databento.com/pricing)
- [borsapy](https://github.com/saidsurucu/borsapy) · [pykap](https://github.com/cemsinano/pykap) · [kapmcp (MKK VYK API)](https://github.com/hasancagrigungor/kapmcp)
- [NVIDIA NIM fiyat/limit rehberi](https://decodethefuture.org/en/nvidia-nim-api-pricing-limits-guide/) · [NVIDIA Build ücretsiz API](https://yangmao.ai/en/providers/nvidia-build/free-api/) · [build.nvidia.com modeller](https://build.nvidia.com/models)
