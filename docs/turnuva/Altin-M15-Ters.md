---
proje: TradeBot
created: 2026-09-30
type: turnuva-plani
durum: sonuçlandı — KALDI (2026-09-30)
---
# Turnuva — Altın M15 aynası: "kaybeden stratejinin tersi" (ön kayıt)

Dosya: `config/turnuva/altin_m15_ters.yaml`. Kod: `cekirdek/altin.py::_ters` (`ters_*`).

## Neden

Scryne bir video gösterdi (2026-09-30, @lionmastertrader): "%30 kazanma oranı, 1:2 R/R ile sinyal üreten kaybeden
stratejinin tam tersini al: %70 kazanma oranı, 1:0,5 R/R." Videonun prop challenge hesabı bir üstünlük değil, kural
yapısı sorusudur (yüksek kazanma oranı düşüşü küçültür, beklenen değeri değiştirmez). Ama altında test edilebilir bir
soru var: **maliyetten önce sistematik olarak kaybeden bir strateji var mı?** Varsa aynası maliyetten önce kazanır.

Bir stratejinin aynası, maliyetten önceki getirisinin tam tersini alır; maliyeti ise yine öder (iki taraf da spread
öder). Net: ayna ≈ −(orijinal net) − 2 × maliyet. Yani ayna ancak orijinal maliyetten önce de açıkça kaybediyorsa işe
yarar.

**Koşudan önce yapılan kaba hesap (Altın M15 sonuç dosyalarından):**

| Aile | Net/yıl | Maliyet/yıl | Maliyet öncesi | Aynanın kaba neti |
| --- | --- | --- | --- | --- |
| bant_donus | −%10,5 | %2,9 | −%7,5 | ≈ +%4,6 |
| ea_birlesik | −%12,9 | %2,3 | −%10,7 | ≈ +%8,4 |
| trend_geri_cekilme | −%4,9 | %2,7 | −%2,1 | ≈ −%0,6 |
| sikisma_kirilim | −%3,2 | %2,7 | −%0,5 | ≈ −%2,2 |
| kanal_kirilim | −%1,6 | %1,9 | +%0,3 | ≈ −%2,2 |
| seans_kirilim | −%0,6 | %2,3 | +%1,7 | ≈ −%4,0 |

**Dürüstlük notu (geriye bakma yanlılığı):** bu dalga sonuçlar görüldükten sonra kuruldu ve iki aile önceden umut
verici görünüyor. Karşı önlemler: (1) altı ailenin hepsi aynalanır, seçim yok; (2) ızgara, veri, boyut, maliyet ve
ölçüt orijinal ön kayıtla birebir; (3) aynı aile (`altin_m15`): DSR 32 + 32 = 64 denemeyle sayılır; (4) walk-forward
ve 2x maliyet stresi. Bant dönüşünün aynası ekonomik olarak "M15'te aşırı bant kırılımının devamı" demektir (kısa vadeli
momentum); 2023–26 altının güçlü yükselişi (+%136) bu yönde bir rejim etkisi olabilir: yıllık kırılım raporlanır.

## Kural

Pozisyon serisinin aynası: `ters_f(b) = −f(b)`. Stop ve hedef seviyeleri aynı kaldığı için bu, videodaki "TP ile SL yer
değiştirmiş ters işlem"le birebir aynıdır. EA risk katmanları (günlük ±3R, 3 ardışık kayıp, haber filtresi) orijinalin
gözünden işler (saf ayna; ayrı bir risk mantığı kurulmaz, yeni parametre yok).

## Karar ölçütü

Altın M15 ile aynı (A: DSR ≥ 0,95 + OOS + stres; B: sermayesiz paper gözlemi, DSR şartı yok).

**Demo'ya ne girer (sonuçtan önce yazıldı):** B ya da A çıkan en iyi ayna, demo hesaptaki altın gözlem kolunun yerine
geçer (kanal_kirilim kapanır; aynı düğüm, yeni kol adı). Hiçbiri geçmezse demo kolu değişmez.

## Sonuç (2026-09-30, koşu `dalgaaltin_m15_ters`, ön kayıt 44476f9)

**KALDI: altı aynanın hiçbiri geçmedi; iki taraf da kaybediyor.** Aile DSR'ı 64 denemeyle; hepsinde 0.

| Ayna | Sharpe | En kötü düşüş | OOS yıllık | Orijinal Sharpe |
| --- | --- | --- | --- | --- |
| ters_trend_geri_cekilme | 0,19 | −%9 | +%2,1 | −1,34 |
| ters_bant_donus | 0,01 | −%18 | +%2,1 | −1,98 |
| ters_kanal_kirilim | −1,58 | −%28 | −%12,8 | −0,18 |
| ters_ea_birlesik | −1,65 | −%39 | −%12,7 | −1,43 |
| ters_seans_kirilim | −1,76 | −%22 | −%11,9 | −0,08 |
| ters_sikisma_kirilim | −2,95 | −%29 | −%14,5 | −0,63 |

- **Hem strateji hem aynası kaybediyor:** maliyetten önceki getiri her ailede sıfıra yakın; kayıp maliyetten geliyor.
  M15 altında yılda binlerce işlem, spread ve kaymayla her iki yönü de eksiye çeker. "Tersini al" yalnız maliyetten
  önce sistematik kaybeden bir stratejide işe yarar; burada öyle bir strateji yok.
- **Koşudan önceki kaba hesap yanlıştı (bizim hatamız):** `maliyet_payi` sütunu yıllık maliyet sanıldı; oysa tanımı
  toplam maliyet / toplam |brüt getiri| (`arastirma/metrik.py`). Gerçek yıllık maliyet çok daha büyük. Ön kayıt bu hatayı
  olduğu gibi taşıyor; sonuç ölçütle verildi, tahminle değil.
- Demo'daki altın gözlem kolu değişmez (ön kayıttaki kural).
