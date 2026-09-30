---
proje: TradeBot
created: 2026-09-27
type: turnuva-plani
durum: ön kayıt (koşudan önce commit edildi)
---
# Turnuva — Altın M15 (ön kayıt)

Dosya: `config/turnuva/altin_m15.yaml`. Kurallar dalga 1 ile aynıdır: maliyet (CFD metal, aleyhte), frenler, walk-forward,
stres ve A/B ölçütü (B için DSR şartı yok). Bu dosya koşudan önce commit edildi.

## Neden

Scryne satılan bir altın EA'sının tanıtımını ve bir videoyu gördü (2026-09-27): "XAUUSD Adaptive Edge M15", 5 alış + 5
satış stratejisi, piyasa filtreleri, risk katmanları; videoda "1 dolardan giriyor, her işlemde para 2 katına çıkıyor".
İstek: araştır, profesyonel karşılığını kur, gerçekliğini ölç. İki ayrı soru var:

1. **Videodaki iddia** ("her işlemde 2 kat"): bir strateji sorusu değil, kaldıraç ve olasılık sorusu. Ayrı ölçülür
   (`research/altin/iddia.py`, aşağıda).
2. **EA'nın anlattığı yapı** (çok strateji + risk katmanları) altında gerçek bir üstünlük var mı: bu turnuva.

## 1. Videodaki iddia: hesap

- XAUUSD 0,01 lot = 1 ons. Fiyat 1 $ oynarsa kâr/zarar 1 $. 1 $'lık hesapta +1 $ = 2 kat, −1 $ = hesap sıfır.
- Altın ~4.300 $ (2025 sonu). 1 ons'u 1 $ teminatla açmak **~4.300:1 kaldıraç** ister. Teminat: 1:20 (AB perakende
  sınırı) 215 $, 1:500 8,6 $, 1:2000 2,15 $. Yani "1 dolardan 0,01 lot" ancak "sınırsız kaldıraç" veren offshore
  hesaplarda mümkün.
- Son bir yılda altının günlük aralığı medyan 45 $. ±1 $'lık bariyer bu salınımın 45'te biri: işlem dakikalar içinde
  sonuçlanan bir yazı-turadır. Spread (0,20–0,50 $) bu 1 $'ın %20–50'sini peşin alır.
- Yazı-turada p ≈ 0,4 ise art arda 5 katlama olasılığı 0,4⁵ ≈ %1, 10 katlama ≈ %0,01. 1.000 kişi denerse ~10 kişi 5 kez
  art arda katlar. Videoya çıkanlar onlardır (hayatta kalan yanlılığı). Kalan ~990 kişinin hesabı sıfırlanmıştır.
- EA'nın kendi tanıtımı da iddiayla çelişir: sabit 0,01 lot, günlük zarar sınırı %3, işlem başı R/R 2. Bu yapı "her
  işlemde 2 kat" üretemez; o ancak hesabın tamamını tek işleme koyan kaldıraçla olur.
- **TradeBot'ta imkânsız:** sabit 3x tavan, ≥ 5x hiçbir modda yok (kural 6). Ölçüm yalnız iddiayı test etmek içindir.

Ölçüm: gerçek dakikalık XAUUSD'de rastgele anlarda ±1 $ bariyerli işlem, spread 0,20 / 0,35 / 0,50 $. Aynı dakikada iki
bariyer de geçilirse sıra bilinmez: kötümser ve iyimser sayım ikisi de raporlanır. Çıktı: p, bariyere varış süresi,
p^k, 1.000 kişiden kaçının art arda 5/10 katladığı, işlem başı beklenen değer.

## 2. EA'nın yapısı: turnuva

EA stratejilerini adlandırmıyor. Burada her biri gün içi altında bilinen bir fikre dayanan, hem alış hem satış yönlü beş
aile var (`src/tradebot/cekirdek/altin.py`):

| Aile | Fikir |
| --- | --- |
| `seans_kirilim` | Asya seansı aralığının (UTC 00–07) Londra/NY saatlerinde kırılımı |
| `kanal_kirilim` | Son n barın tepe/dip kırılımı (48 bar = 12 saat, 96 bar = 24 saat) |
| `trend_geri_cekilme` | EMA 50/200 trendi yönünde RSI(14) geri çekilmesi |
| `bant_donus` | Bollinger z-skoru aşırılığından dönüş |
| `sikisma_kirilim` | Bant genişliği düşükken bant kırılımı |
| `ea_birlesik` | Beşi birlikte, en fazla 3 açık işlem (EA gibi) |

**Risk katmanları EA'nın varsayılanları** (`yonet`): stop = sl_atr × ATR(14), hedef = 2 × stop, en uzun 192 bar,
günlük ±3R (EA: işlem başı %1 riskle günlük ±%3), günde 3 ardışık kayıpta dur, haber filtresi (±60 dk yeni giriş yok;
FOMC, NFP, CPI resmi takvimleri, `config/haber_takvimi.yaml`).

**Izgara (32 deneme):** stop genişliği 1,5 / 2 ATR, haber filtresi açık/kapalı (filtrenin katkısı ölçülür) ve ailenin
tek ana parametresi. EA'nın diğer varsayılanları sabit.

**Bizim farkımız (profesyonel katman):**
- Karar bar kapanışında, dolum sonraki barın açılışında. Stop ve hedef kapanışta denetlenir (boşlukta kayıp 1R'yi
  aşabilir, aleyhte).
- Maliyet: CFD metal, taraf başı ~2 bps (yarım spread 1 bps varsayılan, komisyon 0,5, kayma 0,5) + finansman;
  stres testinde 2 kat.
- Boyut sabit lot değil, oynaklık hedefi (%20) ve 3x tavan.
- Walk-forward (IS 1,5 yıl → OOS 0,5 yıl), DSR (32 deneme), yıllık ve rejim kırılımı.

## Karar ölçütü

Dalga 1 ile aynı (A: DSR ≥ 0,95 + OOS + stres; B: sermayesiz paper gözlem). Sıfır hipotezi: hiçbir aile geçmez.

## Veri

Dukascopy XAUUSD dakikalık BID, son 3 yıl (2023-09 → 2026-09). Dukascopy hız sınırı nedeniyle indirme ~8 saat
sürüyor. 15m bar dakikalıktan kurulur. ASK dakikalık yok: spread maliyet modelinin varsayılanından (aleyhte).

## Sonuç (2026-09-28, koşu `dalgaaltin_m15`)

Veri: Dukascopy XAUUSD dakikalık, 2023-09-01 → 2026-09-25 (ön kayıttaki dönem; ilk indirme zaman bütçesiyle
2023-11-09'da durmuştu, eksik 6 hafta koşudan önce tamamlandı).

**Hiçbir aile geçmedi; sıfır hipotezi ayakta. EA'nın yapısı gün içi altında maliyet sonrası kâr üretmiyor.**

| Aile | Sharpe | DD | OOS yıllık | DSR |
| --- | --- | --- | --- | --- |
| seans_kirilim | −0,08 | −%13 | −%1,4 | 0,28 |
| kanal_kirilim | −0,18 | −%19 | −%1,0 | 0,19 |
| sikisma_kirilim | −0,63 | −%15 | −%5,7 | 0 |
| trend_geri_cekilme | −1,34 | −%15 | −%7,7 | 0 |
| ea_birlesik (EA gibi, beşi birlikte) | −1,43 | −%37 | −%15,5 | 0 |
| bant_donus | −1,98 | −%32 | −%18,1 | 0 |

- **Birleştirmek kurtarmıyor:** beş zayıf stratejiyi birlikte çalıştıran `ea_birlesik` en kötülerden biri. Çok
  strateji, çok işlem demek (yılda ~4.000); her işlem maliyet öder.
- **Haber filtresinin katkısı yok:** 32 varyantta filtre kapalı ortalama −%0,161/hafta, açık (±60 dk) −%0,160/hafta.
- En iyi iki aile (seans ve kanal kırılımı) sıfıra yakın ama negatif: kırılım fikrinde zayıf bir iz var, maliyeti
  karşılamıyor.
- Videodaki iddia (bölüm 1, `research/altin/sonuc/iddia_2026-09-27.json`): 0,20 $ spread'le tek işlemde 2 katlama
  olasılığı %37–47, art arda 5 katlama ~%0,7 (1.000 kişiden ~7), işlem başı beklenen değer −0,25 $. Kumar; strateji değil.

Sonuca bakıp ızgara ya da filtre değiştirilmedi (kural 10). Bu 32 deneme ilgili ailelerin defterinde sayılı.

## Ek (2026-09-30): demo gözlem kolu

Scryne bir TikTok "robot scalping" videosu gösterdi (20 dakikada 14 → 7.183 USD). Videoda görülen: aynı yönde, aynı
fiyattan 12–13 özdeş pozisyon, bakiyeyle büyüyen lot (0,01 → 0,31), ~200–850x kaldıraç; bir karede yığın −111 USD
zararda. Doğrulanmış kayıt yok. Yöntem kaldıraç ve yığma; kural 6 gereği hiçbir modda yok. Scryne kurallar içinde
demo kolunu seçti: `kanal_kirilim` (n = 48, 2 ATR, haber filtresi yok; bu turnuvanın en iyi varyantı) NCM forex demo
hesabında sabit 0,01 lot, her M15 kapanışında karar (`canli/altin.py`). Yeni deneme değil: test edilmiş varyantın
ileriye dönük ölçümü. Beklenti negatif.
