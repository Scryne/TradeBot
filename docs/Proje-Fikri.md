---
proje: TradeBot
created: 2026-09-24
updated: 2026-09-24
type: proje-fikri
status: onaylandı (sürüm 2 — kurumsal, çok piyasalı)
kaynak: docs/Arastirma.md + Scryne ile 2026-09-24 karar konuşmaları
---
# TradeBot — Proje Fikri (v2)

> Sürüm 1 (kripto odaklı taslak) aynı gün Scryne'ın yön değişikliğiyle geçersiz oldu:
> "ben kurumsal bir trade bot yapmak istiyorum. tüm modellerde çalışacak bir trade bot." Eski metin git
> geçmişinde duruyor.

## Problem

Scryne kendi sermayesini, insan müdahalesi olmadan çalışan ve kurumsal kalitede bir sistemle büyütmek
istiyor. Hazır perakende botlar üç yerde başarısız oluyor:
- tek piyasaya kilitli olmaları,
- doğrulanmamış strateji kullanmaları,
- maliyeti ve riski ihmal etmeleri (Araştırma §0, §11).

Kurumsal sistemlerin sahip olduğu parçalar genelde bireysel kullanıcının elinde yoktur: emir yönetimi,
katmanlı risk, mutabakat, denetim izi, çok piyasalı muhasebe. TradeBot bu parçaları tek kişinin
yönetebileceği ölçekte bir araya getirir. Hangi piyasada hangi stratejinin kazandırdığını da tahmin
etmez, **ölçerek** bulur.

## Kimlik

| Boyut | Karar |
| --- | --- |
| **Kalite** | Kurumsal: emir yönetimi, katmanlı risk motoru, mutabakat, denetim izi, yeniden üretilebilirlik |
| **Kullanıcı** | Yalnız Scryne, kendi hesabı ve kendi parası. Başkasına ürün, sinyal ya da portföy yönetimi yok |
| **Piyasalar** | Çok piyasalı: kripto, forex, emtia, endeksler, ABD ETF/hisse, BIST (ve sonraki dalgalarda vadeliler) |
| **Otonomi** | Tamamen otonom: strateji seçimi, sermaye dağıtımı, emir; riski azaltan her şey otomatik |
| **Para** | İlk aşamada gerçek para yok: backtest + paper. Gerçek para ayrı bir kararla ve sonra |

## Hedef

**Scryne'ın kararı:** bir hafta boyunca olabildiğince yüksek kazanç.

**Ölçülebilir tanım (onaylandı):** Haftalık net kazanç maksimize edilir. Ama tek bir hafta değil, **çok
sayıda haftanın ortalama bileşik haftalık büyümesi** ölçülür ve **en kötü haftaya sınır** konur.
Gerekçe: tek haftanın sonucu büyük ölçüde şanstır. Tek haftayı maksimize eden seçim, sistemi en yüksek
riske ve iflasa sürükler (Araştırma §5.11).

| Ölçüt | Değer |
| --- | --- |
| Ana puan | Ortalama net haftalık bileşik büyüme (log getiri) |
| Kol başına en kötü hafta kapısı | ≥ −%10 |
| Kol başına en kötü düşüş kapısı | ≥ −%30 |
| Portföy acil durdurma | −%25 |
| İstatistik kapısı | Deflated Sharpe anlamlı (deneme sayısına göre) |

## Temel Özellikler (v1)

1. **Çok piyasalı çekirdek.** Enstrüman kaydı, piyasa takvimleri, çoklu para birimi muhasebesi, piyasa
   başına maliyet modeli. Motor: NautilusTrader (Faz 0 spike koşuluyla).
2. **Veri platformu (ilk dalga, ücretsiz kaynaklar):**
   - Binance (kripto)
   - Dukascopy (FX, metaller, emtia, endeks CFD)
   - Tiingo / Massive / Alpaca (ABD ETF'leri)
   - borsapy / Yahoo (BIST günlük) ve KAP

   Ham veri değişmez. Veri point-in-time tutulur. Metinlerde zaman ilk yayın zamanıdır.
3. **Strateji turnuvası.** Yedi aile yarışır: trend/momentum, kesitsel momentum, ortalamaya dönüş, carry,
   takvim etkileri, gün içi kırılım, olay tabanlı. Eleme hunisi beş aşamalıdır: test planı → hızlı tarama
   → sağlamlık → gerçekçi yürütme → paper. Kazanan puana ve kapılara göre ilan edilir, ham getiriye göre
   değil.
4. **Otonom sermaye dağıtıcı.** Kol (strateji × piyasa) başına risk bütçesi, korelasyon kontrolü ve
   haftalık yeniden dağıtım. Sermaye kademeli verilir: 4 hafta paper → %25, 8 hafta → %50, 12 hafta →
   %100.
5. **Kaldıraç.** Yarım Kelly. Kodda sabit 3x tavan. 5x ve üstü hiçbir modda yok.
6. **Beş katmanlı risk motoru.** Katmanlar: emir öncesi, pozisyon, kol, portföy, sistem. Motordan bağımsız
   bir gözetmen vardır. Portföy frenleri: günlük −%3, haftalık −%8, acil durdurma −%25. Acil durdurmadan
   sonra yeniden başlatma yalnız Scryne'ın onayıyla olur.
7. **Zekâ katmanı (Jev).** Jev yargılar, kod uygular.
   - **A — Koruma:** haber/duyuru vetosu, KAP, SEC, pump/manipülasyon, borsa bildirimleri, emir reddi
     sınıflandırma.
   - **B — Veri doğruluğu:** kurumsal işlem tespiti, enstrüman eşleme, sözleşme şartnamesi okuma, haber
     tekilleştirme.
   - **D — Operasyon:** log/alarm triyajı, rapor doğrulama, deneme tekrar dedektörü, Telegram salt-okuma
     sorguları.
   - **C — Strateji özellikleri:** olay özellikleri, merkez bankası tonu, şirket açıklaması tonu, metin
     tabanlı rejim. Ölçülür, değer katan girer.
   - Her strateji Jev'li ve Jev'siz yarışır, Jev'in katkısı sayıyla görünür.
   - Belirsiz durumda NVIDIA ücretsiz modeline yükseltilir. O da emin değilse riski azalt.
8. **Agresif gözlem kolu.** Paper'da aynı stratejiler tam Kelly ve 3x tavanla koşar. Sermaye dağıtımına
   girmez.
9. **Operasyon.** Evdeki ikinci bilgisayar (Windows, 16 GB RAM, 1 TB, kablolu internet), WSL2 + Docker
   Compose, Telegram bildirimleri (kritik/uyarı/bilgi), Tailscale üzerinden web pano, günlük yedek,
   denetim izi.

## Kapsam Dışı

- 5x ve üstü kaldıraç, martingale, kayıpta pozisyon büyütme.
- Market making, HFT, borsalar arası arbitraj.
- TensorTrade/RL'yi temel olarak kullanmak (ileride deney olabilir).
- Jev'e ya da yükseltme modeline yön, fiyat, boyut ya da emir kararı verdirmek.
- Başkasının parası, sinyal paylaşımı, copy trading, ürünleştirme.
- v1'de ücretli veri. Bir dalganın ölçümü fırsat gösterirse ayrı kararla açılır.
- v1'de gerçek para.

## Açık Sorular (Faz 0 spike'larında kapanacak)

1. NautilusTrader v2 (sürüm adayı) Windows/WSL2'de kararlı mı? Özel BIST/MT5 bağlantısı yazılabiliyor mu?
   (Olmazsa LEAN, o da olmazsa kendi çekirdeğimiz.)
2. Ücretsiz veri kaynaklarının gerçek kalitesi, hızı ve kapsamı. BIST gün içi verisi mümkün mü?
3. Jev güven eşikleri (A1/A2) ve NVIDIA kataloğunda yükseltme için en iyi model hangisi?
4. Paper canlı bağlantılar: ABD ETF'leri için hangi ücretsiz paper hesap Türkiye'den açılabilir? FX için
   MT5 demo köprüsü nasıl kurulur?
5. Vergi (gerçek para fazında, mali müşavirle).
