---
proje: TradeBot
created: 2026-09-30
type: turnuva-plani
durum: ön kayıt (koşudan önce commit edildi)
---
# Turnuva — Dalga 11: ABD hisse endeksi olay ve takvim primleri (ön kayıt)

Dosya: `config/turnuva/dalga11_endeks.yaml`. Kod: `cekirdek/endeks_takvim.py` (saf, nedensel;
`tests/test_endeks_takvim.py`). FOMC takvimi: `config/fomc_planli.yaml` (dalga 10 ile aynı, yalnız planlı toplantılar).

## Neden

Dalga 10'dan (aynı gün) çıkan ders: forex'te takvim/akış primleri var ama küçük (FOMC günü dolar B, yılda +%0,4).
Aynı NCM forex hesabında ABD endeks vadelileri (ES, NQ) de işlem görüyor ve spread'leri paritelerden dar (canlı tik tam
spread medyanı 0,8 / 0,5 bps). Hisse piyasasında takvim primleri döviz piyasasındakilerden büyük ve daha iyi belgelidir:

| Strateji | Hipotez | Kaynak |
| --- | --- | --- |
| `fomc_oncesi` | S&P 500, planlı FOMC açıklamasından önceki 24 saatte olağandışı pozitif getiri verir (1994–2011'de yıllık hisse priminin büyük kısmı). | Lucca, Moench (2015), *The Pre-FOMC Announcement Drift*, Journal of Finance 70(1) |
| `gece_kaymasi` | Endeks getirisi nakit seans dışında (kapanıştan açılışa) birikir, seans içi getiri ~0. | Cliff, Cooper, Gulen (2008), *Return differences between trading and non-trading hours*, JEF 15(1); Lou, Polk, Skouras (2019), *A tug of war: Overnight versus intraday expected returns*, JFE 134(1) |
| `ay_donumu_saat` | Hisse getirisi ayın son iş günü ile yeni ayın ilk iş günlerinde yoğunlaşır (maaş/fon akışları). | Lakonishok, Smidt (1988), RFS 1(4); McConnell, Xu (2008), *Equity Returns at the Turn of the Month*, FAJ 64(2) |

**Ay dönümü yeniden deneniyor, gerekçesi:** dalga 1 aynı fikri ABD endeks CFD'sinde yıllık %6 finansmanla ölçtü ve
KALDI (Sharpe 0,33, DSR 0,93; walk-forward geçmedi). NCM'de endeks işlemi vadeli kontrattadır: swap yok, maliyet
vadeli taşımasıdır (≈ faiz − temettü). Bu yeni bir maliyet yapısıdır ama fikir aynıdır: deneme dalga 1'in `takvim`
ailesine yazılır ve DSR önceki 12 denemeyle birlikte sayılır (kural 10).

**Önsel (dürüst, koşudan önce):** FOMC öncesi kaymanın 2015'ten sonra zayıfladığı ya da kaybolduğu yayımlandı (Kurov,
Wolfe, Gilbert 2021, *The disappearing pre-FOMC announcement drift*, Finance Research Letters). Gece kayması her gün bir
gidiş-dönüş yapar (~4 bps maliyet + taşıma); günlük etki bunu aşmazsa kaybeder. Ay dönümü yılda 12 işlem; dalga 1'de
CFD finansmanıyla bile Sharpe 0,33 vermişti. Üç fikir de "belirli saatlerde uzun hisse"dir: getirinin bir kısmı
hisse primidir (beta). Bu bir kusur değil ama al-tut ile kıyaslanır (bilgi).

## Kural

- Evren: `DUKASCOPY:USA500IDXUSD` (S&P 500), `DUKASCOPY:USATECHIDXUSD` (Nasdaq 100) saatlik BID spot CFD, 2010-01 →
  2025-12-31 (2026-01 → 08 kör). Uygulama NCM'de ES/NQ vadeli CFD'si.
- Yalnız uzun, sinyal 0/1, yalnız takvimden (fiyata bakmaz). Saatler New York yerel saati (ABD yaz saati), iş günü =
  hafta içi (tatiller yok sayılır).
- **fomc_oncesi** (2 deneme): planlı karar gününden önceki iş günü 14:00 NY → `on` karar günü 14:00 NY (açıklamadan
  önce çıkış), `gun` 16:00 NY kapanışı.
- **gece_kaymasi** (1 deneme): her iş günü 16:00 NY → sonraki iş günü 09:00 NY (hafta sonu dahil).
- **ay_donumu_saat** (2 deneme): ayın son iş gününden önceki iş günü 16:00 NY → yeni ayın `sonra` ∈ {1, 3}. iş günü
  16:00 NY.
- Boyut: varlık başına oynaklık ölçeği, kol %10 oynaklık hedefi (90 gün, ex-ante), **1x brüt tavan**, enstrüman 0,5,
  bant 0,25, frenler açık. Walk-forward IS 3 yıl → OOS 1 yıl. Çıta 0 (finansman alanı vadeli taşımasını düşüyor).

## Maliyet (aleyhte, koşudan önce sabit)

`NCMFX:endeks_sabit`: komisyon 0,5 bps (ölçülmedi), yarım spread 0,5, kayma 1 → taraf başı 2 bps, gidiş-dönüş 4 bps.
Vadeli getirisi ≈ spot − (faiz − temettü)·Δt: tutulan süre için yıllık %5 (dönemin T-bill üst sınırı; temettü yok
sayılır, aleyhte). Stres: maliyet 2 kat, bir bar gecikme.

## Karar ölçütü

Dalga 10 ile aynı (A: DSR ≥ 0,95 + plato + tam dönem kapıları + walk-forward OOS > 0 + yılların ≥ %60'ı pozitif +
rejim + stres; B: DSR şartı yok). DSR aile başına: `endeks_olay` 3 deneme, `takvim` dalga 1'in 12'si + 2.

**Demo hesaba ne girer (sonuçtan önce yazıldı):** A ya da B çıkan her strateji kolunun en iyi varyantı NCM forex demo
hesabında ES (ve NQ) vadeli CFD'siyle gözlem kolu olarak çalışır; gerçek para kapısı değişmez. Hiçbiri geçmezse sıfır
hipotezi ayakta kalır, fikirler kapanan fikirlere eklenir.

## Raporlanacak (kapı değil, bilgi)

- Olay başına ortalama getiri (bps) ve isabet; 2010–2015 ve 2016–2025 ayrı (FOMC öncesi kaymanın kaybolduğu iddiası).
- Al-tut (aynı oynaklıkta) ile kıyas; zamanın yüzde kaçında pozisyonda.
- Dalga 10 FOMC dolar koluyla ve kilit koluyla haftalık korelasyon.
