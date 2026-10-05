"""Olay tabanlı piyasa nötr perp dalgaları (6: kilit açılımı, 7: yeni listeleme, 12: spot delist) — veri hazırlığı ve
koşucu: olaylar +
perp verisi → ön kayıtlı ızgara → defter, sonuç dosyası. Olay kaynağı ön kayıttaki `kaynak` (varsayılan `kilit`)."""
from __future__ import annotations

import hashlib
import json
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import polars as pl
import yaml

from tradebot.arastirma import delist, listeleme
from tradebot.arastirma import kilit as kl
from tradebot.arastirma.dogrulama import beklenen_max_sr, carpiklik_basiklik, dsr, izgara
from tradebot.veri import binance_vadeli as bv
from tradebot.veri import kilit as vk

YIL_HAFTA = 52.1775


def hazirla(veri_dizini: Path, ham, http_al, kayitci=None) -> dict:
    """Takvim sayfası → olaylar; olaylı ve perp'i olan her sembolün günlük mumu ve funding'i (+ BTCUSDT)."""
    d = Path(veri_dizini) / "kilit"
    (d / "perp").mkdir(parents=True, exist_ok=True)
    tablo = vk.coz(vk.indir(ham, http_al))
    tablo.write_parquet(d / "olaylar.parquet")
    perp = bv.usdt_perpler(http_al, ham)
    semboller = sorted(set(tablo["sembol"].to_list()) & set(perp)) + ["BTC"]
    hatali = []
    for i, s in enumerate(semboller):
        k = perp[s]["sembol"]
        if (d / "perp" / f"{s}_funding.parquet").exists():   # kaldığı yerden devam
            continue
        try:
            bv.gunluk(http_al, ham, k).write_parquet(d / "perp" / f"{s}_1d.parquet")
            bv.funding(http_al, ham, k).write_parquet(d / "perp" / f"{s}_funding.parquet")
        except Exception as e:  # noqa: BLE001 — henüz işlem görmeyen / kaldırılmış kontrat (400): atla
            hatali.append({"sembol": s, "hata": f"{type(e).__name__}: {e}"[:120]})
        if kayitci is not None and i % 20 == 0:
            kayitci.info("ilerleme", bitti=i + 1, toplam=len(semboller))
    (d / "perp_listesi.json").write_text(json.dumps({s: perp[s] for s in semboller}, ensure_ascii=False), encoding="utf-8")
    return {"olay": tablo.height, "token": tablo["sembol"].n_unique(), "perp_eslesen": len(semboller) - 1,
            "hatali": hatali}


def _ms(s: str) -> int:
    return int(datetime.fromisoformat(s).replace(tzinfo=UTC).timestamp() * 1000)


def _ozet(h: np.ndarray) -> dict:
    if len(h) < 10:
        return {"hafta": int(len(h))}
    oz = np.cumprod(1 + h)
    tepe = np.maximum.accumulate(np.r_[1.0, oz])[1:]
    sd = h.std(ddof=1)
    return {"hafta": int(len(h)), "yillik_bilesik": float(oz[-1] ** (YIL_HAFTA / len(h)) - 1),
            "sharpe": float(h.mean() / sd * np.sqrt(YIL_HAFTA)) if sd > 0 else 0.0,
            "sr_haftalik": float(h.mean() / sd) if sd > 0 else 0.0, "en_kotu_hafta": float(h.min()),
            "en_kotu_dusus": float((oz / tepe - 1).min())}


def kos(dosya: Path, veri_dizini: Path, defter=None) -> list[dict]:
    d = yaml.safe_load(Path(dosya).read_text(encoding="utf-8"))
    o = d["olcut"]
    kaynak = d.get("kaynak", "kilit")
    kd = Path(veri_dizini) / kaynak
    barlar, fundingler = {}, {}
    for y in (kd / "perp").glob("*_1d.parquet"):
        s = y.name[: -len("_1d.parquet")]
        barlar[s] = pl.read_parquet(y)
        f = kd / "perp" / f"{s}_funding.parquet"
        fundingler[s] = pl.read_parquet(f) if f.exists() else pl.DataFrame()
    btc, btc_f = barlar.pop("BTC"), fundingler.pop("BTC", pl.DataFrame())
    if kaynak == "kilit":
        tablo = pl.read_parquet(kd / "olaylar.parquet")
        ev_sabit = kl.olaylar(tablo, d["olay"]["kategoriler"], d["olay"]["asgari_oran"])
        vh = hashlib.sha256((kd / "olaylar.parquet").read_bytes()).hexdigest()
    elif kaynak == "delist":
        spot = pl.read_parquet(kd / "spot_delist.parquet")
        kap = pl.read_parquet(kd / "perp_kapanis.parquet")
        jev = pl.read_parquet(kd / "jev.parquet")
        barlar = {s: delist.kirp(b, kap.filter(pl.col("sembol") == s)["yayin_ms"].to_list()) for s, b in barlar.items()}
        vh = hashlib.sha256(b"".join((kd / f).read_bytes() for f in
                                     ("spot_delist.parquet", "perp_kapanis.parquet", "jev.parquet"))).hexdigest()
    else:   # listeleme: olay günü ızgara noktasına bağlı (çıkış günü = listeleme + bitis_gun)
        perpler = json.loads((kd / "perp_listesi.json").read_text(encoding="utf-8"))
        ilk_mum = {s: int(b["acilis_ms"].min()) for s, b in barlar.items() if b.height}
        vh = hashlib.sha256((kd / "perp_listesi.json").read_bytes()).hexdigest()
    bas, is_bit, bit = _ms(d["donem"]["bas"]), _ms(d["donem"]["is_bitis"]), _ms(d["donem"]["bit"])
    plan_ac(d, dosya, defter, ["BINANCEF:perp"])
    kollar = []
    tavan = d.get("tavan") or {}
    for p in izgara(d["izgara"]):
        t0 = time.perf_counter()
        if kaynak == "kilit":
            ev, giris, cikis = ev_sabit, p["giris"], p["cikis"]
            ad, dosya_adi = f"kilit(giris={giris},cikis={cikis})", f"kilit_g{giris}_c{cikis}"
            if "asgari_oran" in p:   # dalga 13: açılım eşiği ızgarada
                ev = kl.olaylar(tablo, d["olay"]["kategoriler"], float(p["asgari_oran"]))
                ad = f"kilit(giris={giris},cikis={cikis},oran={p['asgari_oran']})"
                dosya_adi += f"_o{p['asgari_oran']}"
        elif kaynak == "delist":   # olay günü = giriş günü (duyurudan sonraki ilk açılış)
            ev, giris, cikis = delist.olaylar(spot, jev if p["jev"] else None), 0, p["cikis"]
            ad = f"delist(cikis={cikis},jev={int(p['jev'])})"
            dosya_adi = f"delist_c{cikis}_j{int(p['jev'])}"
        else:
            ev = listeleme.olaylar(perpler, ilk_mum, p["giris_gun"], p["bitis_gun"], _ms(d["donem"]["bas"]))
            giris, cikis = -(p["bitis_gun"] - p["giris_gun"]), 0
            zk = f",zarar_kes={p['zarar_kes']}" if "zarar_kes" in p else ""
            ad = f"listeleme(giris={p['giris_gun']},bitis={p['bitis_gun']}{zk})"
            dosya_adi = f"listeleme_g{p['giris_gun']}_b{p['bitis_gun']}" + (f"_z{p['zarar_kes']}" if zk else "")
        zk_ = {"zarar_kes": p["zarar_kes"]} if "zarar_kes" in p else {}
        a = kl.KilitAyar(giris=giris, cikis=cikis, **(d.get("maliyet") or {}), notional=d["notional"], **tavan, **zk_)
        a2 = kl.KilitAyar(giris=giris, cikis=cikis, notional=d["notional"], **tavan, **zk_,
                          **{k: v * o["stres_maliyet"] for k, v in (d.get("maliyet") or {}).items()})
        seri, olay = kl.kos(ev, barlar, fundingler, btc, btc_f, a, bas, bit)
        seri2, _ = kl.kos(ev, barlar, fundingler, btc, btc_f, a2, bas, bit)
        h = kl.haftalik(seri, bas, bit)
        from tradebot.arastirma.metrik import HAFTA_MS, PAZARTESI_KAYMA_MS
        ks = int((is_bit - PAZARTESI_KAYMA_MS) // HAFTA_MS - (bas - PAZARTESI_KAYMA_MS) // HAFTA_MS)
        kurulan = olay.filter(pl.col("kurulmadi").is_null())
        yillar = {}
        for y0 in range(datetime.fromtimestamp(bas / 1000, UTC).year, datetime.fromtimestamp(bit / 1000, UTC).year + 1):
            s = seri.filter(pl.col("gun_ms").is_between(_ms(f"{y0}-01-01"), _ms(f"{y0 + 1}-01-01") - 1))["getiri"]
            yillar[y0] = float(np.prod(1 + s.to_numpy()) - 1) if len(s) else 0.0
        kollar.append({"p": p, "h": h, "tam": _ozet(h), "is": _ozet(h[:ks]), "kor": _ozet(h[ks:]),
                       "stres": _ozet(kl.haftalik(seri2, bas, bit)), "yillik": yillar,
                       "olay": {"toplam": olay.height, "kurulan": kurulan.height,
                                "kurulmadi": olay.filter(pl.col("kurulmadi").is_not_null())
                                .group_by("kurulmadi").len().to_dicts(),
                                "birim_ort": float(kurulan["getiri"].mean()) if kurulan.height else None,
                                "birim_medyan": float(kurulan["getiri"].median()) if kurulan.height else None,
                                "isabet": float((kurulan["getiri"] > 0).mean()) if kurulan.height else None,
                                "birim_t": float(kurulan["getiri"].mean() / (kurulan["getiri"].std() / np.sqrt(kurulan.height)))
                                if kurulan.height > 2 else None},
                       "sure": time.perf_counter() - t0, "ad": ad, "dosya": dosya_adi})
    return degerlendir(kollar, d, veri_dizini, defter, f"BINANCEF:{kaynak}", "1d", vh)


def plan_ac(d: dict, dosya: Path, defter, piyasalar: list[str]) -> None:
    """Ön kayıttaki planı deftere açar (zaten açıksa sürer: kesilen koşu yeniden başlatılabilir)."""
    if defter is not None:
        try:
            defter.plan_ac(d["plan"]["kimlik"], d["plan"]["aile"], " ".join(d["plan"]["hipotez"].split()), d["izgara"],
                           piyasalar, f"{dosya} → olcut {d['olcut']}")
        except ValueError:
            pass


def degerlendir(kollar: list[dict], d: dict, veri_dizini: Path, defter, piyasa: str, zd: str, vh: str) -> list[dict]:
    """Ön kayıtlı ölçütle karar (A/B/KALDI), DSR (önceki dalgalar dahil), defter ve `data/turnuva/dalga<N>/` yazımı.

    `kollar` öğeleri: p, h (haftalık getiri), tam, is, kor, stres, yillik, olay, sure, ad, dosya."""
    o, plan, bas = d["olcut"], d["plan"], _ms(d["donem"]["bas"])
    sr = [k["tam"].get("sr_haftalik", 0.0) for k in kollar]
    # Aynı ailenin önceki dalgaları (ör. 6b → 6): DSR bütün denemelerle sayılır (kural 10)
    for onceki in d.get("onceki_dalgalar") or []:
        for f in sorted((Path(veri_dizini) / "turnuva" / onceki).glob("*.json")):
            sr.append(json.loads(f.read_text(encoding="utf-8"))["tam"].get("sr_haftalik", 0.0))
    deneme_sayisi = len(sr)
    v = float(np.var(sr, ddof=1)) if len(sr) > 1 else 0.0
    out = []
    for k in kollar:
        g3, g4 = carpiklik_basiklik(k["h"])
        dd = dsr(k["tam"].get("sr_haftalik", 0.0), len(k["h"]), deneme_sayisi, v, g3, g4)
        yp = float(np.mean([x > 0 for x in k["yillik"].values()]))
        temel = (yp >= o["yil_pozitif"] and k["tam"].get("en_kotu_hafta", -1) >= o["en_kotu_hafta"]
                 and k["tam"].get("en_kotu_dusus", -1) >= o["en_kotu_dusus"] and k["stres"].get("yillik_bilesik", -1) > 0
                 and k["kor"].get("yillik_bilesik", -1) > o["oos_asgari_yillik"]
                 and k["kor"].get("en_kotu_dusus", -1) >= o["en_kotu_dusus"])
        kr = "KALDI" if not temel else ("A" if dd >= o["dsr_a"] else "B")
        ad = k["ad"]
        sonuc = {"plan": plan["kimlik"], "kol": f"{ad}@{piyasa}@{zd}", "karar": kr,
                 "en_iyi": {"varyant": ad, "sharpe": k["tam"].get("sharpe"), "yillik_bilesik": k["tam"].get("yillik_bilesik")},
                 "dsr": {"dsr": dd, "deneme": deneme_sayisi, "sr_esik": beklenen_max_sr(deneme_sayisi, v)},
                 "tam": k["tam"], "orneklem_ici": k["is"], "kor": k["kor"], "stres_2x": k["stres"], "yillik": k["yillik"],
                 "yil_pozitif_orani": yp, "olay": k["olay"], "veri_hash": vh,
                 "haftalik": {"bas_ms": bas, "getiri": [float(x) for x in k["h"]]}}
        if defter is not None:
            defter.kaydet(plan["kimlik"], "tarama", plan["aile"], plan["aile"], k["p"], piyasa, zd, vh,
                          {x: sonuc[x] for x in ("karar", "dsr", "tam", "kor", "olay")}, k["sure"])
        dz = Path(veri_dizini) / "turnuva" / f"dalga{d['dalga']}"
        dz.mkdir(parents=True, exist_ok=True)
        (dz / f"{k['dosya']}.json").write_text(json.dumps(sonuc, ensure_ascii=False, indent=1),
                                                                            encoding="utf-8")
        out.append(sonuc)
    return out
