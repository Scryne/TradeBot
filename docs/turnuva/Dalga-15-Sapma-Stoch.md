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

## Sonuç (2026-10-05, koşu `dalga15`, ön kayıt 3c693da)

**KALDI: 4 grubun hepsinde.** 32 deneme.

| Grup | En iyi varyant | Sharpe | Yıllık | Düşüş | Walk-forward OOS | Pozitif varyant |
| --- | --- | --- | --- | --- | --- | --- |
| BIST hisse (ilk 30, günlük; videonun piyasası) | güvenli, %7, z −2 | −0,31 | −%6,2 | −%86 | −%11,9/yıl | 0 / 8 |
| BIST100 günlük | güvenli, %7, z −1,5 | −0,03 | −%0,3 | −%23 | −%1,3/yıl | 0 / 8 |
| BTC + ETH 4 saat | güvenli, %7, z −1,5 | 0,30 | +%3,1 | −%28 | +%0,6/yıl | 5 / 8 |
| Altın 4 saat | riskli, %7, z −1,5 | 0,41 | +%2,8 | −%26 | +%1,5/yıl | 8 / 8 |

- Videonun kendi piyasasında (BIST hisseleri) 8 varyantın hepsi eksi; en iyisi 2018'de −%50, 2011'de −%39.
- Altın ve kriptodaki küçük artı yalnız alış yapan bir kuralın yükselen piyasadan aldığı paydır: altın 2025'te +%21,5
  (altının kendisi aynı yıl çok daha fazla yükseldi), 2013 düşüşünde −%12,6. Al-tutu geçmiyor; DSR 0,24–0,37.
- Videodaki örnekler (Ford Otomotiv, Ereğli, Garanti) seçilmiş geçmiş grafiklerdir; kural bütün hisselere ve yıllara
  uygulanınca kazanç kalmıyor. Sonuca bakıp ızgara değiştirilmedi (kural 10).
