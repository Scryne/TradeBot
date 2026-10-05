"""Stopsuz "TP'ye kadar bekle" altın botunun ölçümü (BorsaWorkout "Otobot / Safe Bot" yapısı). ÖN KAYIT: bu dosya
koşudan önce commit edildi; parametreler sonuca bakılarak değiştirilmez (kural 10).

Scryne (2026-10-05) bir YouTube kanalının sattığı botu gösterdi: "14 haftadır %100 kazanma oranı", haftada %2–9,2.
Kanal sahibinin kendi anlatımı (video transkripti): işlemler 1–15 dakikada TP ile kapanır; ters giden işlem kapatılmaz
("müdahale etmeyin, kendisi TP edecek"); "%100" = o hafta açılan bütün işlemler hafta içinde kâra kapandı; lot önerisi
1.000 $ başına 0,01 ("en riskli"); bazı kullanıcılar 1.000 $'a 0,05–0,1 kullanıp hesabı patlatmış. Doğrulanmış kayıt
yok; bot XM'de (1:1000'e kadar kaldıraç, stop-out marjin seviyesi %20) çalışıyor.

Soru: giriş sinyali ne olursa olsun, "stop yok, TP'ye kadar bekle" yapısı gerçek altın fiyatında ne üretir? Botun
indikatörleri bilinmediği için giriş yönü yazı-turadır (sıfır üstünlük). Gerçek bir üstünlük olsaydı bağımsız
doğrulanmış bir kayıtta görünürdü; burada yapının kendisi ölçülür.

Kural (sabit, ön kayıtlı):
- Veri: Dukascopy XAUUSD dakikalık BID, 2023-09-01 → son veri. Alış ASK'tan (BID + spread), satış BID'den.
- Giriş: hafta içi 01–21 UTC, her 30 dakikada bir (dakika % 30 == 0), açık işlem < 10 ise bir işlem; yön yazı-tura.
  Fiyat o dakikanın kapanışı, TP denetimi sonraki dakikadan başlar.
- Boyut: bakiyenin her 1.000 $'ı için `lot` (0,01 lot = 1 ons), en az 0,01 lot. Senaryolar: 0,01 (videodaki "en
  riskli"), 0,02 ("en risklinin riskisi", kanal sahibi "patlamazdı" diyor), 0,05 ve 0,10 (patlatan kullanıcılar).
- Çıkış: yalnız TP: alış BID ≥ giriş + 1,5 $; satış ASK ≤ giriş − 1,5 $ (dolum tam TP fiyatından; bot lehine). Stop yok.
- Hesap: başlangıç 1.000 $, kaldıraç 1:1000, stop-out marjin seviyesi %20: o dakikanın en kötü fiyatıyla (alışlar
  dakikanın dibi, satışlar tepesi + spread; ikisi aynı anda: aleyhte) özkaynak ≤ %20 × marjin olursa bütün işlemler
  kapanır ve hesap biter. Swap yok (bot lehine: zarardaki işlemleri günlerce taşımak gerçekte swap öder).
- Hafta (UTC, Pazartesi başlangıç) "%100": hafta sonunda açık işlem yok ve o hafta stop-out yok (kanalın tanımı).
- Başlangıçlar: 2023-09'dan 2026-03'e her ay başı (31 başlangıç), her biri 26 hafta ya da hesap bitene kadar; tohum =
  başlangıç sırası. Spread 0,35 $ (XM standart hesap civarı) ve 0,70 $ (NCM'de 2026-10-05'te canlı ölçülen 0,65–0,81).

Çıktı: senaryo başına hesabı biten başlangıç oranı, bitene kadar geçen hafta, bitmeden önceki "%100" hafta serisi,
haftalık getiri ortancası, 26 hafta sonu bakiye dağılımı. Kullanım (host): python research/altin/stopsuz.py [--cikti x]
"""
from __future__ import annotations

import argparse
import json
import math
from datetime import UTC, datetime

import numpy as np

from tradebot.ayar import ayarlar
from tradebot.veri.depo import BarDepo

LOTLAR = (0.01, 0.02, 0.05, 0.10)
SPREADLER = (0.35, 0.70)
TP = 1.5
KALDIRAC = 1000.0
STOPOUT = 0.20
AZAMI_ACIK = 10
ARALIK_DK = 30
BAKIYE0 = 1000.0
UFUK_HAFTA = 26
HAFTA_MS = 7 * 86_400_000
PAZARTESI0 = 4 * 86_400_000     # 1970-01-05 Pazartesi: (t - PAZARTESI0) // HAFTA_MS = hafta no


def simule(v: dict, bas: int, bit: int, lot: float, spread: float, tohum: int) -> dict:
    t, h, lo, c, dk, sa, gun, hf = v["t"], v["h"], v["lo"], v["c"], v["dk"], v["sa"], v["gun"], v["hf"]
    rng = np.random.default_rng(tohum)
    yonler = rng.choice([-1, 1], size=bit - bas).tolist()
    bakiye = BAKIYE0
    acik: list[list[float]] = []          # [yön, giriş, ons]
    haftalar: list[dict] = []
    hafta_bas_oz = BAKIYE0
    biten = None
    islem = tp_sayisi = 0
    for i in range(bas, bit):
        hi, dip, cl = h[i], lo[i], c[i]
        if acik:
            kalan = []
            for p in acik:
                y, g, q = p
                if (y > 0 and hi >= g + TP) or (y < 0 and dip + spread <= g - TP):
                    bakiye += q * TP
                    tp_sayisi += 1
                else:
                    kalan.append(p)
            acik = kalan
        if acik:
            yuzen = sum(q * ((dip - g) if y > 0 else (g - hi - spread)) for y, g, q in acik)
            marjin = sum(q for _, _, q in acik) * cl / KALDIRAC
            if bakiye + yuzen <= STOPOUT * marjin:
                bakiye = max(0.0, bakiye + yuzen)
                biten = t[i]
                acik = []
                haftalar.append({"hafta": hf[i], "yuzde100": False, "getiri": bakiye / hafta_bas_oz - 1,
                                 "acik": 0, "bitti": True})
                break
        if dk[i] % ARALIK_DK == 0 and gun[i] < 5 and 1 <= sa[i] < 21 and len(acik) < AZAMI_ACIK:
            ons = max(1.0, math.floor(bakiye / 1000.0)) * lot * 100.0 if bakiye >= 1000 else lot * 100.0
            ons = max(1.0, round(ons))
            y = yonler[i - bas]
            acik.append([y, cl + spread if y > 0 else cl, ons])
            islem += 1
        if i + 1 == bit or hf[i + 1] != hf[i]:
            oz = bakiye + sum(q * ((cl - g) if y > 0 else (g - cl - spread)) for y, g, q in acik)
            haftalar.append({"hafta": hf[i], "yuzde100": not acik, "getiri": oz / hafta_bas_oz - 1,
                             "acik": len(acik), "bitti": False})
            hafta_bas_oz = oz
    son_oz = bakiye + sum(q * ((c[bit - 1] - g) if y > 0 else (g - c[bit - 1] - spread)) for y, g, q in acik) \
        if biten is None else bakiye
    seri = 0
    for w in haftalar:
        if w["bitti"]:
            break
        seri = seri + 1 if w["yuzde100"] else 0
    return {"biten_ms": biten, "hafta": len(haftalar), "yuzde100_hafta": sum(w["yuzde100"] for w in haftalar),
            "bitmeden_once_seri": seri, "son_ozkaynak": round(son_oz, 2), "islem": islem, "tp": tp_sayisi,
            "haftalik_getiri": [round(w["getiri"], 4) for w in haftalar]}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--cikti", default="")
    x = ap.parse_args()
    d = BarDepo(ayarlar().veri_dizini).oku("DUKASCOPY:XAUUSD", "1m").sort("acilis_ms")
    t = d["acilis_ms"].to_numpy().astype(np.int64)
    t0 = int(datetime(2023, 9, 1, tzinfo=UTC).timestamp() * 1000)
    m = t >= t0
    t = t[m]
    v = {"t": t.tolist(), "h": d["high"].to_numpy()[m].tolist(), "lo": d["low"].to_numpy()[m].tolist(),
         "c": d["close"].to_numpy()[m].tolist(), "dk": ((t // 60_000) % 60).tolist(),
         "sa": ((t // 3_600_000) % 24).tolist(), "gun": ((t // 86_400_000 + 3) % 7).tolist(),
         "hf": ((t - PAZARTESI0) // HAFTA_MS).tolist()}
    baslar = []
    for k in range(31):
        yil, ay = 2023 + (8 + k) // 12, (8 + k) % 12 + 1
        ms = int(datetime(yil, ay, 1, tzinfo=UTC).timestamp() * 1000)
        i = int(np.searchsorted(t, ms))
        j = int(np.searchsorted(t, ms + UFUK_HAFTA * HAFTA_MS))
        if j - i > 1000:
            baslar.append((f"{yil}-{ay:02d}", i, j))
    rapor = {"veri": {"bas": datetime.fromtimestamp(t[0] / 1000, UTC).isoformat(),
                      "bit": datetime.fromtimestamp(t[-1] / 1000, UTC).isoformat(), "dakika": len(t)},
             "kural": {"tp": TP, "kaldirac": KALDIRAC, "stopout": STOPOUT, "azami_acik": AZAMI_ACIK,
                       "aralik_dk": ARALIK_DK, "bakiye0": BAKIYE0, "ufuk_hafta": UFUK_HAFTA},
             "senaryolar": {}}
    for s in SPREADLER:
        for lot in LOTLAR:
            sonuc = {ad: simule(v, i, j, lot, s, n) for n, (ad, i, j) in enumerate(baslar)}
            biten = [r for r in sonuc.values() if r["biten_ms"] is not None]
            sag = [r for r in sonuc.values() if r["biten_ms"] is None]
            ozet = {
                "baslangic": len(sonuc), "hesabi_biten": len(biten),
                "bitene_kadar_hafta_ortanca": float(np.median([r["hafta"] for r in biten])) if biten else None,
                "bitmeden_once_yuzde100_seri_ortanca": float(np.median([r["bitmeden_once_seri"] for r in biten]))
                if biten else None,
                "yuzde100_hafta_orani": round(sum(r["yuzde100_hafta"] for r in sonuc.values())
                                              / max(1, sum(r["hafta"] for r in sonuc.values())), 3),
                "haftalik_getiri_ortanca": round(float(np.median([g for r in sonuc.values()
                                                                  for g in r["haftalik_getiri"]])), 4),
                "sag_kalan_son_ozkaynak_ortanca": float(np.median([r["son_ozkaynak"] for r in sag])) if sag else None,
                "tum_son_ozkaynak_ortalama": round(float(np.mean([r["son_ozkaynak"] for r in sonuc.values()])), 2),
            }
            rapor["senaryolar"][f"spread_{s:.2f}_lot_{lot:.2f}"] = {"ozet": ozet, "baslangiclar": sonuc}
            print(f"spread {s:.2f} lot/1000$ {lot:.2f}: {json.dumps(ozet, ensure_ascii=False)}", flush=True)
    if x.cikti:
        open(x.cikti, "w", encoding="utf-8").write(json.dumps(rapor, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
