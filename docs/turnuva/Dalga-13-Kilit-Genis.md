---
proje: TradeBot
created: 2026-10-01
type: turnuva-plani
durum: sonuçlandı — 3 kol A (2026-10-01); eşik %0,5 canlıya geçti
---
# Turnuva — Dalga 13: kilit açılımı, daha küçük açılımlar (ön kayıt)

Dosya: `config/turnuva/dalga13_kilit_genis.yaml`. Motor, veri ve maliyet dalga 6/6b ile aynı (`arastirma/kilit.py` →
`cekirdek/kilit.py`). Koşu: `tradebot arastirma kilit --dosya config/turnuva/dalga13_kilit_genis.yaml`.

## Neden

Scryne düzenli kazanç ve daha çok işlem istiyor (2026-10-01). Ölçülen yüzlerce fikirden kapıyı geçen tek aile kilit
açılımı kısası (6b, A: Sharpe 0,89, DSR 0,96). Yeni piyasalarda kaybetmek yerine kanıtlı ailenin kapasitesi sınanır:
eşik düşerse olay sayısı artar. Keyrock'un 16.000+ açılım çalışması etkinin her büyüklükte olduğunu ama büyük ve
ekip açılımlarında sert olduğunu söylüyor (dalga 6 gerekçesi).

## Kural

6b ile aynı (giriş açılımdan 7 gün önce, çıkış açılım günü; token perp kısa + BTC perp uzun; risk motoru tavanları),
iki fark: olay başına bacak nominali %10 → %5 (aynı tavanla en çok 10 açık olay) ve açılım eşiği ızgarada.

| Deneme | Eşik (azami arzın) | Nominal |
| --- | --- | --- |
| `oran=0.01` | ≥ %1 (6b ile aynı olaylar; yalnız nominal etkisi) | %5 |
| `oran=0.005` | ≥ %0,5 | %5 |
| `oran=0.0025` | ≥ %0,25 | %5 |

DSR aile `kilit_kisa`: dalga 6'nın 6 + 6b'nin 1 + bu 3 = 10 deneme.

## Önsel (dürüst, koşudan önce)

- Küçük açılımda etki küçük olabilir; maliyet (gidiş-dönüş ~%0,3 bacak başına) sabit kalır.
- Aynı veri, aynı dönem: kör dönem (2025+) 6b'de de görüldü, bu dalgada bağımsız kanıt değildir. Asıl sınama paper.
- Sonuç ne olursa olsun canlı kola dokunmadan önce paper'da ayrı kol olarak girer.

## Sonuç (2026-10-01, ön kayıt 7dd5489): **üç deneme de A**

| Deneme | Sharpe | Yıllık | En kötü düşüş | DSR (10) | Örneklem içi | Kör (2025+) | Stres 2x | Olay | Olay ort. (t) |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| eşik %1, nominal %5 | 0,94 | +%8,0 | −%10 | 0,97 | +%1,5 | +%24,7 | +%6,2 | 442 | +%2,09 (2,5) |
| **eşik %0,5** | **0,99** | **+%12,2** | **−%17** | **0,98** | **+%5,8** | **+%28,9** | **+%9,0** | **802** | **+%1,77 (3,2)** |
| eşik %0,25 | 0,93 | +%12,4 | −%17 | 0,97 | +%6,5 | +%27,5 | +%8,6 | 931 | +%1,56 (3,2) |

Yıllar (eşik %0,5): 2021 −%4,7, 2022 +%0,1, 2023 +%6,9, 2024 +%23,5, 2025 +%29,8, 2026 (Eylül'e kadar) +%18,4. En
kötü hafta −%7,7. 6b ile kıyas (aynı dönem): Sharpe 0,89 → 0,99, düşüş −%20 → −%17, örneklem içi +%2,9 → +%5,8, olay
382 → 802; kör dönem +%44 → +%29 (daha az yoğunlaşmış).

**Karar (Claude, 2026-10-01):** eşik %0,5, nominal %5 kolu paper ve gerçek (Demo) kilit kollarında 6b'nin yerine
geçti. İki kolun da henüz pozisyonu yoktu (ilk giriş 2 Ekim 00:05 UTC); geçişin maliyeti yok. Yeni kollar
`d13:kilit_kisa@kilit_perp@1d` ve `#gercek`; 6b kolları defterde "durdur: yerine_d13". Seçim aynı veride üç varyant
arasından yapıldı: DSR bunu 10 denemeyle sayıyor; asıl bağımsız sınama paper ve Demo.
