---
proje: TradeBot
created: 2026-10-01
type: turnuva-plani
durum: ön kayıt
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

## Sonuç

(koşudan sonra eklenecek)
