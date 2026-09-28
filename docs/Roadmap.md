---
proje: TradeBot
created: 2026-09-24
updated: 2026-09-27
type: roadmap
status: aktif (sürüm 2 — kurumsal, çok piyasalı)
---
# TradeBot — Roadmap

Durum sütunu session-start hook'u tarafından otomatik okunur — format bozulmasın:
⏳ Bekliyor / 🔄 Devam Ediyor / ✅ Tamamlandı.

Her faz bittiğinde "Notlar" satırı öğrenilenle doldurulur ve sonraki fazlara işlenir. Karar gerekçeleri
`docs/Final-Dokuman.md`'de.

| Faz | Adı | Durum | Bitti Kriteri |
| --- | --- | --- | --- |
| 0 | Riskli kararların spike'ları | ✅ Tamamlandı | Spike 02–05 raporları `docs/spikes/` altında; Final Doküman'daki ⚑ kararlar kesinleşti ya da yedek plana geçildi |
| 1 | Altyapı ve host | ✅ Tamamlandı | Host (WSL2 + Docker + Tailscale + SSH, 7/24 ayarları) hazır; `uv` projesi, Compose iskeleti, PostgreSQL, sır yönetimi, log düzeni; testler yeşil |
| 2 | Veri platformu (ilk dalga) | ✅ Tamamlandı | Kripto, Dukascopy, ABD ETF, BIST günlük verileri katalogda; enstrüman kaydı + takvimler + kurumsal işlemler; PIT evren; kaynak başına kalite raporu |
| 3 | Araştırma motoru | ✅ Tamamlandı | Saf karar çekirdeği; piyasa başına maliyet modelleri; vektörel tarama; walk-forward + plato + DSR; deneme defteri; vektörel ↔ Nautilus parity testi geçiyor |
| 4 | Risk motoru ve boyutlandırma | ✅ Tamamlandı | 5 katman kodlu ve testli; 3x tavan ve ≥ 5x imkânsızlığı testli; yarım Kelly; frenler, acil durdurma, onaylı yeniden başlatma |
| 5 | Turnuva — backtest dalgası 1 | ✅ Tamamlandı | 7 aile × ilk dalga piyasalar huni aşama 0–3'ten geçti; puan tablosu; paper'a girecek kollar yazılı ölçütle seçildi |
| 6 | Zekâ katmanı (Jev) | 🔄 Devam Ediyor | Toplayıcılar (Binance, KAP, RSS, Fed/ECB/TCMB); Jev servisi + NVIDIA yükseltme; A1, A2 canlı; B1 çapraz kontrolü; yargılar dondurulabiliyor; C1–C2 ölçüldü (A4, A5, D3, B2, B4 girdilerinin doğduğu faza taşındı, 2026-09-27) |
| 7 | Paper canlı — kripto + ABD ETF | ✅ Tamamlandı | Nautilus düğümleri paper'da 7/24; sermaye dağıtıcı; Jev'li/Jev'siz kollar; agresif gözlem kolu; mutabakat ve toparlanma testli |
| 8 | Özel bağlantılar — MT5 (FX/emtia/endeks) + BIST | 🔄 Devam Ediyor | MT5 demo köprüsü ve BIST (gecikmeli) paper bağlantısı çalışıyor; bu piyasaların kolları paper turnuvasında |
| 9 | Operasyon: gözetmen, Telegram, raporlar | 🔄 Devam Ediyor | Bağımsız gözetmen motor donmasını yakalıyor (tatbikatla); Telegram 3 seviye; günlük özet + haftalık turnuva raporu; log triyajı; yedek |
| 10 | Web pano | ⏳ Bekliyor | DESIGN.md dolu; PnL, pozisyon, turnuva tablosu, veto geçmişi, sağlık; Tailscale üzerinden telefondan erişim |
| 11 | Paper turnuvası — 12 hafta | 🔄 Devam Ediyor | 12 hafta kesintisiz paper; kademeli sermaye çalıştı; hangi kolların kapıyı geçtiği ve Jev katkısı raporlandı; maliyet varsayımları ölçüldü |
| 12 | Gerçek para (koşullu) | ⏳ Bekliyor | Scryne'ın kararı + aracı kurum/borsa + anahtar (çekim kapalı, IP kısıtlı) + vergi netliği; sabit tavanlı mikro sermaye; ilk emir Scryne onayıyla |
| 13 | Sonraki dalgalar (koşullu) | ⏳ Bekliyor | Ölçüm fırsat gösterirse: ABD tek hisseleri (ücretli veri), CME vadelileri (Databento), VİOP; her biri ayrı kararla |

## Faz Detayları

### Faz 0: Riskli kararların spike'ları
- **İşler:**
  - `01_kaldirac_kirilim` ✅: BTC/ETH günlük Donchian, 1–20x; ≥ 5x 12/12 iflas (Araştırma §5.11).
  - `02_nautilus`: v2 sürüm adayını Windows + WSL2'de kur; kripto ve ABD ETF verisiyle backtest; aynı saf
    karar fonksiyonunu vektörel ve Nautilus'ta çalıştır (birebir aynı karar); BIST günlük verisi için özel
    veri bağlantısı iskeleti; Binance testnet/public ile kısa canlı döngü. Başarısızsa LEAN ile aynı adımlar.
  - `03_veri`: Binance public data, Dukascopy, Tiingo/Massive/Alpaca, borsapy/Yahoo, KAP (MKK VYK), SEC
    EDGAR. Erişim, hız, boyut, kalite ve kapsam. BIST gün içi verisi mümkün mü?
  - `04_jev`: 20–50 gerçek Binance duyurusu + KAP bildirimi ile A1/A2 soru setleri; güven–doğruluk
    tablosu, eşik önerisi; belirsiz örneklerde 2–3 NVIDIA modelinin karşılaştırması, model seçimi.
  - `05_paper_baglanti`: ABD ETF paper hesabı (Alpaca ya da alternatifi) Türkiye'den açılabiliyor mu?
    MT5 demo köprüsü seçenekleri (resmi Python paketi + Windows tarafı servis).
- **Bitti Kriteri:** her spike için kısa rapor ve Final Doküman'a işlenen karar.
- **Notlar:** Spike 01 araştırma sırasında yapıldı, kaldıraç politikasının dayanağı.
  - Spike 02 ✅ (2026-09-25): Nautilus v2 kesinleşti.
    - Bar verisiyle "sonraki açılışta dolum" modu yok → turnuva metrikleri vektörel motordan, Nautilus
      doğrulaması 1 dk yürütme verisiyle yapılır (Faz 2'de 1 dk veri indirme, Faz 3'te kalıcı parity testi).
    - Konteyner DNS'i 1.1.1.1 ve NTP senkronu Faz 1 host işlerine eklendi.
    - Rapor: `docs/spikes/02-nautilus.md`.
  - Spike 03 ✅ (2026-09-25): tüm ilk dalga veri kaynakları ücretsiz çalışıyor.
    - İndirici kuralları → Faz 2 şartnamesi: µs/ms tespiti, Yahoo `period1/period2`, Dukascopy ≥ 3 sn ve
      aylık saatlik dosyalar, PIT evren, ilk yayın zamanı.
    - Stooq elendi. Rapor: `docs/spikes/03-veri.md`.
  - Spike 04-A ✅ (2026-09-25): Jev vetosu Binance 46/46, KAP 44/44.
    - Yanlış veto 0 (anahtar kelime kuralında 30). Karar Choice'a dayanır, Score'a değil.
    - 04-B (NVIDIA model seçimi) anahtar beklediği için Faz 6'nın ilk işine taşındı.
    - Rapor: `docs/spikes/04-jev.md`.
  - Spike 05 ✅ (2026-09-25): paper yürütme her piyasada Nautilus sandbox.
    - Canlı veri: Alpaca paper (ABD), MT5 demo + Windows köprü (FX/emtia/endeks), Yahoo/borsapy (BIST).
    - Rapor: `docs/spikes/05-paper-baglanti.md`.

### Faz 1: Altyapı ve host
- **İşler:** Host kurulumu: WSL2, Docker Desktop, Tailscale, SSH, uyku kapalı, Windows Update
  kontrolü, elektrik gelince açılış, **NTP saat senkronu**, **konteyner DNS'i (1.1.1.1 / 8.8.8.8)** ve host'ta
  DNS gecikmesi ölçümü. Repo yapısı, `uv`, Compose iskeleti, PostgreSQL, `.env` / sır
  yönetimi, yapılandırılmış log, pytest ve temel CI (yerel).
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**
  - 2026-09-25 (a) repo tarafı ✅:
    - `tradebot` paketi: ayar/sır (SecretStr), JSON log + sır maskeleme, hash zincirli denetim izi.
      PostgreSQL'de UPDATE/DELETE tetikleyiciyle reddediliyor, gerçek PG 17'de doğrulandı.
    - Sağlık komutu: DNS, NTP + Binance saat kayması, veritabanı, disk, sırlar.
    - Alembic 0001; Dockerfile (uv, root olmayan kullanıcı); compose (postgres 17, göç, sağlık izleyici,
      konteyner DNS 1.1.1.1, log döndürme); 13 test + ruff temiz.
    - Bu makinede sağlık kontrolü saat kaymasını yakaladı: +1,2–1,4 sn, Windows saati hiç senkron değil.
  - (b) host kurulumu 🔄: `tools/host/` (baslangic, kurulum [Kontrol/-Uygula/-SadeceAnahtar], guncelle) ve
    `docs/host/Kurulum.md` hazır.
    - Host (192.168.1.4, Windows 11, 15,8 GB, C: 471 GB boş): anahtarla SSH ✅, uyku kapalı ✅, Windows Update
      yeniden başlatma kontrolü ✅, `C:\TradeBot` ✅.
    - NTP: kaynak Cloudflare. Yüksek doğruluk ayarlarıyla fark −720 ms'den ±0,3 ms'ye indi ✅.
    - Tailscale ✅ (100.83.56.99). WSL 2.7.14 ✅ (DISM + MSI; `wsl --install` SSH'ta çalışmadı). Docker Desktop kuruldu.
    - Kod bundle ile host'ta (`C:\TradeBotpp`); `.env` rastgele PG parolası + Jev anahtarıyla hazır.
    - Docker Desktop 4.92 (oturum açılınca başlıyor) ✅.
    - SSH oturumunda Docker kimlik araması çalışmıyor ("Belirtilen oturum yok"). Bu yüzden servis kurulumu
      kullanıcı oturumundaki `TradeBot\Guncelle` görevinden yapılıyor (`host_guncelle.ps1`).
    - Host'ta `tradebot saglik`: dns 0,48 sn ✅, saat +0,09 sn ✅, PostgreSQL 17 + zincir ✅, disk 1.023 GB ✅,
      sırlar yalnız NVIDIA/Telegram eksik (beklenen). `kurulum.ps1` kontrolü: tümü OK.
    - **Yeniden başlatma testi ✅ (2026-09-25):**
      - Açılış → otomatik oturum → Docker → TradeBot servisleri kimse dokunmadan 57 sn'de geri geldi.
      - Otomatik oturum: Scryne'ın kararı B (kilitsiz). Parola Sysinternals Autologon ile LSA'da, kayıt
        defterinde düz metin yok. Windows Hello zorunluluğu kapatıldı.
    - **Bulgu: WSL2 sanal makine saati.** Windows saati doğruyken sanal makine açılıştan sonra 335 ms geride ölçüldü;
      chrony −3.643 ppm sapma raporladı. Çözüm: compose'a `saat` servisi (chrony, yalnız SYS_TIME). Sonrasında
      Binance'e göre +0,10 sn.

### Faz 2: Veri platformu (ilk dalga)
- **İşler:** İdempotent indiriciler; Nautilus Parquet kataloğu; ham veri hash'leri; enstrüman kaydı
  (lot, fiyat adımı, çarpan, para birimi, vade); piyasa takvimleri (BIST, NYSE, FX 24/5, kripto 7/24,
  tatiller, yaz saati); kurumsal işlemler (bölünme, bedelsiz, temettü) ve düzeltilmiş seri üretimi; PIT
  evren; kalite raporları.
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**
  - 2026-09-25 kod ✅ (41 test).
    - `tradebot.veri`: enstrüman kaydı, takvimler (kripto 7/24, FX 24/5 NY 17:00, XNYS, XIST exchange_calendars),
      ham depo (SHA-256, değişmez, sürümlü), bar depo (kanonik Parquet).
    - İndiriciler: Binance, Yahoo, Dukascopy. Kalite raporu, PIT evren tablosu, `tradebot veri …` komutları,
      compose `veri` servisi (01:30 UTC).
  - **Binance:** evren S3 listesinden 735 USDT sembolü (kaldırılanlar dahil; bugün işlemde 496). Her dosya
    yayınlanan SHA-256 ile doğrulanıyor. Saatlik tam geçmiş; dakikalık 10 büyük coin; funding.
  - **Yahoo:** OHLC bölünmeye göre geriye dönük düzeltilmiş. Yeni bölünme/bedelsiz görülünce tam yenileme.
    BIST evreni KAP şirket listesi (809; borsaistanbul.com bu ağdan erişilemiyor), geçmiş endeks üyeliği yok →
    yalnız kaldırılmış hisse yanlılığı kalıyor, raporda işaretli.
  - **Dukascopy:** 3 sn arayla bile 503 → 6 sn/istek + üstel bekleme, zaman bütçeli devam eden iş.
    - BID saatlik tam, ASK 3 yıl (spread), dakikalık EURUSD/XAUUSD/US500.
    - İçinde bulunulan ayın saatlik dosyası ay sonunda yayınlanıyor.
  - **LUNAUSDT** gibi aynı sembolde farklı varlık: 30+ günlük boşluk "kimlik kırılması şüphesi"; evren bu
    boşlukta enstrümanı dışarıda bırakır.
  - İlk yükleme host'ta başladı (2026-09-25 15:12 UTC, ~3,8 dosya/sn).
  - 2026-09-27 denetimi (`docs/Denetim-2026-09-27.md`): gece işi hiç tamamlanmamıştı (Dukascopy kaliteden önceydi,
    her dağıtımda kesiliyordu) → sıra düzeltildi, iş 11 dk'da bitiyor. Kalite raporu ilk kez yazıldı ve kalibre edildi:
    - Yahoo normalizasyonu: BIST kapalı günlerindeki bayat barlar atılır (bayramlar, 2023-02-08 iptal seansı), OHLC
      onarımı, imkânsız sıçra-dön barları atılır (±%25 ve geri; TRHOL 2025-01-10 ×102). Yahoo tam yenilendi.
    - XIST takvimine kanıtlı 3 ek seans (2006-01-09, 2009-05-01, 2010-09-09: 200+ hissede normal hacim).
    - Sıçrama uyarısı yalnız sıçra-dön (kötü tick izi), taban eşikli; borsanın kendi kaydında (Binance) bilgi.
    - Sonuç: 66 OK / 1252 UYARI / 90 HATA → **1242 OK / 165 UYARI / 1 HATA**. Kalan BIST uyarıları ±%20 civarı
      taban-dönüşler (eski limit; gerçek olabilir, işaretli kalır); Binance'te gerçek boşluk/kimlik kırılması.
  - **2026-09-27 ✅ Faz 2 tamam.** Dukascopy saatlik/dakikalık geçmişi gece işinin bütçeli son adımında sürüyor.

### Faz 3: Araştırma motoru
- **İşler:** Saf karar çekirdeği arayüzü; look-ahead bozma testi; piyasa başına maliyet modelleri
  (ücret, spread, kayma, swap, funding, BSMV); vektörel tarama; walk-forward, plato, rejim ayrımı, Deflated
  Sharpe; deneme defteri (PostgreSQL); Nautilus sarmalayıcısı ve parity testi; puan + kapı hesabı.
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**
  - 2026-09-25 ✅ (74 test).
    - `tradebot.cekirdek`: saf çekirdek. AST denetimiyle I/O yasak, gelecek-bozma testi.
    - `tradebot.arastirma`: piyasa başına maliyet, vektörel motor (sonraki açılışta dolum, aleyhte maliyet,
      dengeleme bandı), metrik ve kapılar.
    - Deneme defteri: plansız ya da kirli kodla koşu yok, PG'de değiştirilemez.
    - PSR/DSR (makale örneğiyle doğrulandı), walk-forward, plato, Nautilus köprüsü + kalıcı parity testi,
      `tradebot arastirma plan|tara`.
  - **Parity testi motorda gerçek bir hata yakaladı:** ağırlık kaymasının paydasında işlem maliyeti yoktu.
    Düzeltildi; Nautilus ile özkaynak artık 1e-5.
  - **İlk gerçek tarama** (plan 2026-09-25-trend-btc-gosterim, BTC 1d SMA 3×3, 9 deneme): önceden yazılmış
    ölçüte göre **FAIL**.
    - En iyi sma(10,100): +%32/yıl, DD −%69, en kötü hafta −%40 (kapılar geçmedi).
    - DSR 0,981, plato var, WF OOS +%30/yıl. Al-tut +%39/yıl, DD −%83.
    - Okuma: sinyal var, ama ya hep ya hiç boyut düşüşü olduğu gibi taşıyor → Faz 4 boyutlandırma.

### Faz 4: Risk motoru ve boyutlandırma
- **İşler:** Katman 1–4 (Nautilus risk motoru + bizim kontrollerimiz); oynaklık hedefli boyut; kol ve
  portföy seviyesinde yarım Kelly; 3x kod tavanı; frenler; acil durdurma ve onaylı yeniden başlatma;
  likidasyon mesafesi bekçisi.
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**
  - 2026-09-25 ✅ (105 test).
    - `cekirdek.boyut`: oynaklık hedefi (nedensel), yarım Kelly. `kaldirac_dogrula` her girişte: > 3x hata,
      ≥ 5x ayrı "yasak" hatası.
    - `risk.motor`: katman 1–4. Riski azaltan emir her durumda geçer; artıran emir tavanlara göre küçülür ya da
      reddedilir.
    - `PortfoyIzleyici`: fren UTC gün/hafta dönünce kalkar. Acil durdurma yalnız onayla kalkar (denetim izi, tepe
      sıfırlanır). Backtest frenleri uygular.
  - Testler iki hata yakaladı: dengeleme bandı değişim tespiti, lot yuvarlamasında kayan nokta.
  - **Tarama 2** (plan 2026-09-25-trend-btc-oynaklik, %40 vol hedefi + frenler, aile 18 deneme): **FAIL**.
    - Düşüş −%69 → −%25, ama acil durdurma 2019–20'de tetiklendi. Backtest sonrasını düz geçti (2020–26 +%0).
    - En kötü hafta −%15,8; günlük fren bir bar gecikmeli.
  - **Karar (araştırma modu):** acil durdurma araştırmada olay + kapı koşulu, kalıcı değil. Canlıda kalıcı
    (Final Doküman risk tablosu).
  - Onaylı yeniden başlatmanın CLI/Telegram yüzü canlı durum deposuyla birlikte Faz 7/9'da. Katman 5
    (bağımsız gözetmen) Faz 9'da.

### Faz 5: Turnuva — backtest dalgası 1
- **İşler:** Yedi ailenin ilk dalga piyasalardaki kolları; her aile için önce test planı; aşama 1–3;
  puan tablosu; paper'a giriş listesi.
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**
  - 2026-09-25: Ön kayıt `config/turnuva/dalga1.yaml` + `docs/turnuva/Dalga-1.md` (d0625fa).
    - Kol = strateji × piyasa grubu × zaman dilimi (çok enstrümanlı, eşit risk, kol %20 oynaklık).
    - 94 kol, A/B/KALDI ölçütü.
  - Hata yakalandı: kol ölçeği nakitten girişte patlıyordu. Ex-ante ölçekle düzeltildi (470df3a).
  - Ek: DSR dalga sonunda nihai deneme sayısıyla yeniden hesaplanır.
  - Bu dalgada yok, sırası yazılı: carry (kripto funding) 1b, gün içi kırılım 1c (Dukascopy dakikalık), olay tabanlı
    Faz 6 sonrası, pairs dalga 2.
  - 2026-09-26 ara sonuç (`docs/turnuva/Dalga-1-Ara-Sonuc.md`): 66 kol + carry, **A/B yok**.
    - En iyisi BTC+ETH trendi: Sharpe ~1, OOS yıllık +%13–17; DSR'da takılıyor.
    - CFD'de kaldıraçlı trend finansman yüzünden ekonomik değil.
  - Ölçüm hataları bulundu ve düzeltildi (ek 2): enstrüman tavanı, temettü.
  - Veri hataları bulundu ve düzeltildi: Dukascopy yavaşlığı → önce günlük dosyalar; yarıda kesilen yükleme artık
    indirileni kaybetmiyor.
  - Bekleyen: Dukascopy 1h/4h kolları (saatlik veri ~2 gün), dalga 1c (dakikalık), nihai DSR.
  - 2026-09-26 ✅ **Scryne kararı:** B (sermayesiz paper gözlem) için DSR şartı kalktı; A ve gerçek para için DSR ≥ 0,95
    aynen (`Dalga-1.md` ek 3).
    - Paper listesi (`docs/turnuva/Paper-Listesi.md`): `ma_yon@kripto_btc_eth@1h`, `tsmom@kripto_btc_eth@4h`, ikisi
      de B.
    - Kuyruk (veri geldikçe arka planda): Dukascopy 1h/4h, dalga 1c, nihai `sonlandir`.
    - Olay tabanlı aile Faz 6 sonrasına kaldı.
  - Dalga 2 araştırması Faz 6–7 ile paralel yürür (ön kayıtla).
  - 2026-09-27 not: dalga 1'in BIST kolları, sonradan temizlenen verilerle (kapalı gün bayat barları, imkânsız
    sıçra-dönler) koşmuştu. Hepsi KALDI; temiz veri kolları ancak iyileştirebilirdi, ama sonuca bakıp yeniden koşmak
    yeni denemedir (kural 10). Sonraki BIST dalgası temiz veriyle koşar.
  - 2026-09-28 altın M15 (`docs/turnuva/Altin-M15.md`, 32 deneme, satılan EA'nın profesyonel karşılığı): **hepsi KALDI.**
    EA gibi birleşik kol en kötülerden (Sharpe −1,43, OOS −%15,5/yıl); haber filtresinin katkısı yok.

### Faz 6: Zekâ katmanı (Jev)
- **İşler:** Spike 04-B: NVIDIA yükseltme modelinin seçimi (anahtar gelince). Metin toplayıcılar (ilk yayın zamanıyla); tek Jev servisi (uzun ömürlü istemci, kayıt,
  dondurma, maliyet/gecikme izleme); OpenAI uyumlu yükseltme istemcisi (NVIDIA) + yedek zinciri; A1–A6,
  B1–B4, D1–D4 rolleri; olay mesajlarının motora ve backtest'e bağlanması; C1–C4 özelliklerinin
  dondurulmuş ölçümü (sızıntı riski işaretli).
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**
  - 2026-09-26 iskelet ✅ (e82003f…3e3dd57, 164 test):
    - Tablolar `metin`, `jev_yargi`, `olay` (göç 0004, yalnız eklenir).
    - Binance duyuru toplayıcısı (sayfalı geçmiş; CMS 2 sn aralık, 429 ölçüldü).
    - Jev istemcisi (dondurma: sürüm + soru/girdi hash'i), OpenAI uyumlu yükseltme zinciri, A1 rolü, `tradebot zeka`
      komutları (`tur`, `calis`, `geri-doldur`, `vetolar`).
  - Vetolar backtest'te point-in-time maskeyle uygulanıyor (risk yalnız azalır). Dalga dosyasında `jev_veto` → Jev'li
    kol (`+jev`), A/B için.
  - Host'ta geri doldurma: 436 Binance duyurusu (2022-02 → 2026-09), 2982 A1 yargısı (hatasız), 186 veto, 60 belirsiz
    uyarı. Uyarılar yükseltme modeli tanımlı olmadığı için (`modeller: []`) belirsiz kuralına düştü.
    - Belirsizlerin Jev seçimi: 21 başka çift/ürün, 18 varlıkla ilgisiz, 11 delist, 5 USDT çifti, 3 olumlu, 2 dönüşüm.
  - Belirsiz yoldan gelen 22 vetonun 8'i yanlış çıktı (ADA, INJ, FLOKI, PHB, ALPACA: yalnız /TUSD–/BTC çifti; ALCX: yalnız
    margin; NOT ×2: "is NOT" kelimesi), 1 veto kaçırılmış (ADAUP). Olaylar yalnız eklenir: yanlış veto `kaldir` olayıyla
    kapanır (75b4ef8). Kaldırma riski artırır (kural 5/7): otomatik yol yok, yalnız onaylı `tradebot zeka veto-kaldir`.
    8 veto Scryne onayıyla geriye dönük kaldırıldı (2026-09-26, `kaldir` olayları 249–256). ALCX, ALPACA, PHB'nin sonraki
    gerçek delist vetoları (Jev ≥ 0,97) yerinde. `belirsizleri-yukselt` belirsiz kararları yükseltmeye sorar, yalnız
    veto ekler.
  - Spike 04-B ✅ (`docs/spikes/04-jev.md` §6): yükseltme zinciri `nemotron-3-ultra` → `glm-5.3`.
    - nemotron: 90 örnekte 89/90; 60 gerçek belirsiz vakada veto kararı 60/60. Gecikme medyan 12–19 sn (ücretsiz katman).
    - kimi-k3 alınmadı (geçersiz çıktı, kaçırılan veto).
  - `zeka` servisi host'ta canlı (2026-09-26 16:19 UTC). Binance 4 katalog, dakikada bir.
  - `belirsizleri-yukselt` (host): 60/60 yükseltildi (ilk koşuda 9'u 429; bekle-yeniden-dene eklendikten sonra tamam).
    - 1 yeni veto: ADAUP (kaçırılmış olan).
    - Yükseltmenin "veto gerekmez" dediği 8 belirsiz veto, Claude'un etiketindeki 8 yanlış vetoyla birebir aynı (olay
      1, 94, 105, 112, 122, 133, 144, 200). Kalan 14 belirsiz veto yükseltmeyle de doğrulandı.
  - Jev /TUSD ile /USDT çiftini karıştırıyor. A1 sorusunun sonraki sürümüne aday (yeni ölçümle).
  - **Kapsam kararı (2026-09-27, Scryne yetkiyi devretti: "tüm yetki sende"):** girdisi olmayan roller girdinin
    doğduğu faza taşındı; Faz 6 ile Faz 7 paralel.
    - A6 emir reddi → Faz 7 (emir akışı orada). D1 log triyajı, D2 rapor doğrulama, D4 Telegram → Faz 9.
    - A3 SEC 8-K → Faz 13 (tek hisse yok; evrende 26 büyük ETF). SEC basın RSS'i toplanıyor.
    - GDELT atlandı: Faz 7 piyasalarına katkısı zayıf. C4 (metin rejimi) ölçülürken gerekirse geri dönülür.
    - B3 sözleşme şartnamesi → Faz 8 (MT5/VİOP sözleşmeleri orada).
    - Gerekçe: darboğaz takvim. 12 haftalık paper turnuvası başlamadan hiçbir kol gerçek paraya aday olamaz;
      A1 canlı olduğu için paper'da eksik koruma yok.
  - KAP + A2 ✅ (2864535): servis kaynak→rol eşlemesiyle genel, karar kuralı ortak (`zeka.karar`).
    - Liste: KAP'ın kendi sorgu uç noktası (`disclosure/members/byCriteria`), gün başına tek istek, bütün BIST.
      Sıradan gün ~290, rapor sezonu ~1100 bildirim; sonuç kısıtı yok (ölçüldü).
    - Yapısal olarak veto olamayan konular atlanır: devre kesici, yatırımcı temerrüdü, pay alım satım, geri alım,
      borçlanma aracı… (sıradan günde %59).
    - Üretim metin biçimiyle spike'ın 44 KAP örneği yeniden: 44/44, yanlış veto 0 (`a2_bicim_dogrula.py`).
    - A2 vetosu süreli (pazar_tedbiri 30 gün, olumsuz_esasli 20 gün; keyfi başlangıç, A/B'de ölçülür).
      `kurumsal_islem` → `kurumsal` olayı (B1: Yahoo bölünme/bedelsiz çapraz kontrolü için; tüketici henüz yok).
    - Servis KAP'ı canlı izliyor. Geçmiş doldurma 2024-01-01'den başladı. Ölçülen hız günde ~94 takvim günü (KAP'ın
      hız sınırı, 3 sn aralık): toplama ~10 gün (~2026-10-07), ardından toplu yargılama.
    - 2026-09-27 denetimi: alınamayan bildirimler kalıcı delik oluyordu (24 saatte 72) → onarım turu; toplu yargılama
      parça parça (bellek). İş yeni kodla yeniden başlatıldı (`docs/Denetim-2026-09-27.md`).
  - **Kapsam kararı 2 (Claude, 2026-09-27; aynı ilke: girdisi olmayan rol girdinin doğduğu faza):**
    - A5 → Faz 8. Binance spot'ta borsa geneli kesintiyi bayat veri kontrolü ve A6 zaten karşılıyor; kaldıraçsız spot
      pozisyonda bakım penceresi özel risk değil. Toplanan 20 bakım duyurusunun ikisi de "system upgrade" diyor ama
      "Spot trading will not be affected" (anahtar kelime tuzağı: Jev'e uygun yargı). Asıl değer MT5 aracı kurum
      bildirimlerinde (tatil öncesi teminat artışı, işlem saati): örnekler orada doğar.
    - A4 pump/manipülasyon → küçük coin kolu paper'a girdiğinde (paper evreni BTC/ETH).
    - D3 → plan sayısı ~30'a ulaşınca (bugün 8; DSR sayımı aile bazında zaten doğru).
    - B2, B4 → C ölçümleriyle birlikte (tüketicileri C özellikleri).
  - C1 ✅ (`docs/olcum/C1-Veto-Etkisi.md`, plan `2026-09-27-c1-veto-etkisi`): A1 vetosu sonrası 7 gün BTC'ye göre
    medyan −%21 (%83 negatif) → koruma VAR; `token_delist` 30 günde −%58. A2 (kısmi KAP) 7 gün −%1 → ZAYIF;
    `olumsuz_esasli` etkisiz, `pazar_tedbiri` hafif koruma. A2 süreleri KAP geçmişi tamamlanınca yeni planla ölçülür.
  - C2 ✅ (`docs/olcum/C2-FOMC-Ton.md`, plan `2026-09-27-c2-fomc-ton`): 173 FOMC kararı, spike 4/4. Jev metni doğru okuyor
    (karar dağılımı gerçeğe yakın) ama Δton ne aynı gün tahvil tepkisini (t = −0,70) ne sonraki 5 günü açıklıyor →
    **özelliğe girmez**. Neden: ton değişimi piyasanın beklediği şey; sürpriz, beklenti verisi (fed funds vadeli) ister.
  - Faz 6'da kalan: B1 çapraz kontrolü (KAP geçmişi ~2026-10-07). Bitince Faz 6 kapanır.
  - B1 (tasarım, 2026-09-27): asıl değer düzeltilmemiş bölünmeyi yakalamak. Yahoo bir bedelsizi atlarsa seride kalıcı
    −%50 boşluk kalır; kalite raporunun sıçra-dön kuralı onu görmez (geri dönmüyor). Kural: BIST'te büyük, geri dönmeyen
    açılış boşluğu + ±30 gün içinde A2 `kurumsal` olayı + Yahoo'da bölünme kaydı yok → "düzeltilmemiş kurumsal işlem
    şüphesi" (kalite UYARI). KAP geçmişi tamamlanınca (~2026-10-07) kurulur ve geçmişte ölçülür.

### Faz 7: Paper canlı — kripto + ABD ETF
- **İşler:** Nautilus canlı düğümleri (paper); sermaye dağıtıcı (haftalık); Jev'li ve Jev'siz kol çiftleri;
  agresif gözlem kolu (ayrı defter); mutabakat; çökme sonrası yeniden kurulum; A6 emir reddi sınıflandırma
  (Faz 6'dan taşındı).
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**
  - 2026-09-27 paper düğümü canlı (compose `paper`, 02:20 UTC). Tasarım ve B→A terfi ölçütü: `docs/Paper-Tasarim.md`.
    - 5 paper kolu × Jev A/B = 10 sanal defter (kol başına 100.000 USDT), Binance canlı veri + Nautilus sandbox.
    - Karar backtest'in aynı fonksiyonlarıyla (`dengele_adim` backtest döngüsünden çıkarıldı); canlı ↔ backtest ağırlık
      yolu 1e-9 birebir (test); refaktör sonrası kayıtlı turnuva sonuçları gerçek veriyle birebir.
    - Defter PostgreSQL'de (göç 0006, yalnız eklenir); toparlanma, mutabakat, risk onayı.
    - Duman testi (ayrı SQLite): Nautilus v2 API farkları (Binance sağlayıcı config, StrategyId, kurucu yalnız config,
      on_quote) düzeltildi; ücret 10 bps.
  - Agresif gözlem kolu ✅ (9515479): kaynak kolların hedef ortalaması × tam Kelly (≈ 5), spot tavanlarıyla kırpılır
    (pratikte enstrüman başına %50); ayrı defter, dağıtıma girmez.
  - 2026-09-27 düzeltme (6c49fcd): düğüm işlem akışına da abone olduğu için sandbox geç gelen her işlemde "stale trade"
    uyarısı basıyordu (8 saatte ~286 bin satır, Docker log rotasyonu karar kayıtlarını siliyordu). Artık yalnız
    kotasyon; dolum alışta ask, satışta bid'e karşı. Deploy yeniden başlatmasında toparlanma canlıda çalıştı.
  - Sermaye dağıtıcı ✅ (Paper-Tasarim.md §Sermaye dağıtıcı): haftalık ERC (korelasyonlu) × küçültülmüş üstünlük →
    yarım Kelly ≤ 3x → kademe; `portfoy@kripto_btc_eth` kolu Jev'li kaynakların etkin hedeflerini katsayıyla işler.
    Hepsi B olduğu için bugün düz; gölge dağıtım her hafta `paper_dagitim`'e yazılıyor (ilk dolu hafta ~2026-10-26,
    28 gün geçmişle).
  - 2026-09-27 denetimi (`docs/Denetim-2026-09-27.md`):
    - Maliyet ölçümü ayrıldı: `gonderim_fiyati` (göç 0008) + `gecikmeli` bayrağı.
    - `paper_kol_olay` (göç 0009): portföy kolunda kalıcı acil durdurma + onaylı `paper acil-kaldir`; terfi olayı;
      mutabakat durdurması kayıtta.
  - ABD ETF: dalga 1'de A/B çıkan ETF kolu yok. Faz 7'nin ETF ayağı kol çıkarsa açılır; düğüm Binance'e özel.
  - Haftalık rapor ✅: `tradebot paper rapor`; bekçi her Pazartesi 00:30 UTC sonrası `data/rapor/paper-<hafta>.md`
    üretir, özeti Telegram'a gider. Kol başına getiri, düşüş, yürütme/gecikme maliyeti, fren/veto; Jev A/B; agresif ↔
    kaynak ortalaması; dağıtım.
  - A6 (Claude kararı, 2026-09-27): kod tarafı ✅. Aynı kol + enstrümanda art arda 3 ret → kol durur, olay + alarm
    (önceden ret olursa emir her saat körü körüne yeniden gidiyordu). Jev kısmı **Faz 8'e taşındı**. Gerekçeler:
    sandbox bugüne kadar hiç ret üretmedi; Binance ve MT5 reddi yapısal hata koduyla bildiriyor (eşleme kural işidir);
    Jev yalnız tanınmayan serbest metinde anlamlı, bunun spike'ı gerçek MT5 demo ret örnekleriyle yapılır.
  - Terfi değerlendirmesi ✅ (`canli/terfi.py`, Paper-Tasarim.md): bekçi haftalık; aynı dönemin backtest'i, gün hizalaması
    bar kapanışına (test: birebir izleyen paper'da takip hatası < 1e-9).
  - Çökme tatbikatı ✅ (2026-09-27, `docs/Denetim-2026-09-27.md`): süreç içinden çökme → Docker 13 sn'de kaldırdı →
    toparlanma → çift karar yok → mutabakat temiz. `docker kill` elle durdurma sayılır, çökme tatbikatı değildir.
  - **2026-09-27 ✅ Faz 7 tamam.** Bitti kriterinin hepsi karşılandı. ABD ETF ayağı açılmadı: dalga 1'de paper'a giren
    ETF kolu yok; çıkarsa veri/emir bağlantısı Faz 8'in özel bağlantı yoluyla eklenir. Paper çalışmaya devam ediyor;
    12 haftalık turnuva sayacı Faz 11'dir (başlangıç 2026-09-27).

### Faz 8: Özel bağlantılar — MT5 + BIST
- **İşler:** MT5 demo köprüsü (Windows tarafı; veri + simüle ya da demo emir); BIST gecikmeli veri
  bağlantısı ve simüle dolum; bu piyasaların takvim/maliyet modelleriyle paper kolları; B3 sözleşme şartnamesi
  okuma (Faz 6'dan taşındı); A6'nın Jev kısmı (Faz 7'den taşındı): MT5 ret kodları eşleme tablosu, tanınmayan serbest
  metin için Jev, gerçek demo ret örnekleriyle spike; A5 aracı kurum bildirimleri (Faz 6'dan taşındı: tatil öncesi
  teminat artışı, işlem saati değişikliği; demo hesaptan gelen gerçek bildirimlerle spike).
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**
  - 2026-09-27 kurum NCM Investment (VİOP ve forex aynı MT5'te). Scryne iki demo açtı (Forex 316722, VİOP 316723);
    iki taşınabilir terminal host'ta (`C:\TradeBot\mt5\forex`, `C:\TradeBot\mt5\viop`).
  - Spike 08 (`docs/spikes/08-mt5.md`): Python bağlantısı, sözleşme özellikleri ve geçmiş ✅. Altın `GOLD`; endeks/petrol
    vadeli (`ES6Z`, `GER40Z26`, `CL6X`); VİOP `F_XU030`, `F_USDTRY`, `XU30_YAKINVADE` (H1 2020'den: VİOP için ilk veri
    kaynağı). Barlar sunucu saatiyle (büyük olasılıkla UTC+3). Algo Trading `common.ini`'den açıldı.
  - Canlı spread + demo emir testi 2026-09-28 10:00 TR'de zamanlı (`Spike08` görevi).
  - 2026-09-27 köprü ✅ (`src/tradebot/mt5/kopru.py`, gözetmen `tools/host/mt5kopru.ps1`): hesap başına süreç, yalnız
    127.0.0.1; Docker `host.docker.internal` üzerinden okur (sabit DNS bu adı gizliyordu → `extra_hosts`). Kapanmış
    barlar UTC; sunucu farkı canlı tikten ölçüldü: **+3,0 sa** (2026-09-28). MT5 çağrıları tek işçide, takılırsa süreç
    kendini sonlandırır. Emir yolu yok. Bekçi `mt5` kontrolü (3 tur onay).
  - VİOP seansları barlardan: TR 09:40–18:10, endeks ve USD altında akşam 19:15–23:00 (`viop`, `viop_aksam` takvimleri).
  - MT5 verisi kataloğa (`tradebot veri mt5`, gece işinde): NCMFX GOLD/SILVER/FX/`ES!`/`NQ!`/`YM!`/`CL!`, VİOP
    `XU30_YAKINVADE` + vadeli kontratlar (önekle); 1m/1h/1d, ham yanıtlar HamDepo'da.
  - 2026-09-28 VİOP sürekli seri ✅ (`VIOP:XU030_SUREKLI`, `veri/viop.py`): kurumun yakın vade serisi geçişlerde +%7–15
    sıçrıyor (2024'te toplam +%50 sahte getiri). Geçiş günü spot getirisiyle ayıklanır; toplam getiri ham +%2.878 →
    ayarlı +%334. Backtest dönemi 2007-06 → 2025-10-31 (sonrasında 186 günlük kurum deliği).
  - 2026-09-28 VİOP 1 dalgası (`docs/turnuva/VIOP-1.md`, 30 deneme, dalga 1 aileleri): **hepsi KALDI.** En yakını tsmom
    (Sharpe 0,54, OOS +%0,7/yıl; OOS düşüş −%41 kapıyı geçemedi). VİOP maliyet modeli `VIOP:endeks_vadeli` eklendi.
  - Sırada: spike sonucu (spread, emir) → maliyet modelleri → VİOP/altın backtest dalgası (ön kayıtla) → canlı
    bar akışı (paper düğümüne MT5 kaynağı).

### Faz 9: Operasyon
- **İşler:** Bağımsız gözetmen (kalp atışı, özkaynak, pozisyon; motor donarsa kapatma); Telegram bot (3
  seviye, sessiz saat, D4 salt-okuma sorguları); günlük özet + haftalık turnuva raporu (D2 doğrulamalı);
  log triyajı (D1); yedekler; arıza tatbikatları.
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**
  - 2026-09-27 denetimiyle öne alındı: DB yedeği (compose `yedek`, ana bilgisayara kopya, geri yükleme denendi) ve
    bekçi (compose `saglik`: paper kalp atışı, gece işi, yedek yaşı, log hataları → Telegram).
  - 2026-09-27 Telegram canlı (`@ScryneTrade_bot`, yalnız Scryne'ın sohbeti). **D4 ✅** (`telegram_bot.py`, compose
    `telegram`, spike `research/spikes/07_d4`): doğal dil → Jev komut + kol + kol netliği; cevabı kod üretir.
    - Okuma (özet, kol durumu, dağıtım, vetolar, rapor): güven ≥ 0,5. Riski azaltan (kol/tümünü durdur): ≥ 0,7 +
      "evet" onayı (120 sn). Riski artıran serbest metinle asla: yalnız `/devam <kol>` + onay; acil kaldırma CLI.
    - Spike: komut 12/12 (tahmin sorusu → bilinmiyor; "tekrar başlat", "kaldıracı 3x yap" → riski artır). Jev iki
      kopyalı kolda tek kopyayı aşırı güvenle seçebiliyor: ayrı netlik Noul'u (6/8, hatalar güvenli yönde) + onay
      mesajında tam kol adı.
    - Elle durdurma (Telegram, ardışık ret) yeniden başlatmada korunur; mutabakat durdurması kalkar.
  - 2026-09-27 dış ölü adam ✅: bekçi her turda healthchecks.io'ya sinyal yollar, kritik kontrol HATA ise `/fail`.
  - 2026-09-27 bildirim seviyeleri ✅. İlk 3 saatte 8 mesajın 3'ü yanlış KRİTİK'ti: saat/DNS tek turluk sıçrama, 5 dk
    sonra kendiliğinden düzelmiş.
    - Saat ölçümü hatalıydı: Binance farkında t1 bağlantı kurulmadan alınıyordu. DNS + TLS süresi pencereye giriyor, kayma
      hep pozitif çıkıyordu (+2,1 sn). Artık açık bağlantıda 3 örnek alınıyor, en kısa gidiş-dönüş kullanılıyor
      (ana makinede +0,14 sn). NTP'de de ad çözümlemesi pencerenin dışında.
    - `DurumIzleyici`: ortam kontrolleri (DNS, saat, disk) art arda 3 tur (15 dk) aynı yönde kalmadan bildirilmez;
      histerezisli, düzelme de onay ister. Kritikler (paper, gece işi, yedek, veritabanı) ilk turda.
    - Sessiz saat 19–05 UTC (İstanbul 22–08): KRİTİK anında, UYARI/BİLGİ biriktirilir, sabah tek mesaj.
  - 2026-09-28 günlük özet ✅: bekçi her gün sessiz saat bitince (05:00 UTC) bir kez gönderir: sağlık, kolların 24
    saatlik ve başlangıçtan getirisi (Jev'li kopya yalnız A/B farkı olarak), işlem/fren, yeni Jev olayları, gece işi.
  - Faz 9'da kalan: motor donarsa pozisyon kapatma (bağımsız gözetmen), D1 Jev log triyajı, arıza tatbikatları.

### Faz 10: Web pano
- **İşler:** `DESIGN.md` (create-design-md + ui-ux-pro-max); FastAPI + arayüz; frontend denetim pasları.
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**

### Faz 11: Paper turnuvası — 12 hafta
- **İşler:** Sistem kendi başına çalışır; haftalık raporlar okunur; arızalar düzeltilir; kademeli sermaye
  (4/8/12 hafta); gerçek maliyet (spread, maker dolum oranı) ölçülür; Jev katkısı raporlanır.
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**
  - Sayaç 2026-09-27'de başladı (paper düğümü canlı, Faz 7 kapandı); 12 hafta ~2026-12-20. Faz 8–10 bununla paralel.
  - Takvim: ilk gölge dağıtım ~2026-10-26 (28 gün); ilk olası terfi ~2026-11-22 (56 gün, %50 kademe).

### Faz 12: Gerçek para (koşullu)
- **İşler:** Scryne kararı; aracı kurum/borsa seçimi; anahtar güvenliği; vergi; sabit tavanlı mikro
  sermaye; paper ↔ gerçek sapma ölçümü; otonomi seviyesinin yeniden konuşulması.
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**

### Faz 13: Sonraki dalgalar (koşullu)
- **İşler:** Ücretli veriyle ABD tek hisseleri; Databento ile CME vadelileri; VİOP; gerekirse IB bağlantısı;
  A3 SEC 8-K rolü (Faz 6'dan taşındı).
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**
