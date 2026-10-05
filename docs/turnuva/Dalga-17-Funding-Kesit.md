---
proje: TradeBot
created: 2026-10-06
type: turnuva-plani
durum: ön kayıt (koşudan önce commit edildi)
---
# Turnuva — Dalga 17: kesitsel funding (ön kayıt)

Dosya: `config/turnuva/dalga17_funding_kesit.yaml`. Motor `src/tradebot/arastirma/um_dalga.py` (dalga17), çekirdek
`src/tradebot/cekirdek/funding_kesit.py`. Koşu: `tradebot arastirma um --dosya config/turnuva/dalga17_funding_kesit.yaml`.

## Neden

Kapanan "kripto funding carry" BTC/ETH spot uzun + perp kısa idi (2022'den beri T-bill altında). Bu dalga farklı bir
soru soruyor: funding'in **kesitteki** sırası, kaldıraçlı uzunların kalabalıklaştığı isimleri gösteriyor mu? Kalabalık
çözülürken bu isimler hem funding öder hem de kesitin gerisinde kalır. Kesitsel momentum (kapandı) fiyattan bakıyordu;
burada sinyal türev piyasasının konumlanması.

Kanıt durumu: Aperiodic (2025, blog, ikincil) ilk 50 coinde "en yüksek funding kısa, en düşük uzun" kesitsel carry'yi
pozitif buluyor (maliyet belirsiz, Sharpe metinde ~2,5 / dipnotta < 2). BIS WP 1087 (2023): yüksek carry sonraki
çöküşleri öngörüyor (yalnız BTC/ETH). ScryneQuant'ın Faz 12 hipotez 44'ü funding'i en yüksek dilimi evrenden dışlamanın
kör dönemde kıyası geçtiğini gördü (0,221 > 0,167). Önsel orta-zayıf.

## Kural

- Her Pazartesi 00:00 UTC: uygun evren = o gün işlem gören, önceki 30 günün tamamında verisi olan perp'ler; önceki 30
  günün ortalama günlük quote hacmine göre ilk 50 (sabit paralar hariç).
- Sinyal: son `pencere` günün ortalama günlük funding'i (tam karar anında ödenen oran hariç).
- En yüksek `n` kısa, en düşük `n` uzun; bacak başına eşit ağırlık, toplam brüt 1x, dolar nötr.
- Günlük işaretleme açılıştan açılışa; nominaller fiyatla kayar, yeniden dengelemede maliyet |hedef − mevcut| × (ücret
  %0,05 + kayma %0,10). Funding tutulan nominal üzerinden. Hafta içinde işlemden kalkan perp günün son kapanışından
  çıkış maliyetiyle kapanır.

## Izgara (4 deneme, yeni aile `funding_kesit`)

pencere {3, 14 gün} × n {5, 10}. Dönem 2021-01-04 → 2026-09-28; örneklem içi 2021–2024, kör 2025-01-06'dan.
Ölçüt dalga 13 ile aynı.

## Önsel (dürüst, koşudan önce)

- Yüksek funding'li isimler çoğu zaman güçlü yükselişin içindedir: kısa bacak momentuma karşı durur (2021 boğası).
- Haftalık devir yüksekse maliyet (gidiş-dönüş bacak başına ~%0,3) kenarı yiyebilir; devir raporlanır.
