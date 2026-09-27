"""C2 ölçümü (Faz 6): FOMC karar metninin tonu (Jev) özellik olarak değer katıyor mu?

Jev metni yargılar (kural 8: yalnız metin yargısı), tonun getiriyle ilişkisini kod ölçer. Spike: research/spikes/06_c2
(4/4 beklenen ton ve karar).

- Metinler: federalreserve.gov yıllık arşiv (2006–2020) + güncel takvim (2021→); ham HTML ham depoya (kural 9).
- State yalnız açıklama metni, TARİH YOK (model metni tanıyıp piyasa tepkisini hatırlamasın). Yine de örneklemin
  tamamı modelin eğitim kesiminden önce olabilir: SIZINTI RİSKİ işaretli.
- Yargılar `jev_yargi`'ya dondurulur; yeniden koşuda donmuş cevap okunur (çağrı yok).
- Özellik: Δton = ton − önceki kararın tonu (sürprizin yaklaşık ölçüsü).
- Ön kayıtlı testler (Spearman, t = r·√((n−2)/(1−r²))):
  1. Doğrulama: Δton ↔ TLT aynı gün getirisi, beklenen negatif, t ≤ −2 → "Jev tonu anlamlı".
  2. İşlem yapılabilirlik: Δton ↔ sonraki 5 işlem günü (TLT, SPY, GLD) ve BTC (+3 sa → +5 gün); 4 test için |t| ≥ 2,5
     → "özellik adayı", yoksa "özelliğe girmez".
Koşu: host'ta paper konteynerinde. Çıktı: data/olcum/c2_fomc_ton.json.
"""
from __future__ import annotations

import html
import json
import math
import re
import time
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from typesafe_sdk import Choice, Score

from tradebot.arastirma.defter import Defter
from tradebot.ayar import ayarlar
from tradebot.db import motor
from tradebot.veri.depo import BarDepo, HamDepo
from tradebot.veri.takvim import ms
from tradebot.zeka.jev import JevIstemci, donmus

PLAN = "2026-09-27-c2-fomc-ton"
FED = "https://www.federalreserve.gov"
HIPOTEZ = ("FOMC karar metninin Jev ile yargılanan tonundaki değişim (Δton), aynı gün tahvil getirisiyle ters ilişkilidir "
           "(Jev tonu anlamlı) ve sonraki 5 günde TLT/SPY/GLD/BTC getirisini açıklar (özellik adayı).")
OLCUT = ("Doğrulama: Spearman t(Δton, TLT aynı gün) ≤ −2. Özellik adayı: 4 sonraki-5-gün testinden en az birinde |t| ≥ 2,5; "
         "yoksa özelliğe girmez. Örneklem modelin eğitim kesiminden önce olabilir: sızıntı riski işaretli.")

TON = Score(
    instructions={"what": "How hawkish or dovish is the monetary policy stance that the FOMC statement in `aciklama.metin` "
                          "expresses, taking into account both the policy action it announces and the guidance it gives "
                          "about future policy?",
                  "not_for": "Do not use knowledge of how markets reacted or what happened later. Judge only the text."},
    criteria=[
        "Strongly dovish: the Committee cuts the policy rate or launches or expands asset purchases or other major "
        "accommodation, and/or signals that further easing is likely.",
        "Mildly dovish: the Committee holds policy but leans toward easing, stresses downside risks to growth or "
        "employment, or signals patience before any tightening.",
        "Neutral: the Committee holds policy with balanced risks and gives no clear lean toward tightening or easing.",
        "Mildly hawkish: the Committee holds policy or tapers accommodation but leans toward tightening, stresses "
        "inflation concerns, or signals that increases are approaching.",
        "Strongly hawkish: the Committee raises the policy rate or shrinks its balance sheet, and/or signals that further "
        "increases are likely."])
KARAR = Choice(
    instructions="What does the FOMC statement in `aciklama.metin` announce about the target range (or target level) for "
                 "the federal funds rate at this meeting?",
    criteria={"artis": "The Committee raises the federal funds rate target.",
              "sabit": "The Committee keeps the federal funds rate target unchanged.",
              "indirim": "The Committee lowers the federal funds rate target."})
SORULAR = {"ton": TON, "karar": KARAR}


def al(url: str) -> bytes:
    time.sleep(1.0)
    return urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30).read()


def govde(h: str) -> str:
    m = re.search(r'id="article"(.*?)(<div[^>]*id="lastUpdate"|<footer)', h, re.S)
    g = m.group(1) if m else h
    g = re.sub(r"<(script|style)[^>]*>.*?</\1>", " ", g, flags=re.S)
    g = re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", g))).strip()
    return re.sub(r"^.*?(Share|Release Date:[^.]*?(a\.m\.|p\.m\.) EDT|EST)", "", g, count=1)[:6000]


def adresler() -> dict[str, str]:
    """{YYYYMMDD: karar metni adresi}."""
    out: dict[str, str] = {}
    for y in range(2006, 2021):
        s = al(f"{FED}/monetarypolicy/fomchistorical{y}.htm").decode("utf-8", "ignore")
        for u in re.findall(r'href="([^"]+)"\s*>\s*Statement\s*<', s):
            m = re.search(r"(\d{8})a\.htm", u)
            if m:
                out[m.group(1)] = FED + u
    s = al(f"{FED}/monetarypolicy/fomccalendars.htm").decode("utf-8", "ignore")
    for d in re.findall(r"/newsevents/pressreleases/monetary(\d{8})a\.htm", s):
        out.setdefault(d, f"{FED}/newsevents/pressreleases/monetary{d}a.htm")
    return dict(sorted(out.items()))


def spearman(x: np.ndarray, y: np.ndarray) -> dict:
    ok = np.isfinite(x) & np.isfinite(y)
    x, y = x[ok], y[ok]
    n = len(x)
    if n < 10:
        return {"n": n, "r": None, "t": None}
    rx, ry = np.argsort(np.argsort(x)), np.argsort(np.argsort(y))
    r = float(np.corrcoef(rx, ry)[0, 1])
    return {"n": n, "r": r, "t": r * math.sqrt((n - 2) / max(1e-12, 1 - r * r))}


def main() -> None:
    a = ayarlar()
    m = motor(a)
    Defter(m).plan_ac(PLAN, "olcum_c2", HIPOTEZ, {"varlik": ["TLT", "SPY", "GLD", "BTC"], "ufuk": ["ayni_gun", "5g"]},
                      ["FOMC"], OLCUT)
    t0 = time.monotonic()
    ham = HamDepo(a.veri_dizini, m)
    jev = JevIstemci(m, "jev-1.13.0", api_key=a.typesafe_api_key.get_secret_value())
    kayit = []
    for tarih, url in adresler().items():
        icerik = al(url)
        _, sha, _ = ham.kaydet("fed", f"fomc/{tarih}", icerik, "html")
        state = {"aciklama": {"metin": govde(icerik.decode("utf-8", "ignore"))}}
        cevap = donmus(m, SORULAR, state)
        if cevap is None:
            y = jev.sor("C2_fomc", f"FOMC:{tarih}", state, SORULAR)
            cevap = y.cevap if not y.hata else None
        if not cevap:
            continue
        kayit.append({"tarih": tarih, "ham_sha": sha, "ton": cevap["ton"]["score"], "ton_guven": cevap["ton"]["confidence"],
                      "karar": cevap["karar"]["choice"], "karar_guven": cevap["karar"]["confidence"]})

    d = BarDepo(a.veri_dizini)
    seri = {k: d.oku(f"ARCA:{k}", "1d") for k in ("TLT", "SPY", "GLD")}
    btc = d.oku("BINANCE:BTCUSDT", "1h")
    bt, bo = btc["acilis_ms"].to_numpy(), btc["open"].to_numpy()
    for i, r in enumerate(kayit):
        r["dton"] = r["ton"] - kayit[i - 1]["ton"] if i else None
        gun = ms(datetime.strptime(r["tarih"], "%Y%m%d").replace(tzinfo=UTC))
        for k, df in seri.items():
            t, c = df["acilis_ms"].to_numpy(), df["close"].to_numpy()
            j = int(np.searchsorted(t, gun))
            ok = 0 < j < len(t) - 5 and t[j] == gun
            r[f"{k}_ayni"] = float(c[j] / c[j - 1] - 1) if ok else None
            r[f"{k}_5g"] = float(c[j + 5] / c[j] - 1) if ok else None
        karar_ms = gun + 19 * 3_600_000  # 14:00/14:15 ET ≈ 18:00–19:15 UTC; +3 sa sonrası
        j = int(np.searchsorted(bt, karar_ms + 2 * 3_600_000))
        k = int(np.searchsorted(bt, karar_ms + 2 * 3_600_000 + 5 * 86_400_000))
        r["BTC_5g"] = float(bo[k] / bo[j] - 1) if 0 < j and k < len(bt) and bt[0] < karar_ms else None

    x = np.array([r["dton"] if r["dton"] is not None else np.nan for r in kayit], dtype=float)
    col = lambda ad: np.array([r.get(ad) if r.get(ad) is not None else np.nan for r in kayit], dtype=float)  # noqa: E731
    testler = {"dogrulama_TLT_ayni_gun": spearman(x, col("TLT_ayni")), "SPY_ayni_gun": spearman(x, col("SPY_ayni"))}
    for ad in ("TLT_5g", "SPY_5g", "GLD_5g", "BTC_5g"):
        testler[ad] = spearman(x, col(ad))
    dogr = testler["dogrulama_TLT_ayni_gun"]["t"]
    aday = [ad for ad in ("TLT_5g", "SPY_5g", "GLD_5g", "BTC_5g") if testler[ad]["t"] is not None and abs(testler[ad]["t"]) >= 2.5]
    ozet = {"n_karar": len(kayit), "ton_dagilim": np.histogram([r["ton"] for r in kayit], bins=[0, 0.5, 1.5, 2.5, 3.5, 4.01])[0].tolist(),
            "karar_dagilim": {c: sum(1 for r in kayit if r["karar"] == c) for c in ("artis", "sabit", "indirim")},
            "testler": testler, "jev_tonu_anlamli": dogr is not None and dogr <= -2,
            "ozellik_adayi": aday, "karar": "ÖZELLİK ADAYI" if aday else "ÖZELLİĞE GİRMEZ", "sizinti_riski": True}
    sonuc = {"plan": PLAN, "ozet": ozet, "kayit": kayit, "sure_sn": round(time.monotonic() - t0, 1)}
    cikti = Path(a.veri_dizini) / "olcum" / "c2_fomc_ton.json"
    cikti.parent.mkdir(parents=True, exist_ok=True)
    cikti.write_text(json.dumps(sonuc, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    Defter(m).kaydet(PLAN, "olcum", "fomc_ton", "olcum_c2", {"soru": "ton+karar", "model": "jev-1.13.0"}, "FOMC", "olay",
                     "fed+bar", ozet, sonuc["sure_sn"])
    print(json.dumps(ozet, ensure_ascii=False, indent=1, default=str))


if __name__ == "__main__":
    main()
