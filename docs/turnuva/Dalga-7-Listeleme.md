---
proje: TradeBot
created: 2026-09-29
type: turnuva-plani
durum: ön kayıt (koşudan önce commit edildi)
---
# Turnuva — Dalga 7: yeni listelenen token perp kısası (ön kayıt)

Dosya: `config/turnuva/dalga7_listeleme.yaml`. Veri: `tradebot veri listeleme`. Motor: kilit motoru (`arastirma/kilit.py`,
karar `cekirdek/kilit.py`); olay üretimi `arastirma/listeleme.py`.

## Neden

Kilit kolu (dalga 6) ilk gerçek ikinci getiri kaynağı oldu: fiyat deseni değil, yapısal arz akışı. Aynı akışın en yoğun
anı listelemedir. 2024'ten beri yeni token'ların çoğu düşük dolaşım / yüksek FDV ile listeleniyor; airdrop alıcıları ve
erken yatırımcılar satıyor, piyasa yapıcı ve borsa ilgisi ilk günlerden sonra azalıyor. Binance Research'ün "low float,
high FDV" raporu (Mayıs 2024) ve piyasa takipçilerinin 2024–25 ölçümleri yeni listelemelerin çoğunun ilk aylarda BTC'nin
gerisinde kaldığını söylüyor. Kural tamamen kodla kurulur (listeleme anı kontrat kaydından); Jev yön vermez (kural 8).

**Önsel (dürüst):** etki biliniyor, bu yüzden fiyatlanmış olabilir. Kalabalık kısa pozisyon funding'i negatife iter
(kısa öder); ayrıca yeni token'larda sert kısa sıkıştırmaları olur. Kol ikisini de gerçek funding ve günlük fiyatla öder.

## Olay ve kural

- Olay: Binance USDT-M perp'inin `onboardDate`'i (listeleme anı, UTC gün başına indirilir) 2021-01-01 sonrası.
- Dışlananlar (koşudan önce sabit): BTC, ETH, sabit paralar, fiat ve endeks kontratları (`listeleme.HARIC`); ilk günlük
  mumu listeleme anından 3 günden fazla önce olan kontratlar (yeniden listeleme / ad değişikliği: yeni token değil).
- İşlem: listelemeden `giris_gun` gün sonra 00:00 UTC açılışında token perp kısa + BTC perp uzun, bacak başına özkaynağın
  %10'u; listelemenin `bitis_gun`. günü açılışında kapat.
- Tavan: paper risk motorunun varsayılanları (BTC bacağı ≤ %50, açık brüt ≤ 1x): en çok 5 açık olay; fazlası reddedilir.
- Izgara (6 deneme): giriş 1 / 7 gün × çıkış 14 / 30 / 60. gün.

## Maliyet (aleyhte, koşudan önce sabit)

Taker %0,05 her bacak her yönde; kayma token %0,2 (yeni listeleme: kilit kolunun iki katı), BTC %0,01; funding gerçek.
Stres: 2 kat.

## Karar ölçütü

Dalga 6 ile aynı: yılların ≥ %60'ı pozitif, en kötü hafta ≥ −%10, en kötü düşüş ≥ −%30, 2 kat maliyette pozitif, kör
dönem (2025-01 → 2026-09) pozitif ve düşüşü ≥ −%30; A ayrıca DSR ≥ 0,95 (6 deneme, ayrı aile `listeleme_kisa`). Ek
bilgi: kilit koluyla haftalık korelasyon ve 50/50 karışım.

## Bilinen sınırlar

- **Hayatta kalan yanlılığı kısanın ALEYHİNE:** `exchangeInfo` yalnız kayıtlı kontratları verir; tamamen silinen
  (çoğunlukla çöken) token'lar eksiktir.
- Günlük mum: giriş/çıkış 00:00 açılışında; listeleme günü (gün 0) yüksek oynaklıklı ilk saatler ölçülmez.
- Kısa pozisyonun borsa riski (ADL, likidasyon) modellenmedi; %10 nominal ve BTC bacağı riski küçültür.
- Kilit koluyla aynı token'lar çakışabilir (listelemeden sonraki ilk kilit açılımları): korelasyon raporlanır.

## Sonuç (2026-09-29, koşu `dalga7`, ön kayıt 6ec60c3)

**Altı kol da KALDI; hepsi düşüş kapısından.** Olay: 582 nitelikli listeleme (2021-01 → 2026-09).

| Varyant | Sharpe | Yıllık | Düşüş | DSR | Kör yıllık | Olay (t) | İsabet | Kilitle kor. |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| giriş 1 / çıkış 14 | 0,72 | +%23,1 | −%61 | 0,70 | +%35 | +%4,7 (2,1) | %64 | +0,18 |
| giriş 1 / çıkış 30 | 0,64 | +%19,6 | −%57 | 0,64 | +%31 | +%6,9 (1,9) | %66 | +0,19 |
| giriş 7 / çıkış 30 | 0,57 | +%15,3 | −%45 | 0,57 | +%60 | +%5,3 (1,7) | %66 | +0,22 |
| giriş 1 / çıkış 60 | 0,16 | −%3,2 | −%68 | 0,22 | +%24 | +%2,9 (0,5) | %61 | +0,18 |
| giriş 7 / çıkış 60 | −0,01 | −%12,0 | −%68 | 0,12 | +%4 | −%0,2 (0,0) | %64 | +0,15 |
| giriş 7 / çıkış 14 | −0,18 | −%16,2 | −%82 | 0,05 | −%42 | −%0,6 (−0,3) | %59 | +0,07 |

Okuma:
- **Yön doğru, kuyruk öldürücü.** Giriş 1 / çıkış 14: olay medyanı +%10,8, yıllar 2021 +%14, 2022 +%13, 2023 +%39,
  2024 +%6, 2025 +%43, 2026 +%21 (hepsi pozitif). Ama 37 olayda kısa bacak nominalinin yarısından fazlasını kaybetti
  (AVNT 2025-09 −%298, GAS 2023-11 −%168, STBL, M, Q 2025 ~−%155): tipik kısa sıkıştırması.
- Etki ilk haftada: giriş 7 / çıkış 14 negatif.
- Kilit koluyla korelasyon düşük (+0,18); 50/50 karışım (giriş 1 / çıkış 30) Sharpe 0,86, düşüş −%24.

Sonuca bakıp dalga 7 değiştirilmedi. Kuyruğu kesen zarar-kes kuralı ayrı ve yeni bir denemedir: §7b.

## 7b — zarar-kes (ön kayıt, `config/turnuva/dalga7b_listeleme_kes.yaml`)

Giriş 1 × çıkış 14/30 × zarar-kes %30/%50/%100 (6 deneme; aile DSR'ı 12 denemeyle). Olayın birikmiş zararı (bacak
nominaline oranla, günlük açılıştan açılışa) eşiğe ulaşınca bir sonraki açılışta iki bacak kapanır (`cekirdek/kilit.py`
`zarar_kes`, paper ile ortak çekirdek). Gün içi sıçramalar görülmez (aleyhte: gerçek zarar eşiği aşabilir, ölçülen de
aşar). **Dürüstlük:** kural ve kör dönem sonuca bakıldıktan sonra; kör sonuç bağımsız kanıt sayılmaz, B/A çıkarsa asıl
kanıt paper'dır.

## 7b sonucu (2026-09-29, koşu `dalga7b`, ön kayıt c533f17)

**Altı kol da KALDI.** Aile DSR'ı 12 denemeyle.

| Varyant | Sharpe | Yıllık | Kötü hafta | Düşüş | DSR | Kör yıllık | Olay (t) |
| --- | --- | --- | --- | --- | --- | --- | --- |
| giriş 1 / çıkış 14 / kes %50 | 0,87 | +%28,4 | −%17 | −%35 | 0,80 | +%44 | +%5,0 (2,4) |
| giriş 1 / çıkış 14 / kes %30 | 0,69 | +%21,1 | — | −%47 | 0,67 | +%29 | +%3,9 (1,9) |
| giriş 1 / çıkış 14 / kes %100 | 0,52 | +%13,6 | — | −%53 | 0,51 | +%7 | +%3,4 (1,5) |
| giriş 1 / çıkış 30 / kes %30–100 | 0,40–0,46 | +%7–9 | — | −%69–77 | ≤ 0,45 | −%19 … +%3 | t ≤ 1,2 |

**Kapılar çok mu sıkı? (Scryne'ın sorusu, ölçüldü):** en iyi kol yalnız en kötü hafta ve düşüş kapılarında kaldı; bu
kapılar sabit nominalde uygulanıyor. Kol, kapıya sığacak küçük nominallerle yeniden ölçüldü (bilgi, aday değil):

| Nominal | Sharpe | Yıllık | Kötü hafta | Düşüş |
| --- | --- | --- | --- | --- |
| %10 (ön kayıt) | 0,87 | +%28,4 | −%17 | −%35 |
| %7 | 0,61 | +%14,7 | −%13 | −%42 |
| %6 | 0,72 | +%17,1 | −%12 | −%38 |
| %5 | 0,40 | +%7,0 | −%14 | −%40 |

Küçük nominalde tavan (BTC ≤ %50, brüt ≤ 1x) daha çok eşzamanlı olayı kabul ediyor ve eklenen olaylar sonucu bozuyor:
0,87, tavana takılan olayların seçimine bağlı şanslı bir sonuçtur. Kapı burada bir kırılganlığı yakaladı; kapı kuralı
değişmedi. Olay düzeyinde etki (ilk hafta, medyan pozitif) gerçek görünüyor ama kuyruk riskiyle birlikte portföy olarak
güvenilir değil. Paper'a girmez.

**İleriye dönük sınama (ön kayıt):** strateji günlük açılış fiyatı ve kontrat kaydıyla kurulduğu için paper olmadan da
bağımsız ölçülebilir: 2027-01-01'de `giris 1 / çıkış 14 / kes %50` (nominal %10, aynı tavanlar) yalnız 2026-09-20 →
2026-12-31 listelemeleriyle yeniden koşulur. Olay ortalaması ≤ 0 ise fikir kapanır.
