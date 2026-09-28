---
proje: TradeBot
created: 2026-09-28
type: turnuva-plani
durum: ön kayıt (koşudan önce commit edildi)
---
# Turnuva — VİOP 1 (ön kayıt)

Dosya: `config/turnuva/viop1.yaml`. Kurallar dalga 1–2 ile aynıdır: kol tanımı, frenler, walk-forward (IS 3 yıl, OOS 1
yıl), stres ve A/B ölçütü (B için DSR şartı yok). Bu dosya koşudan önce commit edildi.

## Neden

Faz 8'in bitti kriteri VİOP ve MT5 piyasalarının kollarını paper turnuvasına almak. Bir kol paper'a ancak ön kayıtlı
bir backtest dalgasından geçerek girer. VİOP için ilk veri kaynağı NCM MT5 (Spike 08); bu dalga onun ilk kullanımı.

## Seri ve dönem

- `VIOP:XU030_SUREKLI`: NCM `XU30_YAKINVADE` + spot BIST30 (Yahoo) ile vade geçişi sıçraması ayıklanmış sürekli seri
  (`src/tradebot/veri/viop.py`, `docs/spikes/08-mt5.md`). Ham seri 2007–2026'da +%2.878, ayarlı +%334: fark tamamen
  vade geçişlerindeki sahte sıçramalar.
- Faiz farkı (baz erimesi) serinin içinde: getiri, TL mevduatının üzerindeki getiridir. Enflasyonun nominal trendi
  sonucu şişirmez.
- Dönem 2007-06 → 2025-10-31. Sonrasında kurumun serisinde 186 günlük delik var; delik sonrası paper ile birlikte
  gözlenir.

## Maliyet (aleyhte, koşudan önce sabit)

Taraf başı: komisyon 4 bps + BSMV %5, yarım spread 2 bps, kayma 2 bps (≈ 8,2 bps). Vade devri yıllık %1,2 (elde tutma
süresine orantılı). Ölçülen: 1 dk barlarda yarım spread medyan ~0,3 bps. Kurumun gerçek VİOP komisyonu bilinmiyor
(demo); gerçek para öncesi doğrulanır. Stres testi maliyeti 2 katına çıkarır.

## Aileler

Dalga 1'in tek enstrümanlık aileleri, ızgaralar aynı (30 deneme): tsmom (4), ma_yon (6), donchian_ls (6), zskor_donus
(6), rsi_donus (4), ay_donumu (4, yalnız long). Kesitsel momentum yok (tek enstrüman).

## Karar ölçütü

A: DSR ≥ 0,95 + OOS + stres + plato. B: ortak kapılar (sermayesiz paper gözlem). Sıfır hipotezi: hiçbir aile geçmez.
DSR'ın deneme sayısı ailenin defterindeki bütün taramalardır (dalga 1–2 dahil).

## Bilinen sınırlar

- Tek enstrüman: kol oynaklığı tek bir serinin oynaklığı; çeşitlendirme yok.
- 2016 öncesi gün içi zaman damgaları belirsiz; dalga yalnız günlük barla koşar.
- VİOP demo hesabı 10.000 TL; bir XU030 kontratının teminatı ~19.600 TL. Paper yürütmesi simüle olduğu için bu,
  boyutu değil yalnız emir testlerini sınırlar.

## Sonuç (2026-09-28, koşu `dalgaviop1`)

**Hiçbir kol geçmedi; sıfır hipotezi ayakta.**

| Kol | Sharpe | DD | OOS yıllık | Kalma nedeni |
| --- | --- | --- | --- | --- |
| tsmom | 0,54 | −%22 | +%0,7 | OOS en kötü düşüş −%41 (kapı −%30). Diğer bütün kapılar geçti (yılların %71'i pozitif, rejim ve stres pozitif). |
| ay_donumu | 0,41 | −%21 | −%0,4 | OOS negatif (DSR 0,60, en yüksek) |
| donchian_ls | 0,33 | −%38 | −%0,5 | Tam dönem kapıları, OOS negatif |
| ma_yon | 0,30 | −%27 | +%2,0 | Tam dönem kapıları, OOS düşüş −%33 |
| zskor_donus | −0,03 | −%38 | −%2,9 | Negatif |
| rsi_donus | −0,11 | −%18 | −%1,5 | Negatif, stres negatif |

Okuma: BIST30 vadelisinde tek enstrümanlık trend, faiz farkı ve maliyet sonrası TL mevduatını ancak sınırda geçiyor ve
uzun düşüşler veriyor. Ortalamaya dönüş aileleri maliyeti karşılamıyor. Sonuca bakıp eşik ya da ızgara değiştirilmedi
(kural 10). Sonraki VİOP denemesi yeni bir ön kayıtla ve yeni bir fikirle olur (ör. TL taşıma getirisi, çok varlıklı
VİOP sepeti); bu dalganın denemeleri defterde sayılı.
