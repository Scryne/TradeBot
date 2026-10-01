---
proje: TradeBot
created: 2026-10-01
type: turnuva-plani
durum: ön kayıt
---
# Turnuva — Dalga 12: spot delist duyurusu → perp kısa (ön kayıt)

Dosya: `config/turnuva/dalga12_delist.yaml`. Kod: `arastirma/delist.py` (olay kuralı, perp kaldırma, Jev eleme;
`tests/test_delist.py`), motor `arastirma/kilit.py` → `cekirdek/kilit.py` (paper kilit düğümüyle ortak, kural 3).
Veri: `tradebot veri delist` → `data/delist/`. Koşu: `tradebot arastirma kilit --dosya config/turnuva/dalga12_delist.yaml`.

## Neden

Araştırma planının 3. maddesi ("Olay tabanlı (Jev)"): C1 ölçümü (`docs/olcum/C1-Veto-Etkisi.md`) A1'in delist
vetosundan sonra tokenın BTC'ye göre 7 günde medyan −%28, 30 günde −%58 düştüğünü gösterdi. O ölçüm spot'taydı ve
"veto koruyor mu" sorusunu soruyordu; spot'ta açığa satış olmadığı için işlem fikri "perp gelince" diye bekledi. Perp
altyapısı artık var (dalga 6/7 motoru, kilit düğümü). Hisse piyasasında da delist edilen hissenin getirisi güçlü
negatiftir (Shumway 1997, *The Delisting Bias in CRSP Data*, Journal of Finance 52(1)). Kripto için yayımlanmış bir
çalışmayı doğrulamadım: kanıt yalnız kendi C1 ölçümüdür.

Kilit ve listeleme kısalarıyla ilişkisi: üçü de "arzı ya da talebi bozulan token kısa, BTC uzun" ailesidir, ama
tetikleyici farklıdır (takvim, listeleme, borsanın kararı). Trend kollarıyla korelasyonun düşük olması beklenir (bilgi).

## Kural

- **Olay (kod, kural 8):** Binance delist kataloğunda başlığında `Will Delist <liste> on <tarih>` geçen duyuru;
  başlığında Margin, Futures, Options, Loan, Perpetual ya da Pairs geçenler hariç. Tokenlar başlıktaki büyük harfli
  sembollerdir. Aynı token yeniden duyurulursa ilk duyuru sayılır.
- **Giriş:** olay günü T = yayın + 60 sn'den sonraki ilk 00:00 UTC açılışı (gün içinde duyurulan olayda 0–24 saat
  gecikme; ilk tepkinin bir kısmı kaçar: aleyhte). T'nin açılışında token perp kısa + BTC perp uzun, bacak başına
  özkaynağın %10'u.
- **Çıkış:** T + `cikis` gününün açılışı (7 ya da 30). Önce gelirse: Binance perp'in kaldırılmasını duyurduysa
  duyurudan sonraki ilk açılış (canlı düğümün `teslim_planli` kuralıyla aynı) ya da perp işlem görmeyi bıraktıysa
  (hacmi sıfır mum).
- **Jev'li varyant:** yalnız A1'in aynı tokena duyurudan ±1 gün içinde `token_delist` vetosu verdiği olaylar kalır
  (dondurulmuş yargılar; Scryne onayıyla kaldırılan vetolar sayılmaz). Jev olay eklemez, yalnız eler: riski azaltır.
- **Tavan:** risk motorunun varsayılanları (BTC bacağı ≤ özkaynağın %50'si, brüt ≤ 1x): aynı anda en çok 5 olay;
  toplu delist günlerinde fazlası sembol sırasıyla reddedilir.
- **Maliyet (aleyhte):** taker %0,05, token kayması %0,3 (kilitin 3 katı), BTC %0,01; gerçek funding geçmişi
  (kısa pozitif oranda alır, negatifte öder). Stres: maliyet 2x.

## Izgara (4 deneme, aile `delist_kisa`)

| Deneme | Tutma | Jev onayı |
| --- | --- | --- |
| `delist(cikis=7,jev=0)` | 7 gün | yok |
| `delist(cikis=30,jev=0)` | 30 gün | yok |
| `delist(cikis=7,jev=1)` | 7 gün | A1 `token_delist` |
| `delist(cikis=30,jev=1)` | 30 gün | A1 `token_delist` |

Dönem: 2022-02-01 → 2026-09-30; örneklem içi 2025-01-01'e kadar, kör 2025+. DSR yeni aile, 4 deneme. C1 bir strateji
denemesi değildi (spot olay ölçümü), aileye sayılmaz; ama hipotez ondan doğdu: sonuç C1 ile aynı veriyi görür, bu
yüzden asıl bağımsız sınama paper'dır.

## Kapılar (dalga 6b ile aynı)

DSR ≥ 0,95 → A; yılların ≥ %60'ı pozitif, en kötü hafta ≥ −%10, en kötü düşüş ≥ −%30 (tam ve kör), stres 2x
maliyette yıllık > 0, kör dönem yıllık > 0 → B; değilse KALDI.

## Önsel ve yanlılıklar (dürüst, koşudan önce)

- **Olay sayısı az olabilir.** Fizibilite (getiriye bakmadan): A1'in 155 `token_delist` vetosundan 69'unun
  `exchangeInfo`'da kayıtlı perp'i vardı; kaldırılmış kontratların mumları da API'den alınabiliyor, gerçek sayı veri
  hazırlığında çıkar. Delist edilen tokenların çoğu zaten küçük ve perp'i çoktan kaldırılmış olabilir.
- **Sıkıştırma riski:** dalga 7'nin listeleme kısası, olay ortalaması pozitifken kısa sıkıştırmaları yüzünden düşüş
  kapısında kaldı. Delist edilen tokenlarda da sert yükselişler bilinir (likidite azalır). Kapı bunu ölçer.
- **Kalabalık kısa:** duyurudan sonra funding negatife döner; kısa taraf öder. Gerçek funding geçmişi kullanılıyor.
- **Perp kaldırma zamanlaması:** kaldırma duyuruları yalnız arşivdeki başlıklardan çıkarılır. "Multiple ... Contracts"
  başlıklarında semboller gövdeden alınır: fazladan sembol erken kapanış demektir.
- **Jev yargıları geriye dönük üretildi** (2026-09, aynı model ve soru): canlıda aynı yargının aynı anda verileceği
  varsayılır. Jev'li varyant olay eklemediği için bu yanlılık yalnız eleme yönündedir.
- **Kör dönem ayrı değil:** C1 2022–2026'nın tamamını gördü. Kör dönem sonucu bağımsız kanıt sayılmaz.

## Sonuç

(koşudan sonra eklenecek)
