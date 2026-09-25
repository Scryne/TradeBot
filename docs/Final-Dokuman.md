---
proje: TradeBot
created: 2026-09-24
type: final-dokuman
status: onaylandı (2026-09-25, Scryne: "eğer bir eksik kalmadıysa faz 1'e geçebiliriz")
---
# TradeBot — Final Doküman

> Bu taslak Scryne ile 2026-09-24'teki karar konuşmalarının sonucudur. "⚑ spike" işaretli kararlar Faz 0'da
> doğrulanır. Sonuç farklı çıkarsa burada güncellenir ve gerekçesi yazılır.

## Özet

TradeBot, Scryne'ın kendi hesabı için çalışan, kurumsal kalitede, çok piyasalı ve tamamen otonom bir trade
sistemidir. Kripto, forex, emtia, endeks, ABD ETF ve BIST piyasalarında yedi strateji ailesini aynı
kurallar ve gerçekçi maliyetlerle bir turnuvada yarıştırır. Çok haftanın ortalamasında en yüksek net
haftalık bileşik büyümeyi veren ve risk kapılarını geçen kollara sermayeyi otomatik olarak kademeli
dağıtır. Emir yürütmeyi, muhasebeyi ve mutabakatı olgun bir motor (NautilusTrader) üstlenir. Sistemi
farklı kılan katmanlar projeye özeldir: turnuva, sermaye dağıtıcı, beş katmanlı risk ve Jev tabanlı zekâ
katmanı. İlk aşama tamamen paper'dır.

## Teknoloji Stack

| Katman | Seçim | Gerekçe |
| --- | --- | --- |
| Dil / paket | Python 3.12, `uv` | Ekosistem: Nautilus, TypeSafe SDK, veri araçları |
| İşlem motoru | **NautilusTrader v2** (`==2.0.0rc5` sabit) ✅ Spike 02 | Emir yönetimi, risk, çoklu para birimli muhasebe, mutabakat hazır; 22 kararlı bağlantı; Python ile özel bağlantı yazılabiliyor; parity %0,0000 (1 dk yürütme) |
| Yedek motor | QuantConnect LEAN | Gerek kalmadı (Spike 02 geçti); kayıt için duruyor |
| Hızlı araştırma | polars + numpy (vektörel) | Binlerce kol × parametre taraması |
| Tarihsel veri deposu | Ham dosyalar (SHA-256 kimlikli, değişmez) + **kendi normalize Parquet bar depomuz** (kanonik). Nautilus kataloğu Faz 3'te bundan dışa aktarılır | Nautilus v2 API'si değişiyor (Spike 02): veri Nautilus sürümünden bağımsız kalır, katalog her zaman yeniden üretilebilir |
| Defter / denetim | PostgreSQL (Docker) | Deneme defteri, turnuva sonuçları, Jev kayıtları, denetim izi |
| Zekâ katmanı | TypeSafe SDK (Jev, `jev-1.13.0` sabit) + OpenAI uyumlu istemci (NVIDIA build.nvidia.com) | Jev yargılar; belirsiz durum ücretsiz yükseltme modeline gider |
| Paketleme | Docker Compose (WSL2 üzerinde), konteyner DNS'i `1.1.1.1` / `8.8.8.8`, sanal makine saati için chrony servisi (`saat`, yalnız SYS_TIME) | Tek komutla ayağa kalkar; ev router'ının DNS'i IPv6'sız adlarda 5–15 sn gecikiyor (Spike 02) |
| Bildirim | Telegram bot | Kritik / uyarı / bilgi seviyeleri |
| Pano | FastAPI + web arayüzü (DESIGN.md) | Tailscale üzerinden telefondan erişim, internete kapalı |
| Uzaktan erişim | Tailscale + SSH | Şifreli özel ağ |
| Test | pytest | Look-ahead bozma, determinizm, parity, risk tavanı testleri |
| Host | Evdeki ikinci bilgisayar: Windows, 16 GB RAM, 1 TB, kablolu | 7/24; MT5 için Windows gerekiyor |

## Mimari

```
┌──────────────────── ZEKÂ KATMANI ────────────────────────────────┐
│  Toplayıcılar: KAP · SEC EDGAR · Binance duyuruları · RSS ·       │
│  merkez bankaları · GDELT · aracı kurum bildirimleri              │
│  → Jev servisi (tek kapı, kayıt + dondurma) → NVIDIA yükseltme    │
│  Çıktı: olay mesajları (veto, olay özelliği, kurumsal işlem,     │
│          enstrüman eşleme, takvim güncellemesi)                  │
└───────────────┬──────────────────────────────────────────────────┘
                │
┌───────────────▼──────── İŞLEM MOTORU (NautilusTrader) ───────────┐
│  Strateji sarmalayıcıları → saf karar çekirdeğini çağırır        │
│  Risk motoru (katman 1-4) → emir yönetimi → bağlantılar          │
│  Portföy / muhasebe / mutabakat / veri kataloğu                  │
│  Bağlantılar: Binance · IB (ileride) · Alpaca? ⚑ · MT5 köprüsü   │
│  (bizim) · BIST veri bağlantısı (bizim)                          │
└───────▲───────────────────────────────┬──────────────────────────┘
        │ haftalık sermaye dağılımı       │ işlem, özkaynak, olay
┌───────┴──── ARAŞTIRMA & TURNUVA ─────┐ ┌─▼──────── OPERASYON ─────────────┐
│ Deneme defteri · vektörel tarama     │ │ Bağımsız gözetmen (katman 5)     │
│ Walk-forward · plato · DSR           │ │ Telegram · pano · log triyajı    │
│ Nautilus doğrulama (parity)          │ │ Denetim izi · günlük yedek       │
│ Puan + kapılar · sermaye dağıtıcı    │ │ Haftalık turnuva raporu          │
└──────────────────────────────────────┘ └──────────────────────────────────┘
```

### Temel tasarım kararları

1. **Saf karar çekirdeği.** Strateji mantığı Nautilus'tan bağımsız saf fonksiyonlardır: I/O yapmaz,
   yalnız t anına kadar kesilmiş veriyi görür. Vektörel tarama ve Nautilus sarmalayıcısı aynı fonksiyonu
   çağırır. Parity testi ikisinin kararlarının birebir aynı olduğunu doğrular.
2. **Sinyal risk motorunu atlayamaz.** Emre giden tek yol risk onayıdır. Engelleyen katman (veto, bayat
   veri) risk motorunun dışında olabilir. İzin veren katman olamaz.
3. **Bağımsız gözetmen.** Motordan ayrı bir süreçtir. Kalp atışını, özkaynağı ve pozisyonları izler. Motor
   donarsa aracı kurum API'si üzerinden pozisyonları kapatır.
4. **Zekâ katmanı ayrı servistir.** Motora yalnız hazır olay mesajları gönderir. Backtest'te aynı mesajlar
   dondurulmuş dosyadan okunur (model sürümü + soru hash'i + girdi hash'i).
5. **Otomasyon asimetriktir.** Riski azaltan her şey otomatiktir: veto, fren, kol durdurma, acil durdurma.
   İzni artıran şeyler (acil durdurma sonrası yeniden başlatma, gerçek paraya geçiş, tavan değişikliği)
   Scryne'ın onayını ister. Paper'da kol terfisi otomatiktir.
6. **Zaman UTC**, nanosaniye epoch (Nautilus). Bizim verimizde bar zaman damgası açılış zamanıdır;
   Nautilus'a verilirken `ts_event` = kapanış zamanıdır (bar ancak kapanınca bilinir). Piyasa takvimleri
   enstrüman kaydındadır. Host saati NTP ile senkron tutulur (Spike 02'de 1 sn kayma ölçüldü).
7. **Yürütme verisi politikası (Spike 02).** Nautilus'ta sonraki bar açılışında dolum modu yok; bar verisiyle
   emir sinyal barının kapanışından dolar (seanslı piyasada iyimser: SPY'da %3,2 fark). Bu yüzden:
   - **Turnuva metrikleri kendi vektörel motorumuzdan gelir** (dolum sonraki barın açılışında, bağlayıcı).
   - **Nautilus doğrulaması 1 dk yürütme verisiyle yapılır** (günlük karar iç barla, dolum sinyalden sonraki
     ilk dakikada, 1 ms gecikme modeli). Parity testi kalıcıdır: karar birebir, özkaynak farkı ≈ 0.
   - 1 dk verisi olmayan piyasada Nautilus backtest'i metrik üretmez; o piyasa paper'da Nautilus'la yaşar.
8. **Sürüm sabitleme ve ince sarmalayıcı.** Nautilus sürümü tam sabittir; yükseltme parity testi geçerek
   verilen ayrı bir karardır. Strateji mantığı saf çekirdektedir, Nautilus'a dokunan kod ince
   sarmalayıcılarda toplanır (v2 API'si rc'ler arasında değişiyor).

## Veri

**İlk dalga (ücretsiz):**

| Piyasa | Tarihsel | Canlı (paper) | Metin (Jev) |
| --- | --- | --- | --- |
| Kripto | Binance public data (1 dk'dan itibaren, funding) | Binance public akış | Binance duyuruları, RSS, CryptoPanic |
| FX, metaller, emtia, endeks CFD | Dukascopy: saatlik (aylık dosya) 20 yıl, dakikalık son 2–3 yıl; nazik indirici (Spike 03) | MT5 demo + Windows köprü servisi (Spike 05) | Merkez bankası metinleri, GDELT (dosya dökümü) |
| ABD ETF'leri | Yahoo günlük (`period1/period2`; SPY 1993→) | Alpaca paper IEX akışı, kendi istemcimiz (Spike 05) | SEC EDGAR |
| BIST (günlük) | Yahoo (.IS) + borsapy yedek; bedelsiz = Yahoo split + KAP (B1) | Yahoo/borsapy gecikmeli, kendi istemcimiz, sandbox dolum | KAP (borsapy üzerinden, HTML'den metin) |

**Sonraki dalgalar (ölçüm fırsat gösterirse, ayrı kararla):** ABD tek hisseleri (batmış hisseleri de
içeren ücretli veri), CME vadelileri (Databento; 125 $ kredi, Nautilus'ta yerleşik bağlantı), VİOP
(aracı kurum hesabı).

**Kurallar:**
- İndirici kuralları `docs/spikes/03-veri.md` §3'tedir (zaman birimi tespiti, Yahoo `range=max` yasağı,
  Dukascopy hız sınırı, PIT evren, ilk yayın zamanı, canlılık testi, yedek kaynak).
- Ham veri değişmez, hash'i kimliğidir.
- Point-in-time evren.
- Metinlerde zaman ilk yayın zamanıdır.
- Kurumsal işlem düzeltmeleri hamdan yeniden üretilir.
- Her kaynak için kalite raporu tutulur.

## Strateji turnuvası

**Aileler ve zaman dilimleri:**

| Aile | Piyasalar | Ufuk |
| --- | --- | --- |
| Trend / momentum (TSMOM, MA filtresi, Donchian/Bollinger) | Tümü | 1h · 4h · 1d |
| Kesitsel momentum | Kripto top-N, sektör ETF, BIST, döviz sepeti | 1d · 1w |
| Ortalamaya dönüş (kısa vade, çift ticareti) | FX, endeks, ETF çiftleri, BIST | 15m–1h (yalnız düşük maliyetli piyasa) |
| Carry (FX swap, kripto funding: yalnız paper) | FX, kripto | 1d |
| Takvim etkileri (gece, ay dönümü, tatil öncesi) | ABD ETF, endeks, BIST | 1d |
| Gün içi kırılım (açılış aralığı) | ABD ETF, endeks CFD | 5m–15m |
| Olay tabanlı (KAP/SEC olay sonrası kayma) | BIST, ABD | 1d |

**Eleme hunisi:**
0. Test planı (bir satır, deneme defterine).
1. Hızlı vektörel tarama, maliyet dahil.
2. Sağlamlık: walk-forward örneklem dışı, plato, rejim ayrımı, Deflated Sharpe.
3. Nautilus'ta gerçekçi yürütme (parity).
4. Paper: en az 4 hafta.
5. Sermaye.

**Puan ve kapılar:**
- Puan, ortalama net haftalık log büyümedir.
- Kapılar: kol başına en kötü hafta ≥ −%10, en kötü düşüş ≥ −%30, anlamlı işlem sayısı, DSR anlamlı.

**Sermaye dağıtıcı:**
- Oynaklık eşitleme (risk paritesi) ve üstünlüğe göre ağırlık (küçültülmüş tahmin).
- Korelasyon kontrolü.
- Portföy kaldıracı yarım Kelly, en fazla 3x.
- Haftalık yeniden dağıtım.
- Kademeli sermaye: 4 hafta paper → %25, 8 → %50, 12 → %100.

**Jev A/B:** Her kol Jev vetolu ve Jev'siz olarak iki kez yarışır. Jev'in katkısı piyasa bazında
raporlanır.

**Agresif gözlem kolu:** Tam Kelly, en fazla 3x. Ayrı defter tutar, dağıtıma girmez.

## Risk motoru

| Katman | Kontroller | İhlalde |
| --- | --- | --- |
| 1 Emir öncesi | Fiyat bandı, azami boyut, lot ve fiyat adımı, piyasa açık mı, veri bayat mı, veto listesi, **3x tavan (kod sabiti)**, emir hızı, çift emir | Ret + log + alarm |
| 2 Pozisyon | Felaket stop'u (oynaklığa göre), likidasyon mesafesi, enstrüman/sektör/sınıf yoğunlaşması | Küçült / kapat |
| 3 Kol | Beklenenin üstünde düşüş, canlı ↔ backtest sapması | Kol durur → 2 hafta sıfır sermayeyle gözlem → turnuvaya döner |
| 4 Portföy | Günlük −%3, haftalık −%8, **acil durdurma −%25**, brüt/net maruziyet, korelasyon, tarihsel VaR izleme | Fren: yeni giriş yok · Acil durdurma: her şey kapanır, yeniden başlatma Scryne onayıyla (canlı). **Araştırmada** (Faz 4 kararı): acil durdurma olay olarak sayılır ama kalıcı değildir (stratejinin tüm dönemi ölçülür); acil tetikleyen strateji kapıdan geçemez |
| 5 Sistem | Bağımsız gözetmen, borsa sağlığı, saat senkronu, mutabakat farkı, Jev/haber servisi sağlığı | Motor donarsa kapat; mutabakat farkında dur; Jev yoksa "habere kör" mod (yeni giriş yarım boyut) |

## Zekâ katmanı (Jev)

| Grup | Roller | Durum |
| --- | --- | --- |
| A — Koruma | A1 haber/duyuru vetosu · A2 KAP · A3 SEC 8-K · A4 pump/manipülasyon · A5 borsa/aracı kurum bildirimleri · A6 emir reddi sınıflandırma | v1 |
| B — Veri doğruluğu | B1 kurumsal işlem tespiti · B2 enstrüman eşleme · B3 sözleşme şartnamesi okuma · B4 haber tekilleştirme | v1 |
| C — Strateji özellikleri | C1 olay özellikleri · C2 merkez bankası tonu · C3 şirket açıklaması tonu · C4 metin tabanlı rejim | Ölçümle girer |
| D — Operasyon | D1 log/alarm triyajı · D2 rapor doğrulama · D3 deneme tekrar dedektörü · D4 Telegram salt-okuma sorguları | v1 |

**İlkeler:**
- **Jev yargılar, kod uygular.** Jev çıktısı tek başına alım üretmez. Yetkisi yalnız riski azaltmaktır.
  Bu, prompt injection'a karşı da korumadır.
- **Tek Jev servisi:** Her çağrı model sürümü, soru hash'i ve girdi hash'iyle kaydedilir. Maliyet ve
  gecikme izlenir.
- **Kademeli yükseltme:** Jev → (güven düşükse) NVIDIA modeli. Cevap kapalı etiketli JSON olur, kod
  doğrular, isteğe bağlı olarak Jev çapraz denetler. Geçersiz ya da belirsizse riski azalt ve alarm ver.
  Yükseltme modeli spike'ta ölçümle seçilir ve sürümü sabitlenir. Yedek zinciri vardır.
- **Kalibrasyon:** Her rolün eşiği gerçek örneklerle seçilir. Vetoda kaçırılan olay, yanlış alarmdan daha
  pahalıdır.
- **Spike 04 ölçümü (A1/A2/B1):**
  - Binance 46/46, KAP 44/44 doğru; tuzaklar dahil.
  - Veto yanlış alarmı Jev'de 0, anahtar kelime kuralında 30.
  - Gecikme 0,25 sn.
- **Karar Choice'a dayanır, Score'a değil:** aciliyet skoru yalnız alarm önceliği içindir, veto koşulu olmaz.
- **Başlangıç eşiği:** veto yönünde güven ≥ 0,5. Altı yükseltmeye gider. Belirsizlikte veto kategorisi en
  olası iki seçenekten biriyse riski azalt. İlk ay gölge modda kalibre edilir.
- **Rol eklerken önce tuzak listesi yazılır**, sonra her seçeneğin `not_for` tanımı bu tuzaklara göre
  yazılır.
- **Backtest'te canlı çağrı yok:** Yargılar dondurulur. Eğitim kesimi öncesi metinler `sızıntı riski`
  işareti taşır.
- **Yasak:** yön, fiyat, boyut, kaldıraç, hesap, emir kararı.

## Operasyon

- **Host:** Evdeki ikinci bilgisayar (Windows, WSL2 + Docker Desktop). Uyku kapalı. Windows Update'in
  yeniden başlatmaları kontrollü. Elektrik gelince otomatik açılış (BIOS). Ana makineden SSH ile erişim.
- **Süreçler (Docker Compose):** veri toplayıcılar, zekâ servisi, Nautilus düğümleri, sermaye dağıtıcı,
  gözetmen, PostgreSQL, pano API. MT5 terminali Windows tarafında çalışır, köprü bağlantısıyla bağlanır.
- **Bildirim:** Telegram. Kritik ve uyarı anında gelir (uyarılar gece sessiz saatte gruplanır). Günlük
  özet ve haftalık turnuva raporu gönderilir.
- **Pano:** PnL, pozisyonlar, turnuva tablosu, veto geçmişi, sağlık. Yalnız Tailscale üzerinden erişilir.
- **Kayıt ve yedek:** Yapılandırılmış log'lar, denetim izi, günlük veritabanı ve ayar yedeği.
- **Sırlar:** yalnız host'ta tutulur. Git'e, log'a ve panoya girmez.

## Kapsam (v1)

İlk dalga dört piyasa grubunda backtest + paper turnuvası; zekâ katmanında A, B, D grupları ile C ölçümü;
beş katmanlı risk; otonom sermaye dağıtımı; operasyon ve pano. Başarı ölçütü: 12 haftalık kesintisiz paper
turnuvası ve haftalık raporlar. Bu raporlar hangi kolların kapıları geçtiğini ve Jev'in katkısını
gösterir.

## Riskler ve Doğrulamalar

| Risk | Doğrulama | Durum |
| --- | --- | --- |
| Yüksek kaldıraç hesabı sıfırlar | Spike 01: BTC/ETH Donchian 1–20x | ✅ Doğrulandı: ≥ 5x 12/12 iflas → 3x tavan, yarım Kelly |
| Nautilus v2 sürüm adayı kararlı mı; Windows/WSL2; özel bağlantı yazılabilir mi | Spike 02 | ✅ Geçti (koşullarla): kurulum, parity, özel Python istemci, canlı paper; koşullar: 1 dk yürütme verisi, sürüm sabitleme, konteyner DNS'i, NTP |
| Ücretsiz veri yeterli mi (kalite, kapsam, hız); BIST gün içi | Spike 03 | ✅ Geçti: tüm ilk dalga kaynakları çalışıyor; tuzaklar (µs zaman damgası, Yahoo aylık, Dukascopy hız sınırı) indirici kurallarına bağlandı; BIST gün içi yalnız son günler (günlük strateji için yeterli) |
| Jev A1/A2 eşikleri; NVIDIA yükseltme modeli seçimi | Spike 04 | ✅ A: 90/90, yanlış veto 0 (anahtar kelime: 30) · ⏳ B: NVIDIA anahtarı bekliyor (Faz 6'nın ilk işi) |
| Paper canlı bağlantılar: ABD ETF paper hesabı Türkiye'den; MT5 köprüsü | Spike 05 | ✅ Yol belli: Alpaca paper (herkese açık) + kendi istemcimiz; MT5 demo + Windows köprü; BIST Yahoo/borsapy; yürütme her yerde Nautilus sandbox |
| Maliyet varsayımlarının gerçekliği (maker dolum, spread) | Paper ölçümü (Faz 11) | ⏳ |
| Turnuvada aşırı uyum | Deneme defteri + DSR + walk-forward + paper | Tasarımda |
| Otonom sistemin sessiz arızası | Bağımsız gözetmen + mutabakat + Telegram | Tasarımda |

## Kapsam Dışı

5x ve üstü kaldıraç ve martingale · market making, HFT, arbitraj · RL'yi temel olarak kullanmak · Jev'e
yön/fiyat/boyut/emir kararı · başkasının parası ve ürünleştirme · v1'de ücretli veri · v1'de gerçek para.
