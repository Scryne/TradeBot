---
proje: TradeBot
created: 2026-09-27
type: tasarim
durum: Faz 7 (paper canlı) — uygulanıyor
---
# Paper tasarımı (Faz 7)

Kod: `src/tradebot/canli/` (kollar, karar, defter, bar_akisi, dugum). Ayar: `config/paper.yaml`. Servis: compose `paper`.

## Kararlar (Claude, 2026-09-27; Scryne yetkiyi devretti)

1. **Her paper kolu kendi sanal defteriyle Nautilus sandbox'ta gerçekten işlem yapar** (kol başına 100.000 USDT
   sanal). B "sermayesiz gözlem" dağıtıcıdan pay almamak demektir. Maliyet, kayma ve sistem dayanıklılığı ancak gerçek
   emir akışıyla ölçülür.
2. **Karar, backtest'in aynı fonksiyonlarıyla verilir** (kural 3): `turnuva.grup_hazirla` → `hedef_uret` → son satır →
   `panel.dengele_adim` (bant, fren, veto). Backtest döngüsü de aynı `dengele_adim`'i çağırır.
   `tests/test_canli.py` canlı döngünün backtest ağırlık yolunu 1e-9 hassasiyetle ürettiğini doğrular (fren dahil).
   Refaktör sonrası kayıtlı turnuva sonuçları gerçek veriyle birebir yeniden üretildi.
3. **Veri:** canlı bar deposu (`data/canli`): ana depodan kopya + Binance REST ile yalnız kapanmış 1h barlar
   (ham yanıtlar ham depoda). 4h/1d, backtest'teki gibi 1h'den türetilir. Karar kolun son tamamlanmış sınırında kesilir.
4. **Zamanlama:** karar bar kapanışında, emir hemen gider, sandbox'ta canlı kotasyona karşı dolar (≈ sonraki barın
   açılışı, kural 4). Yeniden başlatmada son sınırın ilk saati içindeysek gecikmeli karar verilir, değilse sonraki
   sınır beklenir (`karar_kacirildi`): geç karar parity'yi bozar.
5. **Doğruluk kaynağı PostgreSQL defteridir** (göç 0006, hepsi yalnız eklenir): `paper_kol`, `paper_karar` (emirden önce
   yazılır; aynı kol+bar için ikinci karar olmaz), `paper_emir` (risk kararıyla), `paper_emir_olay` (dolum/ret),
   `paper_ozkaynak` (her saat, kapanışla işaretli, o saatin işlemlerinden önce). Kol tanımı değişirse aynı adla
   açılamaz: yeni paper dönemi = yeni kol adı.
6. **Toparlanma:** sandbox bellektedir. Açılışta defterdeki pozisyonlar `toparlanma` emirleriyle kurulur; bu dolumlar
   defteri ve maliyet ölçümünü değiştirmez.
7. **Mutabakat:** her kararın 5 dk sonrası Nautilus dolumlarından toplanan pozisyon ↔ defter. Fark → alarm, kol durur
   (katman 3/5: yalnız riski azaltan emir geçer).
8. **Risk:** her emir `RiskMotoru.onayla`'dan geçer (kural 5); kolun kendi portföyü, fren durumu, Jev'li kopyada veto.
   Toparlanma yalnız akıl kontrollerinden geçer (risk değişmez).
9. **Jev A/B:** her kol iki kopya (`+jev`: veto uygulanır). BTC/ETH'de veto çok nadir: fark büyük olasılıkla sıfıra
   yakın çıkar; bu da bir bulgudur.

## B → A terfi ölçütü (paper kanıtıyla)

8 haftalık paper, Sharpe ~1'lik bir kolun üstünlüğünü istatistiksel olarak kanıtlayamaz (yıllar gerekir). Terfi bu yüzden
"üstünlük kanıtlandı" değil, **"yürütme çalışıyor ve paper backtest'le çelişmiyor"** demektir. Sermaye kademeli
verilir (%25 → %50 → %100, Final Doküman §Sermaye dağıtıcı). Gerçek para Faz 12'de Scryne'ın ayrı kararıdır.

Bir kol A olur, eğer hepsi:
1. ≥ 8 hafta kesintisiz paper (düğüm kesintisi + mutabakat durdurması toplam sürenin < %2'si).
2. Kapılar paper'da da tutuyor: en kötü hafta ≥ −%10, en kötü düşüş ≥ −%30.
3. **Uygulama uyumu:** aynı dönemin backtest'i (canlı bar deposu, aynı parametre) ile paper özkaynağı arasındaki
   yıllıklaştırılmış takip hatası ≤ %5; gerçekleşen işlem maliyeti (ücret + kayma) ≤ backtest varsayımının 1,5 katı.
4. **Çelişki yok:** paper haftalık ortalamasının backtest haftalık dağılımına göre t ≥ −2.

Dağıtıcı ve agresif gözlem kolu bu belgeye eklenecek (Faz 7 devam).
