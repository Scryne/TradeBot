---
proje: TradeBot
created: 2026-09-27
type: tasarim
durum: Faz 7 (paper canlı) — uygulanıyor
---
# Paper tasarımı (Faz 7)

Kod: `src/tradebot/canli/` (kollar, karar, defter, bar_akisi, dugum). Ayar: `config/paper.yaml`. Servis: compose `paper`.

## Kararlar (Claude, 2026-09-27; Scryne yetkiyi devretti)

1. **Her paper kolu kendi sanal defteriyle Nautilus sandbox'ta gerçekten işlem yapar** (kol başına 100.000 USDT
   sanal). B "sermayesiz gözlem" dağıtıcıdan pay almamak demektir. Maliyet, kayma ve sistem dayanıklılığı ancak gerçek
   emir akışıyla ölçülür.
2. **Karar, backtest'in aynı fonksiyonlarıyla verilir** (kural 3): `turnuva.grup_hazirla` → `hedef_uret` → son satır →
   `panel.dengele_adim` (bant, fren, veto). Backtest döngüsü de aynı `dengele_adim`'i çağırır.
   `tests/test_canli.py` canlı döngünün backtest ağırlık yolunu 1e-9 hassasiyetle ürettiğini doğrular (fren dahil).
   Refaktör sonrası kayıtlı turnuva sonuçları gerçek veriyle birebir yeniden üretildi.
3. **Veri:** canlı bar deposu (`data/canli`): ana depodan kopya + Binance REST ile yalnız kapanmış 1h barlar
   (ham yanıtlar ham depoda). 4h/1d, backtest'teki gibi 1h'den türetilir. Karar kolun son tamamlanmış sınırında kesilir.
4. **Zamanlama:** karar bar kapanışında, emir hemen gider, sandbox'ta canlı kotasyona karşı dolar (≈ sonraki barın
   açılışı, kural 4). Yeniden başlatmada son sınırın ilk saati içindeysek gecikmeli karar verilir, değilse sonraki
   sınır beklenir (`karar_kacirildi`): geç karar parity'yi bozar.
5. **Doğruluk kaynağı PostgreSQL defteridir** (göç 0006, hepsi yalnız eklenir): `paper_kol`, `paper_karar` (emirden önce
   yazılır; aynı kol+bar için ikinci karar olmaz), `paper_emir` (risk kararıyla), `paper_emir_olay` (dolum/ret),
   `paper_ozkaynak` (her saat, kapanışla işaretli, o saatin işlemlerinden önce). Kol tanımı değişirse aynı adla
   açılamaz: yeni paper dönemi = yeni kol adı.
6. **Toparlanma:** sandbox bellektedir. Açılışta defterdeki pozisyonlar `toparlanma` emirleriyle kurulur; bu dolumlar
   defteri ve maliyet ölçümünü değiştirmez.
7. **Mutabakat:** her kararın 5 dk sonrası Nautilus dolumlarından toplanan pozisyon ↔ defter. Fark → alarm, kol durur
   (katman 3/5: yalnız riski azaltan emir geçer).
8. **Risk:** her emir `RiskMotoru.onayla`'dan geçer (kural 5); kolun kendi portföyü, fren durumu, Jev'li kopyada veto.
   Toparlanma yalnız akıl kontrollerinden geçer (risk değişmez).
9. **Jev A/B:** her kol iki kopya (`+jev`: veto uygulanır). BTC/ETH'de veto çok nadir: fark büyük olasılıkla sıfıra
   yakın çıkar; bu da bir bulgudur.

## B → A terfi ölçütü (paper kanıtıyla)

8 haftalık paper, Sharpe ~1'lik bir kolun üstünlüğünü istatistiksel olarak kanıtlayamaz (yıllar gerekir). Terfi bu yüzden
"üstünlük kanıtlandı" değil, **"yürütme çalışıyor ve paper backtest'le çelişmiyor"** demektir. Sermaye kademeli
verilir (%25 → %50 → %100, Final Doküman §Sermaye dağıtıcı). Gerçek para Faz 12'de Scryne'ın ayrı kararıdır.

Bir kol A olur, eğer hepsi:
1. ≥ 8 hafta kesintisiz paper (düğüm kesintisi + mutabakat durdurması toplam sürenin < %2'si).
2. Kapılar paper'da da tutuyor: en kötü hafta ≥ −%10, en kötü düşüş ≥ −%30.
3. **Uygulama uyumu:** aynı dönemin backtest'i (canlı bar deposu, aynı parametre) ile paper özkaynağı arasındaki
   yıllıklaştırılmış takip hatası ≤ %5; gerçekleşen işlem maliyeti (ücret + kayma) ≤ backtest varsayımının 1,5 katı.
4. **Çelişki yok:** paper haftalık ortalamasının backtest haftalık dağılımına göre t ≥ −2.

**Terfinin kaydı:** sınıf kol tanımının parçasıdır, tanım değişirse kol yeniden açılmak zorunda kalır. Terfi bu yüzden
`paper_kol_olay`'a `terfi` olayı olarak yazılır (göç 0009): dağıtıcı sınıfı hafta başından önceki son terfi olayından
okur, yoksa config'deki sınıftan (`PaperDefter.sinif`). Paper'da terfi otomatiktir (Final Doküman §5). **Yapılacak (8.
haftadan önce, ~2026-11-22):** yukarıdaki dört ölçütü hesaplayıp olayı yazan değerlendirme (aynı dönemin backtest'i dahil).

## Kol olayları ve acil durdurma (Claude, 2026-09-27 denetimi)

`paper_kol_olay` (yalnız eklenir): `durdur` (mutabakat farkı; önceden yalnız bellekteydi), `acil_kaldir`, `terfi`.

- **Portföy kolu gerçek hesabın paper karşılığıdır: acil durdurma (tepeden −%25) kalıcıdır** (kural 7). Yalnız
  `tradebot paper acil-kaldir --kol … --onaylayan … --gerekce …` ile kalkar: olay deftere ve denetim izine yazılır,
  çalışan düğüm sonraki kapanışta uygular. Yeniden başlatmada özkaynak geçmişi olaylarla aynı sırada yeniden oynatılır.
- Gözlem kollarında (B, agresif) acil durdurma araştırmadaki gibi kalıcı değildir: stratejinin tamamı ölçülür.
- Mutabakat durdurması yeniden başlatmada kalkar: toparlanma sandbox'ı defterden yeniden kurar, fark ortadan kalkar.
  Olay kayıtta kalır, bekçi hatayı Telegram'a bildirir.

## Maliyet ölçümü (2026-09-27 denetimi)

İlk gün verisi: zamanında verilen kararda kayma ~0 bps + ücret 10 bps (backtest varsayımı taraf başı 13 bps). Açılıştaki
gecikmeli kararlarda ise "kayma" +8…+19 bps göründü. Bu yürütme maliyeti değil, karar kapanışından 20 dakika sonra
gönderilen emrin arada kalan fiyat hareketi. Ayrım artık defterde:
- `paper_emir.gonderim_fiyati` (göç 0008): emir giderken canlı orta fiyat.
- `paper_karar.ayrinti.gecikmeli`: açılışta sınırdan sonra verilen karar.
- **Yürütme maliyeti** = dolum ↔ gönderim fiyatı (+ ücret). **Gecikme kayması** = gönderim ↔ karar fiyatı. Terfi ölçütü 3
  yürütme maliyetini gecikmeli olmayan kararlardan ölçer; gecikme kayması ayrıca raporlanır.
- Sandbox yalnız kotasyona karşı doldurur (alışta ask, satışta bid; L1 miktarı biterse sonraki kotasyon). Derinlik
  modeli yok: kol başına 100.000 USDT'de BTC/ETH için sorun değil, büyük sermayede iyimser kalır.

## Sermaye dağıtıcı (Claude, 2026-09-27)

Kod: `src/tradebot/canli/dagitici.py` (saf), `PaperDefter.dagitim_getir` (okuma/yazma), düğümde `_dagitim_guncelle`.
Ayar: `config/paper.yaml` → `portfoy`. Kayıt: `paper_dagitim` (göç 0007, yalnız eklenir, portföy + hafta başına bir satır).
Elle bakış: `tradebot paper dagitim`.

1. **Haftalık, Pazartesi 00:00 UTC.** Girdi, hafta başından önceki saatlik özkaynak işaretleridir. Günlük getiri = UTC
   gününün son işaretinden son işaretine. Hafta içinde yeniden başlatmada kayıtlı dağıtım okunur, yeniden hesaplanmaz.
2. **Risk paritesi korelasyonla:** son 180 günün ortak günlerinden kovaryans, eşit risk katkısı (ERC). Ortak geçmiş
   28 günden azsa korelasyon 1 varsayılır: kanıt yokken çeşitlendirme varsayılmaz, bu da kaldıracı düşürür. Beş kolun
   hepsi BTC+ETH trendi (backtest korelasyonu ~0,79). Bu yüzden yarım Kelly, kolları tek bir risk olarak görür.
3. **Üstünlük eğimi, küçültülmüş:** Sharpe tahmini = (önsel × 365 + paper Sharpe × paper günü) / (365 + paper günü).
   Önsel = walk-forward OOS Sharpe × 0,5 (0,83–0,96 → 0,41–0,48): seçim yanlılığı ve rejim payı. Eğim = 1 + (tahmin −
   ortalama), 0,5–1,5 aralığında. Tahmini ≤ 0 olan kol pay almaz. 12 haftalık paper bile önselin ancak ~%19'u kadar
   ağırlık taşır: kısa paper dönemi gürültüdür, ağırlığı bir anda çevirmemelidir.
4. **Kaldıraç:** portföyün yarım Kelly'si, μ_p / σ_p² × 0,5 ve en fazla 3x. `kelly_kesri` 0,5'in üstüne ayarlanamaz.
   Gerçekçi girdiyle (korelasyon 0,77, kol oynaklığı %16) gölge kaldıraç ~2,2x çıkıyor. Spot'ta risk motoru enstrüman
   başına 0,5, sınıf başına 1,0 ile keser, portföy hedefi de enstrüman tavanında kırpılır.
5. **Kademe ve sınıf:** yalnız A kolu sermaye alır. Kademe paper gününe göredir: 28 gün %25, 56 gün %50, 84 gün %100.
   B→A terfisi 8. haftadan önce olamayacağı için terfi eden kol %50'den başlar. Doğrudan A girmiş bir kol (DSR ≥ 0,95)
   4. haftada %25 alır. Kademe ve sınıf yüzünden dağıtılmayan pay nakitte kalır, başka kola aktarılmaz.
6. **Gölge dağıtım:** B kollarının ağırlığı ve gölge kaldıraç her hafta yine kaydedilir, katsayıları 0'dır.
   Mekanizma, sermaye verilmeden önce 8 hafta boyunca gerçek veride izlenir.

**Portföy kolu (`portfoy@kripto_btc_eth`):** gerçek parada tek hesap nasıl işleyecekse öyle çalışır. Her saat hedef =
Σ katsayı × kaynak kolun güncel etkin hedefi (kolun kendi fren ve vetosundan sonra). Kendi defteri, frenleri, Jev vetosu
ve risk onayı vardır. Kaynaklar Jev'li kopyalardır: gerçek parada Jev açık koşacak, Jev'siz kopyalar kontrol grubudur.
Bugün bütün kollar B olduğundan portföy düz durur. Dağıtım hesaplanamazsa katsayılar sıfırlanır: portföy düzleşir ve
alarm verilir (belirsizlikte riski azalt).

## Agresif gözlem kolu (Claude, 2026-09-27)

`agresif@kripto_btc_eth`: beş kaynak kolun güncel hedeflerinin ortalaması × tam Kelly (≈ 5, aşağı yuvarlandı), enstrüman
tavanında kırpılır. Ayrı defteri var, dağıtıma girmez. Soru şu: tam Kelly'nin fazladan getirisi, fazladan düşüşe değer
mi? Kural 6 geçerli: portföy tavanı 3x, Binance spot'ta kaldıraç yok. Pratikte kolların ortalaması long iken enstrüman
başına %50 taşır.
