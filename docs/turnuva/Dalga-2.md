---
proje: TradeBot
created: 2026-09-26
type: turnuva-plani
durum: ön kayıt (koşudan önce commit edildi)
---
# Turnuva — Dalga 2 (ön kayıt)

Dosya: `config/turnuva/dalga2.yaml`. Kurallar dalga 1 ile aynıdır: kol tanımı, maliyet, frenler, point-in-time evren,
walk-forward, stres ve A/B ölçütü. B için DSR şartı yoktur (Dalga-1 ek 3). Bu dosya koşudan önce commit edildi.

## Neden

Dalga 1 ara sonucu (`Dalga-1-Ara-Sonuc.md`) üç ders verdi. Bu dalga bunları sınıyor:

1. **Oynaklık penceresi.** 30 günlük tahmin sakin dönemde kaldıracı şişiriyor. Örnek: Nisan 2019'da endekslerde 3x,
   Mayıs'ta −%20. Dalganın tek boyut değişikliği `vol_pencere_gun: 90`.
2. **Kripto büyükler.** Kriptoda trend yalnız büyüklerde çalışıyor. Point-in-time likidite ilk 5, BTC+ETH ile
   karşılaştırılıyor.
3. **Karma sepet.** CFD finansmanı kaldıraçlı trendi siliyor. Çeşitlendirme finansmansız araçlarla aranıyor:
   BTC+ETH (spot, yalnız long) + 26 ABD ETF (iki yönlü) tek kolda.

Izgaralar dalga 1 ile aynı; yeni ayar araması yok. Denemeler trend ailesinin defterine eklenir.

## Teknik notlar (koşudan önce eklenen kod)

- **Karışık takvim.** Grupta birden çok takvim varsa yıllık bar sayısı ızgaradan ölçülür (`bar_yil_olcu`). ETF'in
  hafta sonu barları ileri doldurulmuştur (getiri 0), bu yüzden yıllıklaştırma doğrudur (test).
- **Yalnız long piyasalar.** Binance spot ve BIST enstrümanları grup yönünden bağımsız olarak yalnız long
  (`YALNIZ_LONG_PIYASALAR`, test).

## Kol sayısı

- 4 grup; kripto grupları için 4h ve 1d, ETF ve karma için yalnız 1d.
- Toplam 6 grup-zaman dilimi × 3 strateji = 18 kol, 288 deneme.

## Sonuç (2026-09-26, kod 47096bf)

**18 kol: 3 B, A yok.**

- **90 günlük oynaklık, BTC+ETH'de düşüşü azalttı; Sharpe aynı kaldı ya da arttı.** 1d ve 4h kollarında düşüş
  −%17 ile −%23 arası; dalga 1'de (30 gün) −%24 ile −%32. En iyi kol `donchian_ls@kripto_btc_eth@4h`: Sharpe 1,20,
  DD −%17, OOS yıllık +%12,3.
- **Karma sepet, çeşitlendirme beklentisini karşılamadı** (Sharpe 0,37–0,56). ETF'ler sepete hâkim; ETF trendi
  zaten zayıf.
- **Kripto büyük 5, BTC+ETH'den kötü** (Sharpe 0,62–0,85). Sepet genişledikçe kötüleşme örüntüsü sürüyor.
- **ABD ETF'te 90 gün pencere fark yaratmadı** (Sharpe 0,29–0,51).

Paper listesine eklenenler: `docs/turnuva/Paper-Listesi.md`.
