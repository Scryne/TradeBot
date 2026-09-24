---
spike: 05
konu: Paper canlı bağlantılar — ABD ETF, FX/emtia/endeks, BIST
tarih: 2026-09-25
sonuc: YOL BELLİ (hesap açılışları Scryne'da)
---
# Spike 05: Paper bağlantıları

**Soru:** Kripto dışındaki piyasalarda paper trading için canlı veri ve (simüle) yürütme nereden gelecek?
Türkiye'den ücretsiz açılabiliyor mu?

**Genel ilke (Spike 02'den):** paper aşamasında yürütme her piyasada **Nautilus sandbox**'ta simüle edilir.
Sandbox gerçek emir defteri ya da bar verisiyle doldurur. Dışarıdan gereken yalnız **canlı fiyat akışı**.
Bu, aracı kurum emir API'sine bağımlılığı gerçek para fazına erteler.

| Piyasa | Canlı veri önerisi | Nautilus bağlantısı | Hesap | Durum |
| --- | --- | --- | --- | --- |
| Kripto | Binance public WS | Yerleşik ✅ | Gerekmez | Spike 02'de çalıştı |
| ABD ETF'leri | **Alpaca paper hesabı:** dünyanın her yerinden e-postayla ücretsiz; gerçek zamanlı IEX akışı | **Yok.** Kendi Python veri istemcimiz (Spike 02'deki kalıp) | Scryne açar (e-posta) | Kalıp doğrulandı, anahtar bekliyor |
| FX, altın, endeks, emtia | **MT5 demo hesabı** + Windows'ta resmî `MetaTrader5` Python paketi + küçük köprü servisi (host Windows; motor Docker'da) | Kendi veri istemcimiz (köprüye bağlanır) | Scryne bir MT5 demo hesabı açar (aracı kurum seçimi) | Yol belli; terminal ve hesap bekliyor |
| FX alternatifi | OANDA practice v20 API (ücretsiz demo, akış 4/sn) | Kendi istemcimiz | Türkiye'den açılabilirliği doğrulanmalı | Yedek |
| FX alternatifi 2 | Docker içinde Wine ile MT5 (mt5linux / mt5-docker) | Kendi istemcimiz | MT5 demo | Karmaşık; yalnız host Windows olmazsa |
| BIST | Yahoo 1 dk yoklama (≈15 dk gecikmeli) ya da borsapy (TradingView akışı, resmî değil) | Kendi istemcimiz (Spike 02'de Yahoo ile çalıştı) | Gerekmez | Günlük stratejide gecikme sorun değil: karar kapanışta, dolum ertesi açılışta |

**Notlar:**
- Nautilus'un Interactive Brokers bağlantısı gerçek para fazında ABD ve dünya piyasaları için ana aday olur
  (IB paper hesabı ancak IB hesabıyla açılıyor).
- MT5 köprüsü Faz 8'in işi. Windows servisi bir `MetaTrader5` oturumu açar ve fiyat/mum akışını yerel ağda
  (gRPC ya da HTTP) Nautilus istemcisine verir. Gerçek parada aynı köprü emir yolunu da taşır.

**Scryne'dan gerekenler (paper öncesi, acil değil):**
1. Alpaca paper hesabı (alpaca.markets, yalnız e-posta) → API anahtarı.
2. Bir MT5 demo hesabı: forex/CFD sunan bir aracı kurumdan ücretsiz. Aracı kurum seçimi konuşulur.
3. (Spike 04-B için) build.nvidia.com hesabı → `NVIDIA_API_KEY`.
