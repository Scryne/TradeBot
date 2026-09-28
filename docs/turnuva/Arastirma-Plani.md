---
proje: TradeBot
created: 2026-09-28
type: arastirma-plani
durum: aktif
---
# Araştırma planı — ilişkisiz getiri kaynakları

Karar: Claude (2026-09-28; Scryne yetkiyi devretti). Dayanak: `docs/Denetim-2026-09-28.md` §Stratejik değerlendirme.

## Sorun

~790 deneme sonunda ayakta kalan tek fikir BTC/ETH trendi (B; DSR geçmiyor). Paper'daki 5 kol aynı bahis (korelasyon
~0,79). Gerçek paraya giden yolun darboğazı altyapı değil: **ilişkisiz ikinci ve üçüncü getiri kaynağı.**

## Hedef

Paper turnuvası bitmeden (~2026-12-20) BTC/ETH trendiyle korelasyonu düşük (< 0,3) en az bir B kolunu paper'a almak.
Başarı ölçüsü tek kolun Sharpe'ı değil, portföye katkısı: her dalga en iyi kolun paper kollarıyla haftalık korelasyonunu
ve 50/50 karışımın Sharpe'ını da raporlar (kapı değil, bilgi).

## Kurallar (her dalga)

- Ön kayıt: plan ve ızgara koşudan önce commit edilir; sonuca bakıp değişiklik yeni denemedir (kural 10).
- Küçük ızgara, tek net hipotez, literatürde ekonomik gerekçesi olan fikir. Veri madenciliği yok.
- Çıta risksiz faiz (`olcut.risksiz_yillik`, Dalga-1 ek 4): USD'de T-bill (%4,5); faiz farkını içeren vadeli sürekli
  serilerde 0.
- Maliyet aleyhte, piyasa başına (kural 4); vadelilerde devir maliyeti dahil.

## Sıra

| # | Dalga | Hipotez (ekonomik gerekçe) | Veri | Durum |
| --- | --- | --- | --- | --- |
| 1 | **VİOP 2 — TL taşıma** | USDTRY vadelisi TL–USD faiz farkı kadar primli; kısa pozisyon bu primi toplar. Çöküşler (2018, 2021) trend ve oynaklık filtresiyle kesilir. Carry + momentum filtresi FX'te kanıtlı bir kalıp. | NCM `TRYUSD_YAKINVADE` (2015-07 → 2026-02) + `F_USDTRY` kontratları; spot Dukascopy USDTRY | 🔄 hazırlanıyor |
| 2 | **Dalga 3 — çok varlıklı vadeli trend** | Yönetilen vadeli fonların klasik kaynağı: endeks, emtia, metal, döviz vadelilerinde zaman serisi trendi. Kripto trendiyle korelasyonu düşük, kriz dönemlerinde pozitif. Dalga 1'in CFD sürümü finansmanda boğuldu; vadelide finansman yok (faiz farkı serinin içinde). | NCM sürekli grafikler (`ES!`, `NQ!`, `YM!`, `CL!`; geçiş ayarı gerekir), GOLD/SILVER, FX, VİOP XU030 sürekli | ⏳ |
| 3 | **Olay tabanlı (Jev)** | C1 ölçümü: A1 vetosu sonrası 7 günde varlık BTC'ye göre −%21. Spot'ta açığa satış yok; kullanım alanı veto (zaten canlı) ve gelecekte vadeli/perp. | Jev olayları + Binance | ⏳ (araç gelince) |

### Dalga 3 tasarım notu (veri)

- NCM'nin `ES!`/`NQ!`/`YM!`/`CL!` sürekli grafiklerinde vade geçişinin ayarlı olup olmadığı bilinmiyor; CME kontratları
  3. Cuma'da vadelenir (VİOP takvim kuralı uygulanamaz); tek kontrat geçmişi yalnız birkaç ay. Önce ölçülür (spotla
  geçiş günlerinde sıçrama var mı).
- Yedek yol, **fazla getiri vekili:** vadeli getirisi ≈ spot getiri − (risksiz faiz − temettü/depolama). Dukascopy'nin
  2010'dan endeks/emtia/metal/FX saatlik verisi + günlük risksiz faiz serisi (FRED T-bill; FX'te iki ülke faizi) ile
  vekil seri kurulur. Dalga 1'in CFD kolları finansmanı hem uzun hem kısa pozisyona aynı yönde (%6) yazdı; vadelide kısa
  pozisyon taşımayı kazanır. Bu fark dalga 1'in "CFD'de trend finansmanda boğuldu" sonucunun vadeliye taşınamayacağını
  gösterir: dalga 3 bunu ayrıca sınar.

Bir dalgadan B çıkarsa: MT5 canlı bar akışı paper düğümüne bağlanır (Faz 8'in kalan işi), kol paper'a girer. Bu iş
B çıkmadan yapılmaz (kullanılmayan kod yazılmaz).

## Kapanan fikirler (tekrar denenmez, yeni gerekçe olmadan)

FX/metal/endeks CFD trendi (finansman), ABD ETF trend ve dönüş, BIST hisse (yanlı veri), kripto kesitsel momentum,
kripto funding carry (2022'den beri eşik altı), BIST30 vadeli tek enstrüman (VİOP 1), altın M15 gün içi (EA karşılığı).
