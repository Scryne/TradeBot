---
proje: TradeBot
created: 2026-10-24
type: turnuva-plani
durum: sonuçlandı — A yok; 'QQQ'dan fazla para' 1/8 (sınırda), acil durdurmayla canlıya uygun değil (2026-10-24)
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

## Sonuç (2026-10-24, ön kayıt 5f4d2cb; `data/turnuva/dalga23/sonuc.json`)

**A yok. "Aynı para, daha az risk" yok. "QQQ'dan fazla para" 8 varyantın 1'inde, sınırda.** 6.949 gün, OECD faizi
2009-01 → 2026-09.

| | Yıllık | Sharpe | En kötü düşüş | 1999–2012 | 2013–2026 | −%25 ilk |
| --- | --- | --- | --- | --- | --- | --- |
| QQQ al-tut (kıyas) | +%10,0 | 0,49 | −%83,1 | +%1,9 (−%83) | +%18,7 (−%37) | 2000-04 |
| 2x al-tut (kıyas) | +%7,1 | 0,40 | −%99,2 | −%11,9 | +%30,3 (−%65) | 2000-01 |
| hedef 0,15 · 20 gün · 1x | +%9,8 | 0,70 | −%45,3 | +%5,0 | +%14,8 (−%25) | 2001-03 |
| hedef 0,15 · 60 gün · 1x | +%9,6 | 0,68 | −%39,6 | +%5,6 | +%13,7 (−%26) | 2001-04 |
| hedef 0,20 · 20 gün · 1x | +%11,0 | 0,68 | −%56,1 | +%5,3 | +%17,1 (−%30) | 2001-01 |
| hedef 0,20 · 60 gün · 1x | +%11,1 | 0,67 | −%49,9 | +%6,6 | +%15,8 (−%31) | 2001-01 |
| **hedef 0,20 · 20 gün · 2x** | **+%12,5** | 0,66 | −%56,1 | +%5,6 | **+%19,9** (−%31) | 2001-01 |
| hedef 0,20 · 60 gün · 2x | +%11,9 | 0,64 | −%49,9 | +%5,6 | +%18,5 (−%32) | 2001-01 |
| hedef 0,15 · 20 / 60 gün · 2x | +%10,2 / +%9,8 | 0,68 / 0,67 | −%45 / −%40 | +%5,4 / +%5,2 | +%15,3 / +%14,6 | 2001 |

- Oynaklık yönetimi QQQ'yu her varyantta risk ayarlı iyileştirir (Sharpe 0,64–0,70 ↔ 0,49, en kötü düşüş yarıya yakın),
  walk-forward OOS yıllık +%10,9 (1x) / +%11,3 (2x). DSR ~1,0 (sıfıra karşı; QQQ'ya karşı değil).
- Fazla para ölçütünü yalnız en kaldıraçlı varyant (0,20 · 20 · 2x) geçer; ikinci yarıdaki fark +1,2 puan, komşusu
  (60 gün) ikinci yarıda kalır: plato değil, aşırı uyum payı yüksek.
- Bütün varyantlar 2001'de −%25'i aşar, en kötü hafta −%14 / −%20: proje kapısından (acil durdurma, en kötü hafta) geçmez.
  Canlıya girmesi hem enstrüman tavanı (%50) hem acil durdurma kuralının değişmesini ister (kural 7: Scryne).
- Dürüst okuma: QQQ'nun uzun dönem getirisi 2016–2025'in %19,8'i değil, %10'dur ve −%83 düşüşle gelir. Oynaklıkla
  ölçeklemek aynı parayı yaklaşık yarı düşüşle verir; kaldıraçla "fazla para" kanıtı zayıftır.

## Ek (bilgi, deneme değil): kilit kolu ile birleşim, 2021-01 → 2026-10 (302 hafta)

Kilit kolu (dalga 22 verisi) ile 0,15 · 20 · 1x varyantın haftalık getirileri. Varyant dalga 23 sonuçları görüldükten
sonra seçildi (kaldıraçsız, düşük hedefli, risk kurallarına en yakın grup; 60 günlük komşusu benzer): seçim serbestliği
var. Dönem büyük ölçüde iki kuralın da örneklem içi. Bu ek bir karar vermez, sabah Scryne'la konuşulacak öneriye kanıttır.

| | Yıllık | Sharpe | En kötü düşüş | En kötü hafta |
| --- | --- | --- | --- | --- |
| QQQ al-tut | +%15,3 | 0,76 | −%34,5 | −%11,5 |
| Kilit | +%12,2 | 0,92 | −%17,2 | −%7,7 |
| Oynaklık yönetimli QQQ | +%12,7 | 0,87 | −%22,9 | −%5,9 |
| **%50 kilit + %50 oynaklık yönetimli QQQ** | **+%13,2** | **1,48** | **−%11,6** | **−%3,0** |

Korelasyon kilit ↔ oynaklık yönetimli QQQ **−0,27** (kilit ↔ QQQ −0,26). Mekanizma: kilit altcoin kısa + BTC uzundur;
risk iştahında altcoin'ler BTC'yi geçer (kilit kaybeder, hisse kazanır), risk kaçışında tersi. Birleşimin %50 QQQ ağırlığı
hedef/σ ile ölçeklendiği için toplam özkaynağın %50'sini aşmaz: mevcut enstrüman tavanına sığar.
