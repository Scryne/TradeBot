---
proje: TradeBot
created: 2026-10-18
type: turnuva-plani
durum: ön kayıt (koşudan önce commit edildi)
---
# Turnuva — Dalga 20: Nasdaq 100 gün içi ivme, saatlik (ön kayıt)

Dosya: `config/turnuva/dalga20_gun_ici.yaml`. Çekirdek: `src/tradebot/cekirdek/gun_ici.py` (saf, nedensel;
`tests/test_gun_ici.py`).

## Neden

Scryne 2026-10-18'de Nasdaq botunun günlük kolun yanında gün içi kol da taşımasını seçti. Gün içi stratejiler içinde
akademik olarak belgelenmiş, uzun veriyle tekrarlanmış ve tek enstrümanla (QQQ) uygulanabilen en güçlü aday **piyasa
gün içi ivmesidir**:

| Kaynak | Bulgu |
| --- | --- |
| Gao, Han, Li, Zhou (2018), *Market Intraday Momentum*, JFE 129(2) | SPY 1993–2013: ilk yarım saat (önceki kapanış → 10:00) son yarım saati öngörür; R² ~%1,6, ekonomik olarak anlamlı |
| Baltussen, Da, Lammers, Martens (2021), JFE | 60+ vadeli kontratta 1974–2020 tekrar; mekanizma opsiyon piyasa yapıcılarının gama korunması ve kaldıraçlı ETF dengelemesi |
| Baltussen, Da, Soebhag (2025) | Tek hisselerde son 30 dk'da işaret ters: sinyal endeks düzeyindedir |

**Dürüst önsel:** 2015 sonrası bağımsız bir zayıflama ölçümü bulunamadı. Etki günde bir işlemdir; maliyet (gidiş-dönüş
4 bps) beklenen kazancın büyük kısmını yiyebilir. Saatlik veriyle "son yarım saat" yerine "son saat" ölçülür (sinyalin
seyrelmiş hali). Önceki ABD endeks ölçümleri (dalga 11) takvim primlerinde kaldı.

## Veri

Dukascopy Nasdaq 100 CFD (`USATECHIDXUSD`), saatlik BID, 2011-09 → 2025-12-31 (2026 kör). CFD 23 saat işlem görür;
New York 10:00 ve 16:00 saatlik bar sınırına denk gelir (UTC'de ABD yaz saati tam saat kayar). Pozisyon yalnız XNYS
seansında (`seans: XNYS`): tatil ve yarım günlerde (13:00 kapanış) kol nakittedir. Canlıda uygulama QQQ'dadır: CFD ile
QQQ arasındaki fark (temettü, takip) ölçümün sınırıdır; Alpaca anahtarı geldiğinde QQQ dakikalık verisiyle (2016+)
yeniden ölçülür (yeni deneme).

## Kural

- r1 = close(10:00 NY) / close(önceki işlem günü 16:00 NY) − 1.
- `tutma` ∈ {1, 2} saat: 15:00 ya da 14:00 NY → 16:00 NY, işaret(r1) yönünde; `kisa` ∈ {yok, var} (yalnız uzun ya da
  iki yönlü). 4 deneme, yeni aile `gun_ici_ivme`.
- Karar bar kapanışında, dolum sonraki barın açılışında (kural 4); 16:00'da kapanır, gece pozisyon yok.
- Boyut: %25 yıllık oynaklık hedefi (60 gün), **1x brüt tavan**, frenler açık.

## Maliyet (aleyhte, koşudan önce sabit)

`ABD:qqq_gun_ici`: ücret 0,3 bps (satışta SEC/TAF), yarım spread 0,5 bps (QQQ kotasyonu ~1 sent), kayma 1,2 bps →
taraf başı 2 bps, gidiş-dönüş 4 bps. Kısa bacakta ödünç %1/yıl. Stres: maliyet 2 kat, bir bar gecikme.

## Karar ölçütü

Önceki dalgalarla aynı huni. Çıta 0 (kol zamanın ~%4–8'inde pozisyonda; nakit faizsiz sayılır, aleyhte). A = DSR ≥ 0,95
+ plato + tam dönem kapıları + walk-forward OOS > 0 + yılların ≥ %60'ı pozitif + rejim + stres; B = DSR'sız.

## Paper'a ne girer (sonuçtan önce yazıldı)

- A ya da B çıkan en iyi varyant Nasdaq gün içi kolu olarak paper'da çalışır (QQQ; Alpaca paper anahtarı varsa Alpaca,
  yoksa iç simülasyon).
- **Hiçbiri geçmezse:** Scryne'ın gün içi kol seçimi gereği walk-forward OOS Sharpe'ı en yüksek varyant "gözlem kolu"
  etiketiyle paper'da çalışır; haftalık raporda backtest sonucuyla birlikte gösterilir. Gerçek para kapısı değişmez.
- Sonuca bakıp ızgara değiştirilmez (kural 10).
