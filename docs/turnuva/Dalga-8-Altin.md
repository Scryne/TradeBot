---
proje: TradeBot
created: 2026-09-29
type: turnuva-plani
durum: ön kayıt (koşudan önce commit edildi)
---
# Turnuva — Dalga 8: yalnız altın günlük trend (ön kayıt)

Dosya: `config/turnuva/dalga8_altin.yaml`. Seri `VADELI:XAU` (dalga 3 ile aynı: spot − ABD kısa faizi, fazla getiri).

## Neden

Scryne (2026-09-29): "BTC + ETH'de takılı kalmayalım; trade botlarının çoğu XAUUSD kullanıyor." Altın dört kez ölçüldü
(M15 gün içi, CFD trend, vadeli trend sepeti, Asya seansı); hiçbiri geçmedi. Ölçülmeyen tek açı altının **tek başına**
günlük trendidir: dalga 3'te altın gümüşle aynı sepetteydi (metal kırılımı Sharpe 0,25, düşüş −%58).

**Dürüstlük notu:** bu dalga altının 2023–26 yükselişi (+%136) ve dalga 3 kırılımı görüldükten sonra kuruldu; bu bir
geriye bakma yanlılığıdır. Karşı önlemler: ızgara ve boyut dalga 3 ile aynı (yeni ayar yok); trend ailesinin DSR'ı bütün
dalgaların denemeleriyle sayılır (kural 10); 2026-01 → 09 seçimden sonra kör ölçülür; al-tut ile kıyaslanır.

## Kural, ızgara, ölçüt

Dalga 3 ile aynı (16 deneme: tsmom 4, ma_yon 6, donchian 6; iki yönlü, %20 oynaklık hedefi, 3x tavan, frenler, walk-forward
IS 3 yıl → OOS 1 yıl, çıta 0 çünkü seri fazla getiri). Maliyet `VADELI:metal` modeli. Karar: B için tam dönem ve
walk-forward kapıları + 2026 kör dönemde seçilen varyant pozitif; A ayrıca DSR ≥ 0,95.
