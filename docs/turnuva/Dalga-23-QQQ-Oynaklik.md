---
proje: TradeBot
created: 2026-10-24
type: turnuva-plani
durum: ön kayıt (koşudan önce commit edildi)
---
# Turnuva — Dalga 23: QQQ oynaklık zamanlaması, uzun veri (ön kayıt)

Dosya: `config/turnuva/dalga23_qqq_oynaklik.yaml`. Kod: `arastirma/endeks_oynaklik.py` (saf ağırlık + `backtest.calistir`;
`tests/test_endeks_oynaklik.py`). Karar: Claude, 2026-10-24 gecesi (Scryne: "amacım para kazanmak").

## Soru

Scryne'ın sorusu "bot bana QQQ'yu alıp beklemekten fazla para kazandırır mı". Nasdaq kollarının hiçbiri backtest'te QQQ
al-tutu geçmedi. Bu dalga kesitsel seçimi bırakıp tek bir şeyi sorar: QQQ'nun **kendisini** gerçekleşen oynaklığa göre
ölçeklemek (sakin piyasada daha çok, fırtınada daha az) aynı ya da daha iyi parayı daha az düşüşle verir mi; 2x tavana
izin verilince al-tutu geçer mi?

Kaynak: Moreira, Muir (2017), *Volatility-Managed Portfolios*, JF 72(4): piyasa portföyünü oynaklığın tersiyle ölçeklemek
Sharpe'ı artırır (oynaklık kümelenir, getiri onunla orantılı artmaz). Karşı kanıt: Cederburg, O'Doherty, Wang, Yan (2020),
*On the performance of volatility-managed portfolios*, JFE 138(1): örneklem dışında tutarlı üstünlük yok. Önsel: tek
endekste etki küçük, bilinen.

## Kural

- Veri: Yahoo `ARCA:QQQ` günlük, 1999-03-10 → 2026-10-23 (içinde 2000–02 çöküşü −%83, 2008, 2020, 2022). Nakit `ARCA:SHY`
  (2002-07'den; öncesi nakit getirisi 0, aleyhte).
- Ağırlık (kapanışta, yalnız ≤ t verisi): w = min(tavan, hedef / σ̂), σ̂ son `pencere` günün günlük log getirisinin
  yıllıklandırılmış std'si. Pozisyon sonraki açılışta kurulur (kural 4).
- Maliyet (aleyhte): taraf başı 3 bps (ücret 1 + yarım spread 1 + kayma 1; `ARCA` modeli). Boştaki kısım (1 − w)
  SHY'nin açılıştan açılışa getirisini kazanır. Ödünç kısım (w − 1) OECD ABD 3 ay faizi (2 ay gecikmeli) + %1,5 öder;
  2009 öncesi ve eksik ayda sabit %7. Temettü: iki taraf da açılış fiyatıyla ölçülür (QQQ temettüsü yok sayılır, kıyas
  tutarlı).
- Izgara (8 deneme, yeni aile `oynaklik_zamanlama`): hedef {0,15, 0,20} × pencere {20, 60} × tavan {1, 2}.
- Kıyas (deneme değil, bilgi): QQQ al-tut (w = 1) ve 2x al-tut (w = 2, aynı finansman).

## Risk kuralları ile ilişki (dürüst, koşudan önce)

- Canlı risk motorunda enstrüman tavanı %50: tek ETF'te özkaynağın yarısından fazlası tutulamaz. Bu dalga tavanı
  araştırmada kaldırır; bir varyant geçerse canlıya girmesi Scryne'ın açık tavan onayını ister (kural 7).
- Acil durdurma −%25: QQQ al-tutun kendisi 1999–2026'da bunu defalarca aşar. Her varyant için "−%25 ilk ne zaman" raporlanır;
  canlıda kol orada durur.

## Karar ölçütü (sonuçtan önce yazıldı)

- **A (proje kapısı):** DSR ≥ 0,95 (aile 8 deneme), walk-forward (IS 3 yıl → OOS 1 yıl, aynı tavan grubunda en iyi IS
  Sharpe) OOS yıllık > %4,5, yılların ≥ %60'ı pozitif, en kötü hafta ≥ −%10, −%25'e hiç düşmedi.
- **"QQQ'dan fazla para":** tam dönem yıllık bileşik > QQQ al-tut **ve** iki yarıda da (1999-03 → 2012-12, 2013-01 →
  2026-10) > QQQ al-tut **ve** en kötü düşüş ≤ QQQ'nunki.
- **"Aynı para, daha az risk":** tam dönem yıllık ≥ QQQ'nun %90'ı **ve** en kötü düşüş ≤ QQQ'nunkinin %60'ı, iki yarıda da.
- Hiçbiri yoksa sıfır hipotezi ayakta kalır: tek endeksi oynaklıkla zamanlamak bu kurallarla QQQ'nun yerini tutmaz.
