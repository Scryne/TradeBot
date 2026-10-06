# Canlı kontrol — 2026-10-07 (29 Ekim bakışı öne alındı)

Scryne 2026-10-07: "29 Ekim'e kadar beklemiycez. şuanda olan verilerle konuş ve adımlarını at." Veri pano API'sinden
(`/api/pano`, 2026-10-06 21:33 UTC, kod 812e40c).

## Kollar

| Kol | Hesap | Süre | İşlem | Sonuç | Backtest beklentisi | Okuma |
| --- | --- | --- | --- | --- | --- | --- |
| Kilit d13 | paper 100 bin | 6 gün | 5 olay (4'ü 10-05 "hepsini kapat"la erken kapandı, SEI açık) | −%0,76 (−758 $; CARV −854) | olay başına +%1,77, olay σ ≈ %16 | gürültü içinde |
| Kilit d13 `#gercek` | Binance Demo 1.000 | 6 gün | 5 açılış denendi, 3 doldu | −%0,84 | paper ile aynı | 2 emir düştü (aşağıda) |
| Altın M15 `am15` | NCM demo 10 bin | 15 gün | 14 | −%1,39 | ~0 brüt, maliyet sonrası eksi (`Altin-M15.md`) | beklendiği gibi |
| Skalp `sk10` | NCM demo 10 bin | 24 saat | 1.056 | −%4,2 | ölçülmedi (deney) | sık işlem maliyeti, beklendiği gibi |

## Canlı veri neyi söyleyebilir, neyi söyleyemez

- Kilit kolunun kenarı olay başına +%1,77, olay başına oynaklığı ~%16 (802 olay, t 3,2). Canlıda bu kenarı t ≥ 2 ile
  görmek ~300 olay ister; kol yılda ~140 olay açıyor: **~2 yıl**. 5 olay hiçbir şey söylemez. CARV'ın −%17'si tek
  standart sapma: backtest'te kabaca her 6 olaydan biri böyle.
- Kenarın kanıtı backtest'tir (DSR 0,98, 10 deneme, kör 2025+ +%28,9). Canlı dönemin görevi kârı kanıtlamak değil,
  **zincirin backtest'teki gibi çalıştığını** göstermek: karar saati, dolum, funding, net BTC koruması, planlı çıkış.
- 26 haftalık paper PSR kapısı (2026-10-06 notu) bu yüzden takvimi ~2027-04'e itiyordu, ama kapının kendisi istatistik
  olarak yine yetersiz kalırdı. Faz 12'nin tablodaki koşulu "DSR ≥ 0,95 **ya da** paper PSR". 2026-10-01'de seçilen
  DSR yoluna dönülür (aşağıda).

## Mekanik bulgular

1. **Karar zinciri sağlam.** 5 karar gününün 5'inde karar 00:05–00:06 UTC, gecikmeli gün yok, takvim her gün alındı (38–40
   olay), paper dolumları ve funding satırları yazılıyor.
2. **Demo'da 5 açılıştan 2'si düştü.**
   - PUMP (10-05) `-4140 Invalid symbol status`: Demo'nun sembol listesi ana ağdan ayrışıyor (PUMP Demo'da `SETTLING`,
     NOM `PENDING_TRADING`; ana ağda ikisi de `TRADING`). Düzeltme bafd457: gerçek kol yeni olayı yalnız emrin
     gideceği ortamın `exchangeInfo`'sunda da işlem görüyorsa açar; ortam okunamazsa o gün yeni olay açılmaz,
     açıkların kapanışı değişmez. Ana ağda paper ile aynı sonuç verir.
   - SEI (10-06) `-1000 unknown error`: geçici borsa hatası. 812e40c'deki yeniden deneme SEI'nin penceresinden sonra
     dağıtıldı; bundan sonraki açılışlarda devrede.
3. **Elle kapatmanın bedeli.** 10-05 "hepsini kapat" dört kilit olayını açılımdan 4–7 gün önce kapattı (paper −667 $).
   Olaylara yeniden girilmedi: pencere ortasından giriş ölçülmedi, kural dışı olurdu.
4. **Doğal çıkış henüz yok.** İlk planlı kapanış SEI (paper, 2026-10-13). Demo'daki ilk tam tur AGT/STRK (giriş
   10-07, çıkış 10-14).

## Karar (Claude; Scryne: "herşeyi sana bırakıyorum")

- **Takvim yerine olay kapısı.** 29 Ekim tarihi kalkar. Mekanik kontrol, Demo kolunda **3 doğal tam tur** (giriş +
  açılım günü kapanışı) paper ile aynı günlerde gerçekleşince ve borsa ↔ defter mutabakatı temiz kalınca biter. Takvime
  göre en erken 2026-10-14/16 (AGT, STRK, ARB, VANA, W).
- **Kanıt kapısı DSR yolu** (2026-10-01 kararı geri gelir): d13 DSR 0,98 ≥ 0,95. 26 haftalık paper PSR şartı kalkar;
  paper ve Demo, paper ↔ gerçek sapmasını ölçmek için sürer.
- **Bundan sonrası Scryne'ın:** mekanik kapı geçince gerçek para iki şey ister: ana ağ anahtarı (çekim kapalı, IP
  kısıtlı; `tools/host/binance_anahtar.ps1`) ve config'teki `onay` (kural 7). Sermaye tavanı kodda 2.000 USDT.
- Altın M15 demo izleme kolu olarak sürer (Scryne'ın seçtiği sürekli işlem botu; para riski yok). Skalp deneyi bitti,
  yeniden açılmaz.
