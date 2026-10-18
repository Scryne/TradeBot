---
proje: TradeBot
created: 2026-10-18
type: turnuva-plani
durum: sonuçlandı — KALDI (2026-10-18)
---
# Turnuva — Dalga 20b: gün içi ivme, QQQ 30 dakika (ön kayıt)

Dosya: `config/turnuva/dalga20b_qqq_30dk.yaml`. Çekirdek: `cekirdek/gun_ici.gun_ici_ivme_dk` (saf, nedensel).

## Neden

Dalga 20 (Dukascopy Nasdaq 100 CFD, saatlik) KALDI; sonuçta not edildiği gibi saatlik çözünürlük Gao, Han, Li, Zhou
(2018)'in "son yarım saat" sinyalini seyreltmiş olabilir ve veri QQQ'nun kendisi değildi. Alpaca anahtarı geldi: QQQ'nun
30 dakikalık SIP barları (2016+) ile özgün tanım ölçülebilir.

## Kural

- Veri: Alpaca QQQ 30 dk, `adjustment=all`, uzatılmış seans barları dahil (04:00–20:00 ET): 16:00 barının açılışı
  çıkışın dolum fiyatıdır. Pozisyon yalnız XNYS seansında (`seans: XNYS`; yarım günde son saatler kapalı).
- r1 = close(10:00 NY) / close(önceki 16:00 NY) − 1; `tutma_dk` ∈ {30, 60}: 15:30 ya da 15:00 → 16:00 NY işaret(r1)
  yönünde; `kisa` ∈ {yok, var}. 4 deneme; aile `gun_ici_ivme` (dalga 20 ile ortak, DSR 8 denemeyle).
- Boyut, maliyet (`ABD:qqq_gun_ici`, gidiş-dönüş 4 bps) ve ölçüt (çıta 0) dalga 20 ile aynı. 2016-01 → 2025-12,
  2026 kör.

## Paper'a ne girer (sonuçtan önce yazıldı)

- A ya da B çıkan en iyi varyant `d20b:gun_ici_ivme_dk@qqq@30m` olarak paper'a girer ve d20 gözlem kolunun yerini
  alır (d20 durdurulur).
- Hiçbiri geçmezse d20 gözlem kolu sürer; ek gün içi kol açılmaz.

## Sonuç (2026-10-18, koşu `dalga20b`, ön kayıt 0385fd1)

**KALDI: 4 varyantın hepsi eksi; özgün "son yarım saat" tanımı saatlikten daha kötü.**

| Varyant | Yıllık | Sharpe | Düşüş | Kör 2026 |
| --- | --- | --- | --- | --- |
| yalnız uzun, son saat (en iyi) | −%2,6 | −1,02 | −%24 | −%0,1 |
| yalnız uzun, son yarım saat | −%2,9 | −1,43 | −%26 | −%0,4 |
| iki yönlü, son saat | −%3,9 | −1,03 | −%33 | −%1,6 |
| iki yönlü, son yarım saat | −%5,0 | −1,66 | −%40 | −%2,3 |

QQQ'nun kendi verisiyle, 2016–2025'te on yılın yalnız 2020'sinde artı. Gao ve ark.'nın 1993–2013 bulgusu bu dönemde ve
4 bps gidiş-dönüş maliyetle yok. Ön kayıt gereği yeni gün içi kol açılmadı; d20 gözlem kolu sürer. Gün içi ivme ailesi
8 denemeyle kapandı; bu aileye yeni deneme ancak farklı bir mekanizma önsavıyla açılır.
