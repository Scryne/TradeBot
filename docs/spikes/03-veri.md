---
spike: 03
konu: İlk dalga veri kaynakları — erişim, hız, kapsam, kalite
tarih: 2026-09-25
sonuc: GEÇTİ (tüm ilk dalga kaynakları ücretsiz ve kullanılabilir; indirici kuralları belirlendi)
kod: research/spikes/03_veri/ (olcum.py, olcum2.py) · research/spikes/02_nautilus/parity_1m.py
---
# Spike 03: Veri kaynakları

**Soru:** İlk dalga (kripto, FX/emtia/endeks, ABD ETF, BIST + metin kaynakları) ücretsiz kaynaklarla gerçekten
kurulabilir mi? Hangi tuzaklar var?

**Hüküm: GEÇTİ.** Her piyasa için anahtarsız ya da ücretsiz anahtarla çalışan bir kaynak var. Asıl iş
kaynakları bulmak değil, **nazik ve doğru indirici** yazmak. §3'teki kurallar Faz 2'nin şartnamesidir.

İki turda ölçüldü:
- Birinci tur Windows'ta yerel çalıştı (24 ölçüm, 20 başarılı).
- İkinci tur Docker'da public DNS ile çalıştı, DNS etkisini ayırmak için.

## 1. Sonuç tablosu

| Kaynak | Kapsam | Erişim | Hız / boyut | Kalite ve tuzak |
| --- | --- | --- | --- | --- |
| **Binance arşivi** (data.binance.vision) | Spot mum 1 dk→, funding (UM) | Anahtarsız | ETH 1 dk bir ay: 2 MB zip, 44.640 satır, 8 sn (DNS'siz) | Eksik dakika 0. **2025'ten itibaren zaman damgası mikrosaniye, öncesi milisaniye** |
| Binance `exchangeInfo` | 3.713 sembol, 749 USDT çifti (496'sı işlemde) | Anahtarsız | 2 sn | **Listeleme tarihi yok.** PIT evren için sembolün ilk mum tarihi kullanılır |
| Binance duyuruları (CMS API) | Delist, listeleme, bakım, haber, diğer (katalog başına 20) + gövde | Anahtarsız | 0,1 sn | `pageSize` 20 çalışıyor, 12 → 400. Gövde zengin metin JSON |
| **Dukascopy** | FX, XAU, US500, DAX, Brent, WTI, USDTRY… | Anahtarsız HTTP | **Sıkı hız sınırı:** ~5 hızlı istekten sonra 503, sonra geçici IP engeli (bağlantı reddi) | Dakikalık mum: gün başına 1 dosya. **Saatlik mum: ay başına 1 dosya (744 mum, hafta sonu dahil)**. Fiyat tamsayı × point |
| **Yahoo grafik uç noktası** | ABD ETF'leri 1993→, BIST 2000→, XU100 1997→ | Anahtarsız (resmî olmayan uç nokta) | 1–3 sn | **`range=max` günlük yerine AYLIK döndürüyor** → `period1/period2` ile günlük tam (SPY 8.471 gün). 1 dk yalnız son ~8 gün, 1 saat son 2 yıl. BIST bedelsiz sermaye artırımları "split" olarak geliyor (THYAO: 2009 500:100 …) |
| Stooq CSV | — | **Kapandı:** JavaScript doğrulaması istiyor | — | Kullanılmaz |
| **borsapy** | BIST günlük (10 yıl), 1 dk (son 5 gün), KAP listesi + gövde, VİOP, ekonomik takvim, TCMB/EVDS | Anahtarsız (EVDS hariç) | 1–12 sn | `period=max` günlükte hata, `10y` çalışıyor. KAP gövdesi ham HTML döner, metin ayıklanmalı. Canlı akışı resmî olmayan TradingView WebSocket'i |
| **KAP** (borsapy üzerinden) | Hisse başına son 20 bildirim, tam metin | Anahtarsız | ~0,3 sn/bildirim | Başlıklar çok genel ("Özel Durum Açıklaması"), anlam gövdede. Jev bunu iyi ayırıyor (Spike 04) |
| **SEC EDGAR** | Şirket başvuruları, 8-K, kabul zamanı | Anahtarsız, kimlikli User-Agent şart | 0,3 sn | `acceptanceDateTime` var → ilk yayın zamanı |
| FRED CSV | Makro seriler | Anahtarsız | 1 sn (DNS'siz) | — |
| Fed basın RSS | FOMC metinleri | Anahtarsız | 0,1 sn | — |
| TCMB | Duyurular | HTML; RSS yok | — | Karar metni için HTML ayıklama ya da EVDS (anahtar) |
| GDELT DOC API | Küresel haber | Anahtarsız | — | **429:** 5 sn'de 1 istek kuralı sıkı. Toplu kullanım için GDELT'in dosya dökümleri tercih edilir |
| Tiingo / Massive / Alpaca veri | ABD | **Ücretsiz anahtar gerekir** | Ölçülmedi | Alpaca'nın ücretsiz planı IEX akışı; paper hesabı herkese açık (Spike 05) |

## 2. Bu makineye özgü: DNS

Ev router'ının DNS'i IPv6 kaydı olmayan alan adlarında 5–15 sn gecikiyor. data.binance.vision,
stream.binance.com, datafeed.dukascopy.com ve fred.stlouisfed.org bundan etkileniyor. Birinci turdaki yavaşlığın
(Binance arşivi 13 sn, Dukascopy gün başına 10 sn) çoğu buydu. Konteynerde `--dns 1.1.1.1` ile ortadan kalkıyor.
Spike 02'deki karar aynen geçerli: **servisler konteyner DNS'i ile çalışır.**

## 3. Faz 2 indirici kuralları (bu spike'tan)

1. **Zaman birimi tespiti:** Binance arşivinde değer > 10¹⁴ ise mikrosaniye. Bütün zamanlar UTC ms'ye
   normalize edilir. Test: 2024 ve 2026 dosyası aynı ölçekte.
2. **Yahoo günlük** yalnız `period1/period2` ile istenir. `range=max` yasak (aylığa düşüyor). Temettü ve
   bölünme olayları (`events=div,splits`) ayrıca saklanır. BIST bedelsiz artırımları bu olaylardan gelir,
   B1 (Jev) ile KAP'tan çapraz doğrulanır.
3. **Dukascopy nazik indirici:**
   - Tek HTTPS oturumu, istekler arası ≥ 3 sn.
   - 503'te üstel geri çekilme, bağlantı reddinde 5+ dk bekleme.
   - Saatlik veri aylık dosyalardan: 20 yıl ≈ 240 istek ≈ 12 dk/sembol.
   - Dakikalık veri yalnız yürütme doğrulaması için son 2–3 yıl: ≈ 780 istek ≈ 40 dk/sembol, gece işi.
   - Hafta sonu ve tatil mumları takvimle ayıklanır (hacim 0).
4. **Evren PIT:** Binance'te listeleme tarihi = ilk mum. Delist tarihi = son mum + duyuru arşivi. BIST'te
   Yakın İzleme Pazarı ve kottan çıkma KAP'tan (Jev A2).
5. **Metin kaynaklarında ilk yayın zamanı:** Binance `releaseDate`, SEC `acceptanceDateTime`, KAP gönderim
   tarihi (saniye hassasiyetli). Backtest kesmesi bu alana göredir.
6. **Hız sınırı disiplini:** GDELT 5 sn/istek, Dukascopy ≥ 3 sn, Yahoo ölçülü (günlük toplu iş, sembol başına
   1 istek). Hepsi yerel önbellekli ve idempotent.
7. **Resmî olmayan kaynaklar** (Yahoo, borsapy/TradingView) her an değişebilir. Her kaynak için bir "canlılık
   testi" gözetmende çalışır, bozulursa alarm verir. Kritik veride ikinci kaynak yedektir: BIST günlük için
   Yahoo ↔ borsapy.

## 4. Kararlar (Final Doküman'a)

- İlk dalga veri kaynakları kesinleşti: Binance arşivi + REST, Dukascopy (saatlik aylık, dakikalık son 2–3
  yıl), Yahoo (ETF ve BIST günlük), borsapy (BIST yedek + KAP + VİOP), SEC EDGAR, Fed RSS, FRED.
  GDELT dosya dökümleriyle.
- Stooq elendi.
- Tiingo, Massive ve Alpaca veri anahtarları ancak gerekirse alınır (Alpaca paper, Spike 05).
