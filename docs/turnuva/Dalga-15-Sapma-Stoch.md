---
proje: TradeBot
created: 2026-10-05
type: turnuva-plani
durum: ön kayıt (koşudan önce commit edildi)
---
# Turnuva — Dalga 15: "sapma + stokastik RSI + EMA" sistemi (ön kayıt)

Dosya: `config/turnuva/dalga15_sapma_stoch.yaml`, çekirdek `src/tradebot/cekirdek/sapma_stoch.py`.

## Neden

Scryne (2026-10-05) bir YouTube videosunun dökümünü gönderdi ("gelmiş geçmiş en başarılı trade sistemi"). Video BIST
hisselerinde (Ford Otomotiv, Ereğli, Garanti, Tofaş) seçilmiş örnekler gösteriyor, ölçüm yok; bir kurs üyeliği ve aracı
kurum yönlendirmesi satıyor. Kurallar mekanik olduğu için doğrudan ölçülebilir.

## Kural (videodan)

1. Moving Average Deviation(21) "yeşil" = fiyat ortalamanın çok altında → takip. Burada z = (kapanış − SMA21) / std21
   ≤ eşik (TradingView göstergesinin tam tanımı videoda yok; eşik ızgarada iki değer).
2. Stokastik RSI(14) K, D'yi yukarı keser → "riskli" giriş.
3. "Güvenli" giriş: ayrıca kapanış EMA(21) üstünde.
4. Kâr al %5 / %7, stop %2. Yalnız alış. Takip 20 bar içinde tetiklenmezse düşer.

Karar bar kapanışında, dolum sonraki açılışta; stop ve hedef kapanışta denetlenir (boşlukta kayıp %2'yi aşabilir).

## Izgara ve piyasalar (32 deneme, yeni aile `sapma_stoch`)

z eşiği {−1,5, −2,0} × güvenli {0, 1} × kâr al {%5, %7}; stop %2. Gruplar: altın 4 saat (Dukascopy), BTC+ETH 4 saat,
BIST100 günlük, BIST ilk 30 hisse günlük (videonun piyasası; tek hisse 4 saatlik veri yok). Maliyet piyasa başına
(BIST hisse taraf başı ~14 bps; videodaki "10 binde 2" komisyon iyimser senaryo, stres 2x ayrıca).

## Ölçüt

Dalga 1 ile aynı: A = DSR ≥ 0,95 + walk-forward OOS + stres + yıllar; B = DSR'sız kapılar. Sonuca bakıp ızgara
değiştirilmez (kural 10).
