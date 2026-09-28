"""Dalga 4 koşucusu: ön kayıtlı opsiyon kollarını (yapı × para) koşar, deftere yazar, sonuç dosyası üretir.

Veri: `data/opsiyon/{PARA}_haftalik.parquet` + `{PARA}_teslim.json` (`tradebot veri deribit`). Parametre araması yok:
her kol tek varyanttır (ön kayıt); DSR kol sayısı kadar denemeye göre hesaplanır. Kör dönem (`donem.is_bitis`
sonrası) seçimde kullanılmaz, ayrı raporlanır ve kapıdır.
"""
from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import polars as pl
import yaml

from tradebot.arastirma import opsiyon as op
from tradebot.arastirma.dogrulama import beklenen_max_sr, carpiklik_basiklik, dsr
from tradebot.arastirma.metrik import HAFTA_MS, PAZARTESI_KAYMA_MS

VARSAYILAN_OLCUT = {"dsr_a": 0.95, "yil_pozitif": 0.60, "stres_maliyet": 2.0, "en_kotu_hafta": -0.10,
                    "en_kotu_dusus": -0.30, "oos_asgari_yillik": 0.0}


def _ms(s: str) -> int:
    return int(datetime.fromisoformat(s).replace(tzinfo=UTC).timestamp() * 1000)


def veri_oku(veri_dizini: Path, para: str) -> tuple[list[dict], dict[str, float], str]:
    d = Path(veri_dizini) / "opsiyon"
    y, t = d / f"{para}_haftalik.parquet", d / f"{para}_teslim.json"
    h = hashlib.sha256(y.read_bytes() + t.read_bytes()).hexdigest()
    return pl.read_parquet(y).to_dicts(), json.loads(t.read_text(encoding="utf-8")), h


def karar(tam: dict, oos: dict, stres: dict, d: float, o: dict) -> str:
    temel = (tam.get("yil_pozitif_orani", 0) >= o["yil_pozitif"] and tam.get("en_kotu_hafta", -1) >= o["en_kotu_hafta"]
             and tam.get("en_kotu_dusus", -1) >= o["en_kotu_dusus"] and stres.get("yillik_bilesik", -1) > 0
             and oos.get("yillik_bilesik", -1) > o["oos_asgari_yillik"] and oos.get("en_kotu_dusus", -1) >= o["en_kotu_dusus"])
    if not temel:
        return "KALDI"
    return "A" if d >= o["dsr_a"] else "B"


def haftalik_korelasyon(sonuclar: list[op.HaftaSonucu], trend: dict | None) -> float | None:
    """Trend kolunun (turnuva sonuç dosyası `haftalik.tam`) haftalık log getirisiyle korelasyon."""
    if not trend:
        return None
    t = dict(zip(trend["hafta"], trend["log"], strict=True))
    a, b = [], []
    for s in sonuclar:
        h = (s.giris_ms - PAZARTESI_KAYMA_MS) // HAFTA_MS
        if h in t:
            a.append(np.log1p(s.getiri))
            b.append(t[h])
    return float(np.corrcoef(a, b)[0, 1]) if len(a) > 20 else None


def kos(dosya: Path, veri_dizini: Path, defter=None, trend_dosyasi: Path | None = None) -> list[dict]:
    d = yaml.safe_load(Path(dosya).read_text(encoding="utf-8"))
    o = VARSAYILAN_OLCUT | (d.get("olcut") or {})
    m = op.Maliyet(**(d.get("maliyet") or {}))
    bas, is_bit, bit = _ms(d["donem"]["bas"]), _ms(d["donem"]["is_bitis"]), _ms(d["donem"]["bit"])
    plan = d["plan"]
    if defter is not None:
        try:
            defter.plan_ac(plan["kimlik"], plan["aile"], " ".join(plan["hipotez"].split()), {"dosya": str(dosya)},
                           [f"DERIBIT:{p}" for p in d["paralar"]], f"{dosya} → olcut {o}")
        except ValueError:
            pass   # plan açık: aynı ön kayıtla devam
    trend = None
    if trend_dosyasi is not None and Path(trend_dosyasi).exists():
        trend = json.loads(Path(trend_dosyasi).read_text(encoding="utf-8"))["haftalik"]["tam"]
    kollar = []
    for para in d["paralar"]:
        yuzey, teslim, vh = veri_oku(veri_dizini, para)
        yuzey = [y for y in yuzey if bas <= y["giris_ms"] < bit]
        for yapi in d["yapilar"]:
            t0 = time.perf_counter()
            s = op.kos(yuzey, teslim, yapi, d["risk"], m)
            s_stres = op.kos(yuzey, teslim, yapi, d["risk"], m.kat(o["stres_maliyet"]))
            kollar.append({"para": para, "yapi": yapi, "veri_hash": vh, "sonuc": s,
                           "tam": op.ozet(s), "is": op.ozet([x for x in s if x.giris_ms < is_bit]),
                           "oos": op.ozet([x for x in s if x.giris_ms >= is_bit]), "stres": op.ozet(s_stres),
                           "sure": time.perf_counter() - t0})
    sr = [k["tam"].get("sr_haftalik", 0.0) for k in kollar]
    v = float(np.var(sr, ddof=1)) if len(sr) > 1 else 0.0
    out = []
    for k in kollar:
        r = np.array([x.getiri for x in k["sonuc"]])
        g3, g4 = carpiklik_basiklik(r)
        dd = dsr(k["tam"]["sr_haftalik"], len(r), len(kollar), v, g3, g4)
        kr = karar(k["tam"], k["oos"], k["stres"], dd, o)
        kol = f"{k['yapi']}@DERIBIT:{k['para']}@1w"
        sonuc = {"plan": plan["kimlik"], "kol": kol, "karar": kr, "risk": d["risk"],
                 "en_iyi": {"varyant": k["yapi"], "sharpe": k["tam"]["sharpe"], "yillik_bilesik": k["tam"]["yillik_bilesik"]},
                 "dsr": {"dsr": dd, "deneme": len(kollar), "sr_esik": beklenen_max_sr(len(kollar), v),
                         "carpiklik": g3, "basiklik": g4},
                 "tam": k["tam"], "orneklem_ici": k["is"], "kor": k["oos"], "stres_2x": k["stres"],
                 "trend_korelasyonu": haftalik_korelasyon(k["sonuc"], trend), "veri_hash": k["veri_hash"]}
        if defter is not None:
            defter.kaydet(plan["kimlik"], "tarama", k["yapi"], plan["aile"], {"yapi": k["yapi"], "risk": d["risk"]},
                          f"DERIBIT:{k['para']}", "1w", k["veri_hash"], {kk: vv for kk, vv in sonuc.items()
                                                                         if kk in ("karar", "dsr", "tam", "kor")},
                          k["sure"])
        dizin = Path(veri_dizini) / "turnuva" / f"dalga{d['dalga']}"
        dizin.mkdir(parents=True, exist_ok=True)
        (dizin / f"{k['yapi']}__DERIBIT_{k['para']}__1w.json").write_text(json.dumps(sonuc, ensure_ascii=False, indent=1),
                                                                          encoding="utf-8")
        out.append(sonuc)
    return out
