---
proje: TradeBot
created: 2026-10-18
type: turnuva-plani
durum: sonuçlandı — A (düşük oynaklık), B (momentum) (2026-10-18)
---
# Turnuva — Dalga 21: momentum ve düşük oynaklık, oynaklık yönetimli (ön kayıt)

Dosya: `config/turnuva/dalga21_risk_katmanli.yaml`. Karar: Scryne 2026-10-18 ("iki şeyi de sana bırakıyorum").

## Neden

Dalga 19 ve 19b'de momentum (Sharpe 0,85–0,88, yıllık +%16) ve düşük oynaklık (DSR 0,97–1,00) getiride en güçlü
ailelerdi, ama ön kayıtlı tam dönem kapısında kaldılar: en kötü hafta −%11 … −%16 (eşik −%10) ve 2020 Mart'ında acil
durdurma (tepeden −%25). Kaybettikleri yer çöküş haftalarıdır. Bu, momentum için belgelenmiş bir özelliktir ve
belgelenmiş bir ilacı vardır:

| Kaynak | Bulgu |
| --- | --- |
| Barroso, Santa-Clara (2015), *Momentum has its moments*, JFE 116(1) | Momentumu kendi gerçekleşen oynaklığıyla sabit hedefe ölçeklemek Sharpe'ı ~0,5'ten ~1'e çıkarır, en kötü ayı yarıya indirir |
| Moreira, Muir (2017), *Volatility-Managed Portfolios*, JF 72(4) | Oynaklık yükselince maruziyeti azaltmak birçok faktörde risk ayarlı getiriyi artırır |
| Cederburg ve ark. (2020), JFE | Karşı görüş: örneklem dışı kazanç birçok faktörde küçülür (dürüst önsel) |

Dalga 19/19b de oynaklık hedefliydi (%20, 60 günlük tahmin), ama 60 günlük pencere ani oynaklık sıçramasını geç gördü.
Bu dalga yalnız boyutu değiştirir: hedef %12, tahmin penceresi 20 gün.

**Kural 10 notu:** Bu dalga önceki sonuçlara bakılarak açıldı (kapıda kalan iki aile). Bu yüzden ayrı ön kayıttır,
denemeler aynı ailelerde sayılır (momentum dalga 1 + 19 + 19b ile birlikte, düşük oynaklık 19 + 19b ile) ve DSR bu
artan deneme sayısıyla hesaplanır. Kapılar ve ölçüt değişmez (en kötü hafta ≥ −%10, acil durdurma yok, T-bill çıtası).

## Kural

- Veri, evren, maliyet, walk-forward ve ölçüt dalga 19b ile aynı (Alpaca 2016+, kapanan üyeler dahil; taraf başı 5,5 bps;
  çıta T-bill %4,5; 2026 kör).
- Boyut: kol oynaklık hedefi **%12**, ex-ante tahmin penceresi **20 gün**, brüt ≤ 1x, frenler açık.
- `hisse_momentum` (4): geriye {126, 252} gün × ilk {10, 20}, son 21 gün atlanır, aylık, piyasa filtresi yok.
- `dusuk_oynaklik` (2): pencere {60, 250} gün, en düşük 20, aylık, filtre yok.
- 6 deneme. Grup A olabilir.

## Paper'a ne girer (sonuçtan önce yazıldı)

- A ya da B çıkan her ailenin en iyi varyantı yeni günlük kol olarak paper'a girer (`d21:<strateji>@nasdaq100@1d`,
  Alpaca verisi). Alpaca paper hesabı tek ve 100.000 $ olduğu için yeni kollar **iç simülasyonda** çalışır (hesapta
  pozisyon katlanmasın); `d19b` kolu Alpaca'da sürer.
- Hiçbiri geçmezse yeni kol açılmaz; aileler bu risk katmanıyla da kapanmış sayılır.
- Gerçek para kapısı değişmez.

## Sonuç (2026-10-18, koşu `dalga21`, ön kayıt 5cbff48)

**Düşük oynaklık A, momentum B.** Risk katmanı amacına ulaştı: iki aile de en kötü hafta kapısını rahat geçti ve hiç
acil durdurma tetiklemedi (19b'de ikisi de tetiklemişti). Bedeli getiri: maruziyet düştü.

| Strateji | Varyant | Yıllık | Sharpe | Düşüş | En kötü hafta | OOS yıllık / Sharpe | DSR (deneme) | Kör 2026 | Karar |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| dusuk_oynaklik | 60 gün, ilk 20 | +%7,2 | 0,71 | −%14,6 | −%6,4 | +%9,4 / 0,88 | 0,97 (10) | +%8,2 | **A** |
| hisse_momentum | 126 gün, ilk 10 | +%11,6 | 0,95 | −%17,5 | −%5,7 | +%10,0 / 0,83 | 0,71 (62) | +%19,7 | **B** |

Kıyas: QQQ al-tut 2016–2025 +%19,8/yıl, Sharpe 0,97, düşüş −%37 (kör +%22,1).

**Dürüst çekinceler (A'yı okurken):**
1. Bu dalga sonuca bakılarak açıldı: risk katmanını (%12, 20 gün) önceki dalgalarda kapıda kalan aileler için seçtim.
   Izgaradaki 6 deneme sayıldı, ama "hangi risk katmanı" seçimi deneme defterine giremeyen bir serbestlik derecesidir.
2. Düşük oynaklık ailesi yeni ve küçüktür (10 deneme): DSR eşiği düşük (SR* 0,014). Momentumun DSR'ı aynı Sharpe'a
   yakın değerle 62 denemede 0,71'de kaldı; fark büyük ölçüde deneme sayısından.
3. Örneklem 10 yıl, tek ülke, tek endeks; düşük oynaklık 2022 ve 2025'te eksi, aşağı rejim t 0,67 (zayıf).
4. Getiri T-bill'in yalnız ~2 puan üstünde (OOS +%9,4 − %4,5); QQQ'nun getirisini değil, düşüşü azaltmayı sunuyor.

Final Doküman'daki gerçek para kanıt yolu (DSR ≥ 0,95 + plato) biçimsel olarak sağlandı; yukarıdaki çekinceler ve kural
7 gereği gerçek paraya geçiş Scryne'ın açık kararıdır, otomatik bir adım değildir. Önerim: önce paper'da birkaç ay.

**Paper (ön kayıt gereği, iç simülasyon):** `d21:dusuk_oynaklik@nasdaq100@1d` (A) ve `d21:hisse_momentum@nasdaq100@1d` (B).
