---
proje: TradeBot
created: 2026-10-18
type: turnuva-plani
durum: ön kayıt (koşudan önce commit edildi)
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
