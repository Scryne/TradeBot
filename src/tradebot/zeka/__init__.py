"""Zekâ katmanı (Faz 6): Jev yargıları + belirsizlikte yükseltme modeli → olay (veto/uyarı).

Değişmez kural 8: Jev ve yükseltme modeli yalnız riski AZALTABİLİR. Yön, fiyat, boyut ve emir kararı verdirilmez.
Olaylar risk motorunun veto listesine girer (Portfoy.veto): o enstrümanda risk artırılamaz, azaltılabilir.
Backtest içinde canlı model çağrılmaz: yargılar `jev_yargi`'da dondurulur (model sürümü + soru ve girdi hash'i),
olaylar `olay`'da `gecerli_ms` ile point-in-time okunur.
"""
