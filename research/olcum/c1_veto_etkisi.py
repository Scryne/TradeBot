"""C1 ölçümü (Faz 6): Jev vetolarının koruma değeri — olay çalışması.

Soru: veto verilen enstrümanı tutan biri, veto olmasaydı ne kaybederdi? Her veto için giriş = `gecerli_ms`'den sonraki
ilk barın açılışı (motorun göreceği an). Getiri ufukları 1, 7, 30 takvim günü; anormal getiri = enstrüman − kıyas.
Kıyas: A1 (Binance, 1h) BTCUSDT; A2 (BIST, 1d) aynı penceredeki BIST kesitinin medyanı. Seri ufuktan önce biterse
(delist) son kapanış kullanılır ve `seri_bitti` işaretlenir. Sızıntı kontrolü: duyurudan önceki 7 gün.
Onaylı `kaldir` olayıyla kapatılan (yanlış) vetolar çıkarılır.

Ön kayıt (plan koşudan önce deneme defterine yazılır; kural 10). Koşu: host'ta paper konteynerinde
`python research/olcum/c1_veto_etkisi.py`. Çıktı: data/olcum/c1_veto_etkisi.json.
"""
from __future__ import annotations

import json
import time
from pathlib import Path

import numpy as np
from sqlalchemy import text

from tradebot.arastirma.defter import Defter
from tradebot.ayar import ayarlar
from tradebot.db import motor
from tradebot.veri import enstruman as en
from tradebot.veri.depo import BarDepo

PLAN = "2026-09-27-c1-veto-etkisi"
UFUK_GUN = (1, 7, 30)
GUN = 86_400_000
HIPOTEZ = ("Jev vetosu (A1 Binance delist/dönüşüm/USDT çifti kaldırma; A2 KAP olumsuz esaslı/pazar tedbiri) verilen "
           "enstrüman, kıyasa göre 7 günde medyan −%5'ten fazla kaybeder: vetonun koruma değeri. Sızıntı yok: "
           "duyurudan önceki 7 günde medyan anormal getiri |x| < %2.")
OLCUT = ("Rol başına: 7 gün anormal getiri medyanı < −0,05 ise koruma değeri VAR; −0,05…0 ZAYIF; ≥ 0 YOK. "
         "Ön-duyuru 7 gün medyanı |x| ≥ 0,02 ise SIZINTI işaretlenir. A2 KAP geçmişi tamamlanmadan kısmi (işaretli).")


def getiri(t: np.ndarray, c: np.ndarray, o: np.ndarray, bas_ms: int, bit_ms: int) -> tuple[float | None, bool]:
    """bas_ms'den sonraki ilk barın açılışından, bit_ms'den önce açılan son barın kapanışına."""
    i = int(np.searchsorted(t, bas_ms))
    if i >= len(t):
        return None, True
    j = int(np.searchsorted(t, bit_ms)) - 1
    if j < i:
        return None, False
    return float(c[j] / o[i] - 1), j == len(t) - 1 and t[j] < bit_ms - GUN


def main() -> None:
    a = ayarlar()
    m = motor(a)
    Defter(m).plan_ac(PLAN, "olcum_c1", HIPOTEZ, {"ufuk_gun": list(UFUK_GUN)}, ["BINANCE:*USDT", "BIST:*"], OLCUT)
    t0 = time.monotonic()
    d = BarDepo(a.veri_dizini)
    with m.connect() as b:
        kaldirilan = {int(r.ayrinti["veto_id"]) for r in b.execute(text("select ayrinti from olay where tur='kaldir'"))}
        vetolar = [r for r in b.execute(text("select id, rol, enstruman, gecerli_ms, ayrinti from olay where tur='veto'"))
                   if r.id not in kaldirilan]
    seri: dict[str, tuple] = {}

    def yukle(kim: str, zd: str):
        if (kim, zd) not in seri:
            df = d.oku(kim, zd)
            seri[(kim, zd)] = (df["acilis_ms"].to_numpy(), df["open"].to_numpy(), df["close"].to_numpy()) if len(df) else None
        return seri[(kim, zd)]

    bist = [k["kimlik"] for k in en.hepsi(m) if k["piyasa"] == "BIST" and k["sinif"] == "hisse"]

    def bist_kesit(bas: int, bit: int) -> float | None:
        r = []
        for k in bist:
            s = yukle(k, "1d")
            if s is not None:
                x, _ = getiri(s[0], s[2], s[1], bas, bit)
                if x is not None:
                    r.append(x)
        return float(np.median(r)) if len(r) >= 30 else None

    satir = []
    for v in vetolar:
        a1 = v.rol.startswith("A1")
        zd = "1h" if a1 else "1d"
        s = yukle(v.enstruman, zd)
        if s is None:
            continue
        t, o, c = s
        giris = int(t[int(np.searchsorted(t, v.gecerli_ms))]) if np.searchsorted(t, v.gecerli_ms) < len(t) else None
        if giris is None:
            continue
        r = {"id": v.id, "rol": v.rol, "enstruman": v.enstruman, "etiket": (v.ayrinti or {}).get("jev"), "giris_ms": giris}
        pencereler = [("once7", giris - 7 * GUN, giris)] + [(f"g{h}", giris, giris + h * GUN) for h in UFUK_GUN]
        for ad, bas, bit in pencereler:
            x, bitti = getiri(t, c, o, bas, bit)
            if a1:
                bt = yukle("BINANCE:BTCUSDT", "1h")
                k, _ = getiri(bt[0], bt[2], bt[1], bas, bit)
            else:
                k = bist_kesit(bas, bit)
            r[ad] = None if x is None or k is None else x - k
            r[ad + "_ham"] = x
            if ad != "once7":
                r[ad + "_seri_bitti"] = bitti
        satir.append(r)

    ozet = {}
    for rol in sorted({r["rol"] for r in satir}):
        rs = [r for r in satir if r["rol"] == rol]
        o = {"n": len(rs)}
        for ad in ["once7"] + [f"g{h}" for h in UFUK_GUN]:
            x = np.array([r[ad] for r in rs if r[ad] is not None])
            o[ad] = {"n": len(x), "medyan": float(np.median(x)) if len(x) else None,
                     "ortalama": float(x.mean()) if len(x) else None, "negatif_oran": float((x < 0).mean()) if len(x) else None}
        g7, on = o["g7"]["medyan"], o["once7"]["medyan"]
        o["karar"] = None if g7 is None else ("VAR" if g7 < -0.05 else "ZAYIF" if g7 < 0 else "YOK")
        o["sizinti"] = None if on is None else abs(on) >= 0.02
        o["etiket"] = {e: sum(1 for r in rs if r["etiket"] == e) for e in {r["etiket"] for r in rs}}
        ozet[rol] = o
    sonuc = {"plan": PLAN, "ozet": ozet, "satir": satir, "sure_sn": round(time.monotonic() - t0, 1)}
    cikti = Path(a.veri_dizini) / "olcum" / "c1_veto_etkisi.json"
    cikti.parent.mkdir(parents=True, exist_ok=True)
    cikti.write_text(json.dumps(sonuc, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    Defter(m).kaydet(PLAN, "olcum", "veto_etkisi", "olcum_c1", {"ufuk_gun": list(UFUK_GUN)}, "coklu", "1h/1d",
                     "olay+bar", {k: {kk: vv for kk, vv in v.items() if kk != "etiket"} for k, v in ozet.items()},
                     sonuc["sure_sn"])
    print(json.dumps(ozet, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
