---
proje: TradeBot
created: 2026-09-24
type: roadmap
status: taslak (Final Doküman onaylanınca kesinleşir)
---
# TradeBot — Roadmap

Durum sütunu session-start hook'u tarafından otomatik okunur — format bozulmasın:
⏳ Bekliyor / 🔄 Devam Ediyor / ✅ Tamamlandı.

| Faz | Adı | Durum | Bitti Kriteri |
| --- | --- | --- | --- |
| 0 | Riskli kararların spike'ları | ⏳ Bekliyor | Jev haber vetosu, veri+CCXT bağlantısı ve çekirdek kıyası spike raporları `docs/spikes/` altında; Final Doküman kararları bunlara dayanıyor |
| 1 | Temel ve veri katmanı | ⏳ Bekliyor | `uv` projesi, testler yeşil; BTC/ETH + top-20 için 1h/4h/1d veri, funding ve PIT evren indirilebiliyor; kalite raporu |
| 2 | Backtest motoru | ⏳ Bekliyor | Tek karar fonksiyonu, sonraki bar dolumu, aleyhte maliyet; look-ahead bozma ve determinizm testleri geçiyor; walk-forward + Deflated Sharpe raporu |
| 3 | Boyutlandırma ve risk motoru | ⏳ Bekliyor | Oynaklık hedefi, yarım Kelly kaldıraç, 3x sabit tavan, ≥5x imkânsız (testli); kayıp frenleri ve kill switch testli |
| 4 | Strateji turnuvası (backtest) | ⏳ Bekliyor | Aday aileler 1h/4h/1d'de maliyet dahil ölçüldü; deneme sayısı kayıtlı; paper'a girecek adaylar yazılı ölçütle seçildi |
| 5 | Paper canlı altyapı | ⏳ Bekliyor | Seçilen adaylar paper'da 7/24 koşuyor; mutabakat, çökme sonrası toparlanma, Telegram alarmları çalışıyor; canlı ↔ backtest kararları birebir |
| 6 | Jev katmanı | ⏳ Bekliyor | Haber vetosu gölgede → aktif; log triyajı çalışıyor; olay özellikleri dondurulmuş veriyle ölçüldü (değer katıyor/katmıyor raporu) |
| 7 | Web pano | ⏳ Bekliyor | DESIGN.md dolu; PnL, pozisyon, strateji karnesi, sağlık ve veto geçmişi görünüyor |
| 8 | Mikro gerçek para (koşullu) | ⏳ Bekliyor | Borsa kararı + API anahtarı (çekim kapalı, IP kısıtlı) + Scryne onayı; sabit tavanlı küçük sermayeyle gerçek emir; ücret/kayma ölçüldü |
| 9 | Ölçekleme ve kaldıraç (koşullu) | ⏳ Bekliyor | Önceden yazılmış ölçütle sermaye artışı; gerçek parada kaldıraç yalnız hukuki netlik + ölçülmüş Kelly ile |

## Faz Detayları

### Faz 0: Riskli kararların spike'ları
- **İşler:**
  - `01_kaldirac_kirilim` ✅ (araştırma sırasında yapıldı: ≥ 5x her yapılandırmada iflas).
  - `02_jev_haber_vetosu`: 20–50 gerçek Binance duyurusu ve kripto haberiyle `ts.py` üzerinden soru seti
    (varlık, olay tipi, resmi kaynak, doğrulanmış olay, ciddiyet). Güven–doğruluk tablosu ve eşik önerisi.
  - `03_veri_ccxt`: Binance public data indirme hızı ve boyutu; CCXT ile Binance ve BtcTurk public uçları
    (fiyat, emir defteri, ücret bilgisi); Binance TR API erişimi doğrulaması.
  - `04_cekirdek_kiyas`: aynı basit trend stratejisi Freqtrade'de ve ince kendi çekirdekte. Kurulum süresi,
    portföy ağırlığı desteği, Jev ve dondurulmuş özellik entegrasyonu.
- **Bitti Kriteri:** her spike için kısa rapor ve Final Doküman'a giden karar.
- **Notlar:**

### Faz 1: Temel ve veri katmanı
- **İşler:** Python 3.12 + `uv`, proje yapısı, pytest; veri indirici (idempotent), Parquet deposu, kalite
  kontrolleri (eksik bar, sıçrama, zaman damgası), funding geçmişi, listeleme tarihiyle PIT evren.
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**

### Faz 2: Backtest motoru
- **İşler:** vektörel araştırma yolu + olay tabanlı doğrulama yolu aynı karar fonksiyonunu çağırır; ücret,
  spread, kayma, funding modeli; walk-forward çerçevesi; deneme defteri (her backtest koşusu sayılır);
  Deflated Sharpe.
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**

### Faz 3: Boyutlandırma ve risk motoru
- **İşler:** oynaklık hedefli ağırlık; strateji başına Kelly tahmini ve yarısı; kaldıraç tavanı (3x) kodda
  sabit ve testli; günlük/haftalık kayıp freni, maksimum düşüş kill switch'i, likidasyon mesafesi bekçisi;
  riski azaltan otomatik, izni artıran onaylı.
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**

### Faz 4: Strateji turnuvası (backtest)
- **İşler:** aday aileler: kırılım (Donchian/Bollinger), oynaklık hedefli trend, kesitsel momentum, kısa
  vadeli dönüş (maker varsayımıyla ve olmadan), funding carry. Zaman dilimleri 1h/4h/1d. Evren BTC/ETH →
  top-20. Her aile için önce bir satırlık test planı, sonra koşu.
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**

### Faz 5: Paper canlı altyapı
- **İşler:** zamanlayıcı döngü; paper aracı (gerçek fiyat/spread, aleyhte dolum); idempotent emir arayüzü;
  mutabakat; durumun yeniden kurulması; Telegram bildirimleri; 7/24 çalışma (Açık Soru 3).
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**

### Faz 6: Jev katmanı
- **İşler:** haber toplayıcı; tek uzun ömürlü TypeSafe istemcisi; veto kuralı (kodda eşik); gölge modda
  kayıt → aktif; log triyajı; tarihsel haberlerin dondurulmuş yargıları (model sürümü + hash) ve olay
  özelliklerinin backtest ölçümü (eğitim kesimi sızıntısı işaretli).
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**

### Faz 7: Web pano
- **İşler:** `DESIGN.md` (create-design-md + ui-ux-pro-max), FastAPI + web arayüzü, yalnız yerel ağ.
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**

### Faz 8: Mikro gerçek para (koşullu)
- **İşler:** borsa kararı; alt hesap; yalnız işlem izni olan, çekimi kapalı, IP kısıtlı anahtar; sabit
  sermaye ve kayıp tavanı; ilk emir Scryne'ın açık onayıyla; gerçek ücret ve kaymanın paper ile kıyası.
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**

### Faz 9: Ölçekleme ve kaldıraç (koşullu)
- **İşler:** önceden yazılmış ölçütle sermaye artışı; gerçek parada kaldıraç (≤ yarım Kelly, ≤ 3x);
  gerekirse yeni piyasalar (BIST/Algolab).
- **Bitti Kriteri:** tablodaki gibi.
- **Notlar:**
