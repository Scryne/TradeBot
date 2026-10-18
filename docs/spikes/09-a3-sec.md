---
proje: TradeBot
created: 2026-10-18
type: spike
durum: geçti
---
# Spike 09 — A3: SEC 8-K → Nasdaq hissesi vetosu (Jev)

Betik: `research/spikes/spike_a3_sec.py`. Rol: `src/tradebot/zeka/a3_sec.py`, toplayıcı `src/tradebot/metin/sec.py`.
Model `jev-1.13.0` (sabit; `ts.py kontrol` ile yaşadığı doğrulandı).

## Soru

8-K başvurusunu yapan şirketin hissesini tutan biri için başvuru ne anlama geliyor? Choice `etki` (5 seçenek):
`bankruptcy_or_delisting`, `being_acquired`, `accounting_problem`, `serious_negative` (veto kümesi) ve
`routine_or_positive`. Tuzak listesi soru tanımından önce yazıldı (rol dosyasının başında): alan taraf hedef değildir,
rutin finansman, denetçi rotasyonu, uyum bildirimi.

## Örnekler ve sonuç

Beklenen etiketler olaylardan (çalıştırmadan önce) elle yazıldı. Veri: SEC `submissions` API'si (gerçek başvurular,
kapanmış şirketler dahil).

| Grup | Örnek | Sonuç |
| --- | --- | --- |
| Satın alınan (hedef) | ATVI ×2 (anlaşma, tamamlanma + delist), SPLK, XLNX, CELG, WBA | 6/6 `being_acquired`, güven ≥ 0,99 |
| Alan taraf (tuzak) | MSFT (ATVI), AMD (XLNX) ×3, CSCO (SPLK) | 5/5 `routine_or_positive` |
| İflas / delist | SVB Financial Chapter 11 (1.03, 3.01) | `bankruptcy_or_delisting` 1,00 |
| Muhasebe | SMCI denetçi istifası ve endişe bildirimi (4.01) | `accounting_problem` 1,00 |
| Ciddi olumsuz | MSFT siber olay (1.05); Intel %15 işten çıkarma (2.02, ek 99.1) | `serious_negative` 1,00 / 0,77 |
| Rutin kazanç (yanlış veto tuzağı) | AAPL, NVDA, AMD, MSFT, COST, NFLX, TSLA (zayıf çeyrek) | 7/7 `routine_or_positive`, 1,00 |
| Rutin finansman | AAPL tahvil ihracı (8.01) | `routine_or_positive` 1,00 |

**23/23 doğru, yanlış veto 0.** Gecikme ~0,3 sn/çağrı.

## Öğrenilenler (koda işlendi)

1. **Kalem filtresi dar olmalı.** İlk sürüm 2.02 ve 7.01'i rutin sayıp modele hiç sormuyordu: Intel'in yeniden
   yapılanması kazanç bildirimindeydi (2.02), Walgreens'in satışı basın açıklamasındaydı (7.01). Rutin kümesi yalnız
   yönetişim kalemleri: 5.02, 5.03, 5.07, 5.08, 9.01.
2. **Ek 99 okunmalı.** 2.02 ve 7.01 başvurularının ana belgesi kapak sayfasıdır; haber ek 99.1'deki basın
   açıklamasındadır. Ek adı şirkete göre değişir (Intel: `q224_earningsrelease.htm`): tür satırından (`EX-99`) bulunur.
   Ek okununca Intel 0,77 güvenle `serious_negative` oldu (önce 1,00 güvenle rutin diyordu: model görmediği metni
   yargılayamaz).

## Karar

A3 canlıya girer: yalnız Jev'li ikiz kolda (`+jev`), yalnız riski azaltır (vetolu hissede yeni alış yok; kural 5, 8).
Eşik ve yükseltme A1/A2 ile aynı (`zeka.karar`; güven < 0,5 → NVIDIA modeli; belirsizde veto). Veto süreleri
`config/zeka.yaml` `sec.veto_gun` (satın alınma 180, muhasebe 30, ciddi olumsuz 10 gün; iflas/delist kalıcı).
Jev'li/Jev'siz kol karşılaştırması paper'da ölçülür.
