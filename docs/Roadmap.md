---
proje: TradeBot
created: 2026-09-24
updated: 2026-09-24
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
| 1 | Altyapı ve host | 🔄 Devam Ediyor | Host (WSL2 + Docker + Tailscale + SSH, 7/24 ayarları) hazır; `uv` projesi, Compose iskeleti, PostgreSQL, sır yönetimi, log düzeni; testler yeşil |
| 2 | Veri platformu (ilk dalga) | ⏳ Bekliyor | Kripto, Dukascopy, ABD ETF, BIST günlük verileri katalogda; enstrüman kaydı + takvimler + kurumsal işlemler; PIT evren; kaynak başına kalite raporu |
| 3 | Araştırma motoru | ⏳ Bekliyor | Saf karar çekirdeği; piyasa başına maliyet modelleri; vektörel tarama; walk-forward + plato + DSR; deneme defteri; vektörel ↔ Nautilus parity testi geçiyor |
| 4 | Risk motoru ve boyutlandırma | ⏳ Bekliyor | 5 katman kodlu ve testli; 3x tavan ve ≥ 5x imkânsızlığı testli; yarım Kelly; frenler, acil durdurma, onaylı yeniden başlatma |
| 5 | Turnuva — backtest dalgası 1 | ⏳ Bekliyor | 7 aile × ilk dalga piyasalar huni aşama 0–3'ten geçti; puan tablosu; paper'a girecek kollar yazılı ölçütle seçildi |
| 6 | Zekâ katmanı (Jev) | ⏳ Bekliyor | Toplayıcılar (KAP, SEC, Binance, RSS, merkez bankaları, GDELT); Jev servisi + NVIDIA yükseltme; A, B, D rolleri çalışıyor; yargılar dondurulabiliyor; C özellikleri ölçüldü |
| 7 | Paper canlı — kripto + ABD ETF | ⏳ Bekliyor | Nautilus düğümleri paper'da 7/24; sermaye dağıtıcı; Jev'li/Jev'siz kollar; agresif gözlem kolu; mutabakat ve toparlanma testli |
| 8 | Özel bağlantılar — MT5 (FX/emtia/endeks) + BIST | ⏳ Bekliyor | MT5 demo köprüsü ve BIST (gecikmeli) paper bağlantısı çalışıyor; bu piyasaların kolları paper turnuvasında |
| 9 | Operasyon: gözetmen, Telegram, raporlar | ⏳ Bekliyor | Bağımsız gözetmen motor donmasını yakalıyor (tatbikatla); Telegram 3 seviye; günlük özet + haftalık turnuva raporu; log triyajı; yedek |
| 10 | Web pano | ⏳ Bekliyor | DESIGN.md dolu; PnL, pozisyon, turnuva tablosu, veto geçmişi, sağlık; Tailscale üzerinden telefondan erişim |
| 11 | Paper turnuvası — 12 hafta | ⏳ Bekliyor | 12 hafta kesintisiz paper; kademeli sermaye çalıştı; hangi kolların kapıyı geçtiği ve Jev katkısı raporlandı; maliyet varsayımları ölçüldü |
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
    - Kalan: yeniden başlatma dayanıklılık testi (Scryne onayıyla) ve otomatik oturum kararı.

### Faz 2: Veri platformu (ilk dalga)
- **İşler:** İdempotent indiriciler; Nautilus Parquet kataloğu; ham veri hash'leri; enstrüman kaydı
  (lot, fiyat adımı, çarpan, para birimi, vade); piyasa takvimleri (BIST, NYSE, FX 24/5, kripto 7/24,
  tatiller, yaz saati); kurumsal işlemler (bölünme, bedelsiz, temettü) ve düzeltilmiş seri üretimi; PIT
  evren; kalite raporları.
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**

### Faz 3: Araştırma motoru
- **İşler:** Saf karar çekirdeği arayüzü; look-ahead bozma testi; piyasa başına maliyet modelleri
  (ücret, spread, kayma, swap, funding, BSMV); vektörel tarama; walk-forward, plato, rejim ayrımı, Deflated
  Sharpe; deneme defteri (PostgreSQL); Nautilus sarmalayıcısı ve parity testi; puan + kapı hesabı.
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**

### Faz 4: Risk motoru ve boyutlandırma
- **İşler:** Katman 1–4 (Nautilus risk motoru + bizim kontrollerimiz); oynaklık hedefli boyut; kol ve
  portföy seviyesinde yarım Kelly; 3x kod tavanı; frenler; acil durdurma ve onaylı yeniden başlatma;
  likidasyon mesafesi bekçisi.
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**

### Faz 5: Turnuva — backtest dalgası 1
- **İşler:** Yedi ailenin ilk dalga piyasalardaki kolları; her aile için önce test planı; aşama 1–3;
  puan tablosu; paper'a giriş listesi.
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**

### Faz 6: Zekâ katmanı (Jev)
- **İşler:** Spike 04-B: NVIDIA yükseltme modelinin seçimi (anahtar gelince). Metin toplayıcılar (ilk yayın zamanıyla); tek Jev servisi (uzun ömürlü istemci, kayıt,
  dondurma, maliyet/gecikme izleme); OpenAI uyumlu yükseltme istemcisi (NVIDIA) + yedek zinciri; A1–A6,
  B1–B4, D1–D4 rolleri; olay mesajlarının motora ve backtest'e bağlanması; C1–C4 özelliklerinin
  dondurulmuş ölçümü (sızıntı riski işaretli).
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**

### Faz 7: Paper canlı — kripto + ABD ETF
- **İşler:** Nautilus canlı düğümleri (paper); sermaye dağıtıcı (haftalık); Jev'li ve Jev'siz kol çiftleri;
  agresif gözlem kolu (ayrı defter); mutabakat; çökme sonrası yeniden kurulum.
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**

### Faz 8: Özel bağlantılar — MT5 + BIST
- **İşler:** MT5 demo köprüsü (Windows tarafı; veri + simüle ya da demo emir); BIST gecikmeli veri
  bağlantısı ve simüle dolum; bu piyasaların takvim/maliyet modelleriyle paper kolları.
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**

### Faz 9: Operasyon
- **İşler:** Bağımsız gözetmen (kalp atışı, özkaynak, pozisyon; motor donarsa kapatma); Telegram bot (3
  seviye, sessiz saat, D4 salt-okuma sorguları); günlük özet + haftalık turnuva raporu (D2 doğrulamalı);
  log triyajı (D1); yedekler; arıza tatbikatları.
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**

### Faz 10: Web pano
- **İşler:** `DESIGN.md` (create-design-md + ui-ux-pro-max); FastAPI + arayüz; frontend denetim pasları.
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**

### Faz 11: Paper turnuvası — 12 hafta
- **İşler:** Sistem kendi başına çalışır; haftalık raporlar okunur; arızalar düzeltilir; kademeli sermaye
  (4/8/12 hafta); gerçek maliyet (spread, maker dolum oranı) ölçülür; Jev katkısı raporlanır.
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**

### Faz 12: Gerçek para (koşullu)
- **İşler:** Scryne kararı; aracı kurum/borsa seçimi; anahtar güvenliği; vergi; sabit tavanlı mikro
  sermaye; paper ↔ gerçek sapma ölçümü; otonomi seviyesinin yeniden konuşulması.
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**

### Faz 13: Sonraki dalgalar (koşullu)
- **İşler:** Ücretli veriyle ABD tek hisseleri; Databento ile CME vadelileri; VİOP; gerekirse IB bağlantısı.
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**
