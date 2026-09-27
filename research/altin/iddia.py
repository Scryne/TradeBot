"""Altın EA videosundaki iddianın ölçümü: "1 dolarlık hesapla 0,01 lot, her işlemde para 2 katına çıkıyor".

Gerçekler (sözleşme):
- XAUUSD 0,01 lot = 1 troy ons. Altın 1 $ hareket ederse kâr/zarar 1 $.
- 1 $'lık hesapta 1 $ kâr = paranın 2 katı; 1 $ zarar = hesap sıfır. Yani her işlem, fiyatın ±1 $'lık iki bariyerinden
  hangisine önce değdiği sorusudur. Spread (alış-satış farkı) bu 1 $'ın içinden ödenir.
- Marjin: 1 ons'u açmak için gereken teminat = fiyat / kaldıraç. 1 $'la açabilmek için kaldıraç ≥ fiyat (~3.000–4.000:1).

Ölçüm (gerçek dakikalık XAUUSD BID, Dukascopy):
- Rastgele başlangıç dakikaları (hafta içi, 01–21 UTC), yön yazı-tura (EA'nın sinyalinin yönü bilinmiyor; eğer EA'nın
  gerçek bir üstünlüğü varsa, p yazı-turanın üstünde olmalı, aşağıda "gereken üstünlük" hesaplanır).
- Alış: giriş = BID + spread; kazanç BID ≥ giriş + 1; kayıp BID ≤ giriş − 1 (hesap sıfır). Satış simetrik (ASK = BID +
  spread). Dakika içinde iki bariyer de geçilirse sıra bilinmez: kötümser (kayıp) ve iyimser (kazanç) ikisi de raporlanır.
- Spread senaryoları: 0,20 / 0,35 / 0,50 $ (ECN … standart perakende hesap).
Çıktı: bir işlemde ikiye katlama olasılığı p, bariyere varış süresi, art arda k katlama olasılığı p^k, 1.000 kişiden
kaçının 5 / 10 art arda katlama yapacağı (videoya çıkanlar), işlem başı beklenen değer.

Kullanım (host): python research/altin/iddia.py [--ornek 20000] [--gun 180]
"""
from __future__ import annotations

import argparse
import json
from datetime import UTC, datetime

import numpy as np
import polars as pl

from tradebot.ayar import ayarlar
from tradebot.veri.depo import BarDepo

SPREADLER = (0.20, 0.35, 0.50)
BARIYER = 1.0          # 0,01 lot + 1 $ hesap: +1 $ = 2 kat, −1 $ = sıfır
AZAMI_DK = 7 * 24 * 60  # bir hafta içinde sonuçlanmayan örnek dışarıda (yok denecek kadar az)


def simule(t, h, lo, c, bas: np.ndarray, yon: np.ndarray, spread: float) -> dict:
    kazanc_k, kazanc_i, sure = 0, 0, []
    for i, y in zip(bas, yon, strict=True):
        giris_bid = c[i]
        if y > 0:   # alış: ASK'tan gir (BID + spread), BID'den çık
            ust, alt = giris_bid + spread + BARIYER, giris_bid + spread - BARIYER
            son = min(len(c), i + 1 + AZAMI_DK)
            yuk, dus = h[i + 1:son] >= ust, lo[i + 1:son] <= alt
        else:       # satış: BID'den gir, ASK'tan (BID + spread) çık
            ust, alt = giris_bid - spread + BARIYER, giris_bid - spread - BARIYER  # ASK bariyerleri BID'e çevrili
            son = min(len(c), i + 1 + AZAMI_DK)
            yuk, dus = lo[i + 1:son] <= alt, h[i + 1:son] >= ust              # yuk = kazanç, dus = kayıp
        ik = np.flatnonzero(yuk)
        iz = np.flatnonzero(dus)
        k = ik[0] if len(ik) else 10**9
        z = iz[0] if len(iz) else 10**9
        if k == z == 10**9:
            continue
        sure.append(min(k, z) + 1)
        if k < z:
            kazanc_k += 1
            kazanc_i += 1
        elif k == z:
            kazanc_i += 1   # aynı dakika: iyimser sayımda kazanç
    n = len(sure)
    return {"n": n, "p_kotumser": kazanc_k / n, "p_iyimser": kazanc_i / n,
            "sure_dk_medyan": float(np.median(sure)), "sure_dk_p90": float(np.quantile(sure, 0.9))}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ornek", type=int, default=20000)
    ap.add_argument("--gun", type=int, default=180)
    ap.add_argument("--cikti", default="")
    x = ap.parse_args()
    a = ayarlar()
    d = BarDepo(a.veri_dizini).oku("DUKASCOPY:XAUUSD", "1m")
    d = d.filter(pl.col("acilis_ms") >= d["acilis_ms"].max() - x.gun * 86_400_000).sort("acilis_ms")
    t = d["acilis_ms"].to_numpy()
    h, lo, c = d["high"].to_numpy(), d["low"].to_numpy(), d["close"].to_numpy()
    saat = (t // 3_600_000) % 24
    gun = (t // 86_400_000 + 4) % 7  # 0 = Pazartesi
    uygun = np.flatnonzero((saat >= 1) & (saat < 21) & (gun < 5))
    uygun = uygun[uygun < len(c) - AZAMI_DK]
    rng = np.random.default_rng(0)
    bas = np.sort(rng.choice(uygun, size=min(x.ornek, len(uygun)), replace=False))
    yon = rng.choice([-1, 1], size=len(bas))
    fiyat = float(np.median(c))
    rapor = {"veri": {"bas": datetime.fromtimestamp(t[0] / 1000, UTC).isoformat(),
                      "bit": datetime.fromtimestamp(t[-1] / 1000, UTC).isoformat(), "dakika": len(t),
                      "medyan_fiyat": fiyat},
             "marjin_1_ons": {f"1:{k}": round(fiyat / k, 2) for k in (20, 100, 500, 2000)},
             "gereken_kaldirac_1_dolar": round(fiyat), "senaryolar": {}}
    for s in SPREADLER:
        r = simule(t, h, lo, c, bas, yon, s)
        p = r["p_kotumser"]
        r["ev_dolar_islem_basi"] = round(p * 1 - (1 - p) * 1, 4)
        r["art_arda"] = {str(k): p ** k for k in (1, 3, 5, 10)}
        r["bin_kisiden_5_art_arda"] = round(1000 * p ** 5, 1)
        r["bin_kisiden_10_art_arda"] = round(1000 * p ** 10, 3)
        rapor["senaryolar"][f"spread_{s:.2f}"] = r
    metin = json.dumps(rapor, ensure_ascii=False, indent=1)
    print(metin)
    if x.cikti:
        open(x.cikti, "w", encoding="utf-8").write(metin)


if __name__ == "__main__":
    main()
