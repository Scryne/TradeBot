---
spike: 02
konu: NautilusTrader v2 — kurulum, backtest, parity, özel bağlantı, canlı paper
tarih: 2026-09-25
sonuc: GEÇTİ (koşullarla)
kod: research/spikes/02_nautilus/
---
# Spike 02 — NautilusTrader v2

**Soru:** NautilusTrader v2 (sürüm adayı) motorumuz olabilir mi? Windows/Docker'da çalışıyor mu, saf karar
çekirdeğimizle aynı kararları veriyor mu, kendi bağlantımızı yazabiliyor muyuz, canlı paper döngüsü
çalışıyor mu?

**Hüküm: GEÇTİ, dört koşulla (§5).** Motor NautilusTrader v2 olarak kesinleşti. Yedek plana (LEAN) gerek yok.

## 1. Kurulum

| | Sonuç |
| --- | --- |
| Sürüm | `nautilus-trader==2.0.0rc5` (15.09.2026). v1'in son sürümü 1.231.0 (02.08.2026) |
| Windows (yerel) | ✅ Hazır `cp312-win_amd64` paketi; `uv add` sorunsuz |
| Docker (Linux) | ✅ `python:3.12-slim` + pip; imaj 1,1 GB, derleme 52 sn |
| Bağımlılık notu | numpy ve pandas v2'nin zorunlu bağımlılığı değil, ayrıca eklenmeli |

## 2. Backtest ve parity (`parity.py`, `parity_1m.py`)

Saf karar fonksiyonu `karar.hedef_agirlik` (SMA20/100, long-only) iki yoldan çalıştırıldı: vektörel yol
(tek çağrı) ve Nautilus sarmalayıcısı (her barda o ana kadarki geçmişle).

**Gelecek-bozma testi:** t sonrası veri 200 kez rastgele bozuldu, t'ye kadarki kararlar değişmedi → ✅.

**Karar parity'si:**

| Veri | Bar | Karar serisi | İşlem sayısı |
| --- | --- | --- | --- |
| BTCUSDT 1d (2020→) | 2.458 | ✅ birebir | 25 = 25 |
| BTCUSDT 4h (2022→) | 10.367 | ✅ birebir | 127 = 127 |
| SPY 1d (10 yıl, Yahoo) | 2.513 | ✅ birebir | 23 = 23 |

**Dolum semantiği: kritik bulgu.** Nautilus'ta bar verisiyle "sonraki bar açılışında dolum" modu **yok**
(dokümanda açıkça yazıyor). `on_bar`'dan verilen piyasa emri **sinyal barının kapanış fiyatından** dolar.

| Veri | Sinyal kapanışında dolum (Nautilus varsayılanı) ile sonraki açılış farkı (son özkaynak) |
| --- | --- |
| BTCUSDT 1d | %0,018: 7/24 piyasada kapanış ≈ sonraki açılış |
| BTCUSDT 4h | %0,029 |
| SPY 1d | **%3,16**: seans boşlukları; kapanıştan sonra o fiyattan işlem gerçekte yapılamaz → iyimser |

Yalnız bar verisiyle gecikme modeli kullanmak da çözüm değil: dolum sonraki barın **kapanışına** kayıyor.

**Çözüm (doğrulandı): günlük karar + 1 dakikalık yürütme verisi.**
- Strateji, Nautilus'un 1 dk veriden iç olarak topladığı günlük barı görür.
- Emir 1 ms gecikmeyle borsaya ulaşır ve sinyalden sonraki ilk dakikada dolar.
- Test verisi: BTCUSDT, 12 ay, 525.600 dk bar.

| Referans | Karar | İşlem | Dolum fiyatı farkı | Son özkaynak farkı |
| --- | --- | --- | --- | --- |
| Vektörel: ertesi günün ilk dakikası | ✅ | 3 = 3 | %0,0000 | **%0,0000** |
| Vektörel: ertesi gün açılışı | ✅ | 3 = 3 | ort. %0,0046 | %0,014 |

**Performans:** 525.600 bar yükleme 0,5 sn + koşu 0,7 sn. 10 bin 4 saatlik bar 2,3 sn.

## 3. Özel bağlantı (`canli.py` → `YahooVeriIstemcisi`)

- v2'de saf Python bağlantısı yazılabiliyor: `nautilus_trader.live.clients.MarketDataClient` ve
  `DataClientFactory`, düğüme `add_data_client("YAHOO", Fabrika, DataClientConfig())` ile ekleniyor.
- Yazılan istemci Yahoo grafik uç noktasını 15 sn'de bir yokluyor, yalnız kapanmış 1 dk barları yayıyor.
  BIST (.IS) ve MT5 köprüsü için şablon bu.
- Canlıda bağlandı ve 4 dakikada 5 bar yaydı ✅.
- Aynı yapıda `ExecutionClient` de var: emir, iptal ve mutabakat raporları. MT5 emir köprüsü buna göre
  yazılır.

## 4. Canlı paper döngüsü (Docker)

Tek düğümde:
- Binance public veri (yerleşik bağlantı, anahtarsız),
- bizim özel istemcimiz,
- sandbox yürütme (yerel eşleştirme motoru, 10.000 USDT simüle).

Test süresi 4 dakika.

| | Sonuç |
| --- | --- |
| Binance 1 dk bar | 4 ✅ |
| Özel istemci barı | 5 ✅ |
| Paper dolum | BUY 0,001 @ 84.426,84 · SELL 0,00014 @ 84.450,92 + 0,00086 @ 84.450,91: satış gerçek emir defterinde iki kademeden doldu ✅ |
| Komisyon | Enstrümandan (taker %0,1) ✅ |
| Durdurma | `node.handle().stop()` ile temiz kapanış ✅ |

## 5. Koşullar: bunlar olmadan kullanılmaz

1. **Yürütme verisi politikası.**
   - Nautilus'ta gerçekçi doğrulama için 1 dk (ya da daha ince) yürütme verisi gerekir.
   - Bu veri olmayan piyasalarda (ücretsiz BIST günlük) Nautilus backtest'i seanslı piyasada iyimser çıkar.
     Orada **kendi vektörel motorumuz** (sonraki açılış kuralı) bağlayıcıdır, Nautilus yalnız paper/canlı
     için kullanılır.
   - Parity testi projede kalıcı test olur.
2. **Sürüm sabitleme ve ince sarmalayıcı.** v2 hâlâ değişiyor. rc5 ile ana daldaki resmi örnek arasında
   farklar görüldü: `MakerTakerFeeModel` parametreleri, `subscribe_trade_ticks` → `subscribe_trades`,
   `LoggerConfig` alanları, `run_async` durdurma yolu.
   - Sürüm tam sabitlenir (`==2.0.0rcN` / `==2.0.x`).
   - Yükseltme, parity testi geçerek yapılan ayrı bir karardır.
   - Strateji mantığı Nautilus'a değil saf çekirdeğe yazılır. Nautilus'a dokunan kod ince sarmalayıcılarda
     toplanır.
3. **DNS.** Bu makinede IPv6 kaydı olmayan adların çözümlemesi 5–15 sn sürüyor (`stream.binance.com` 11 sn,
   konteynerde 15 sn). Nautilus'un WebSocket zaman aşımı 5 sn, bu yüzden Binance bağlantısı kurulamadı.
   - Önceden çözümleyip önbelleğe almak işe yaramadı: Rust tarafı kendi sorgusunu yapıyor.
   - **Çözüm:** konteynere özel DNS (`--dns 1.1.1.1 --dns 8.8.8.8`, Compose'da `dns:`). Sistem ayarına
     dokunulmadı.
   - Ev bilgisayarında (aynı router) aynı ayar kullanılır.
4. **Saat senkronu.** Windows saati Binance sunucusundan ~1,0 sn geride ölçüldü: canlı bar gecikmesi −1 sn
   görünüyor. Host kurulumunda NTP senkronu şart. İmzalı borsa isteklerinde `recvWindow` bunu tolere eder,
   ama zaman damgalı kayıt ve denetim izi doğru saat ister.

## 6. Küçük notlar

- Backtest'te `subscribe_bars` "no client found" hata satırı basıyor. Zararsız, ama log gürültüsü.
- Binance veri istemcisi açılışta işlemde olmayan yüzlerce eski sembol için uyarı basıyor. Log düzeninde
  filtrelenir.
- Binance toplu arşivinde (data.binance.vision) **2025'ten itibaren zaman damgaları mikrosaniye**, öncesi
  milisaniye. Veri katmanında birim tespiti şart (Spike 03'e girdi).
- Stooq'un ücretsiz CSV'si artık JavaScript doğrulaması istiyor, betikle alınamıyor. Yahoo grafik uç noktası
  SPY ve THYAO.IS için çalışıyor (Spike 03'e girdi).
