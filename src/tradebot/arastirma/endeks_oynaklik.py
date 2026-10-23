"""Dalga 23: tek endeksin (QQQ) oynaklık zamanlaması, uzun veri (docs/turnuva/Dalga-23-QQQ-Oynaklik.md).

Ağırlık saf ve nedenseldir (`agirlik`: yalnız ≤ t kapanışları). Yürütme `backtest.calistir` (kapanışta karar, sonraki
açılışta dolum, taraf başı maliyet). Motorun finansmanı bütün pozisyona işler; burada yalnız ödünç kısma işlemesi gerekir,
boştaki kısım da nakit getirisini kazanır. İkisi `kos`'ta motor sonucunun üstüne eklenir (motor finansmansız çağrılır).
"""
from __future__ import annotations

import dataclasses
import hashlib
import time
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import yaml

from tradebot.arastirma import backtest as bt
from tradebot.arastirma import metrik as mt
from tradebot.arastirma.dogrulama import haftalik_dsr, izgara
from tradebot.arastirma.maliyet import YIL_MS, MaliyetModeli
from tradebot.cekirdek.gosterge import kayan_std, log_getiri

GUN_YIL = 252


def agirlik(kapanis: np.ndarray, hedef_vol: float, pencere: int, tavan: float) -> np.ndarray:
    """w[t] = min(tavan, hedef / σ̂[t]); σ̂ son `pencere` günlük log getirinin yıllık std'si (≤ t). Tanımsızsa 0."""
    s = kayan_std(log_getiri(np.asarray(kapanis, dtype=float)), pencere) * np.sqrt(GUN_YIL)
    w = np.where(np.isfinite(s) & (s > 0), hedef_vol / np.where(s > 0, s, 1.0), 0.0)
    return np.clip(w, 0.0, tavan)


def kos(t: np.ndarray, acilis: np.ndarray, w: np.ndarray, mm: MaliyetModeli, nakit_r: np.ndarray,
        borc_yillik: np.ndarray) -> bt.Sonuc:
    """Motor sonucu + boştaki kısmın nakit getirisi (1 − w)⁺·nakit_r − ödünç kısmın finansmanı (w − 1)⁺·borç·Δt.
    `nakit_r[i]`: nakdin bar i getirisi (açılış i → i+1); `borc_yillik[i]`: bar i'nin yıllık ödünç oranı."""
    s = bt.calistir(t, acilis, w, mm)
    sure = np.diff(np.asarray(t, dtype=np.int64)) / YIL_MS
    p = s.pozisyon
    net = s.net + np.maximum(1.0 - p, 0.0) * nakit_r[:-1] - np.maximum(p - 1.0, 0.0) * borc_yillik[:-1] * sure
    return dataclasses.replace(s, net=net, ozkaynak=np.cumprod(1.0 + net),
                               maliyet=s.maliyet + np.maximum(p - 1.0, 0.0) * borc_yillik[:-1] * sure)


def _ms(s: str) -> int:
    return int(datetime.fromisoformat(s).replace(tzinfo=UTC).timestamp() * 1000)


def _yil(t_ms: int) -> int:
    return datetime.fromtimestamp(t_ms / 1000, UTC).year


def ozet(s: bt.Sonuc, bas_ms: int | None = None, bit_ms: int | None = None) -> dict:
    """[bas, bit) dilimi: yıllık bileşik, Sharpe (günlük → yıllık), en kötü düşüş, en kötü hafta, −%25'in ilk günü."""
    m = np.ones(len(s.t), dtype=bool)
    if bas_ms is not None:
        m &= s.t >= bas_ms
    if bit_ms is not None:
        m &= s.t < bit_ms
    t, net = s.t[m], s.net[m]
    if len(net) < 20:
        return {"gun": int(len(net))}
    oz = np.cumprod(1.0 + net)
    tepe = np.maximum.accumulate(np.r_[1.0, oz])[1:]
    dd = oz / tepe - 1.0
    yil = (t[-1] - t[0]) / YIL_MS
    h = np.expm1(mt.haftalik_log(t, net))
    acil = np.flatnonzero(dd <= -0.25)
    return {"gun": int(len(net)), "yillik_bilesik": float(oz[-1] ** (1 / yil) - 1) if yil > 0 else 0.0,
            "sharpe": float(net.mean() / net.std(ddof=1) * np.sqrt(GUN_YIL)) if net.std(ddof=1) > 0 else 0.0,
            "en_kotu_dusus": float(dd.min()), "en_kotu_hafta": float(h.min()) if len(h) else 0.0,
            "carpan": float(oz[-1]), "ortalama_agirlik": float(s.pozisyon[m].mean()),
            "acil_ilk": None if not len(acil) else datetime.fromtimestamp(int(t[acil[0]]) / 1000, UTC).date().isoformat()}


def yillar(s: bt.Sonuc) -> dict[int, float]:
    out: dict[int, float] = {}
    for y in range(_yil(int(s.t[0])), _yil(int(s.t[-1])) + 1):
        m = (s.t >= _ms(f"{y}-01-01")) & (s.t < _ms(f"{y + 1}-01-01"))
        if m.any():
            out[y] = float(np.prod(1.0 + s.net[m]) - 1.0)
    return out


def walk_forward(kosular: dict[str, bt.Sonuc], is_yil: int, oos_yil: int) -> dict:
    """Her OOS yılında, önceki `is_yil` yılın Sharpe'ı en yüksek varyantın o yılki getirisi (zincirlenmiş)."""
    adlar = sorted(kosular)
    t = kosular[adlar[0]].t
    y0, y1 = _yil(int(t[0])) + is_yil, _yil(int(t[-1]))
    parca, secim = [], {}
    for y in range(y0, y1 + 1, oos_yil):
        is_m = (t >= _ms(f"{y - is_yil}-01-01")) & (t < _ms(f"{y}-01-01"))
        oos_m = (t >= _ms(f"{y}-01-01")) & (t < _ms(f"{y + oos_yil}-01-01"))
        if not oos_m.any() or is_m.sum() < 20:
            continue
        puan = {a: kosular[a].net[is_m].mean() / (kosular[a].net[is_m].std(ddof=1) or np.inf) for a in adlar}
        en = max(adlar, key=lambda a: puan[a])
        secim[y] = en
        parca.append(kosular[en].net[oos_m])
    net = np.concatenate(parca) if parca else np.zeros(0)
    yil = len(net) / GUN_YIL
    return {"secim": secim, "yillik_bilesik": float(np.prod(1 + net) ** (1 / yil) - 1) if yil > 0 else None,
            "sharpe": float(net.mean() / net.std(ddof=1) * np.sqrt(GUN_YIL)) if len(net) > 20 else None}


def borc_serisi(t_ms: np.ndarray, faiz_gunluk: np.ndarray | None, ek: float, sabit: float) -> np.ndarray:
    """Ödünç yıllık oran: faiz + ek; faiz yoksa (NaN ya da veri hiç yok) sabit."""
    if faiz_gunluk is None:
        return np.full(len(t_ms), sabit)
    return np.where(np.isfinite(faiz_gunluk), faiz_gunluk + ek, sabit)


def nakit_serisi(t_ms: np.ndarray, nakit_t: np.ndarray, nakit_acilis: np.ndarray) -> np.ndarray:
    """Nakdin bar i getirisi (açılış i → i+1, QQQ günleriyle hizalı); nakit verisi olmayan günde 0 (aleyhte)."""
    idx = {int(x): i for i, x in enumerate(nakit_t)}
    out = np.zeros(len(t_ms))
    for i in range(len(t_ms) - 1):
        a, b = idx.get(int(t_ms[i])), idx.get(int(t_ms[i + 1]))
        if a is not None and b is not None and nakit_acilis[a] > 0:
            out[i] = nakit_acilis[b] / nakit_acilis[a] - 1.0
    return out


def calistir(dosya: Path, depo, faiz_gunluk_fn=None, defter=None) -> dict:
    """Ön kayıtlı ızgara → deneme defteri + sonuç. `faiz_gunluk_fn(t_ms) -> np.ndarray | None` (OECD ABD 3 ay, PIT)."""
    d = yaml.safe_load(Path(dosya).read_text(encoding="utf-8"))
    bas, bit = _ms(d["bas"]), _ms(d["bit"])
    q = depo.oku(d["kimlik"], "1d", bas, bit)
    n = depo.oku(d["nakit"], "1d", bas, bit)
    t = q["acilis_ms"].to_numpy()
    acilis, kapanis = q["open"].to_numpy(), q["close"].to_numpy()
    vh = hashlib.sha256(q.write_ipc(None).getvalue() + n.write_ipc(None).getvalue()).hexdigest()
    nakit_r = nakit_serisi(t, n["acilis_ms"].to_numpy(), n["open"].to_numpy())
    faiz = faiz_gunluk_fn(t) if faiz_gunluk_fn is not None else None
    borc = borc_serisi(t, faiz, d["borc"]["ek"], d["borc"]["sabit"])
    mm = MaliyetModeli("abd_etf", **d["maliyet"])
    p = d["plan"]
    if defter is not None:
        defter.plan_ac(p["kimlik"], p["aile"], p["hipotez"], d["izgara"], [d["kimlik"]], yaml.safe_dump(d["olcut"]))
    yari = _ms(d["yari_bolum"])
    kiyas = {}
    for ad, sabit in (("al_tut", 1.0), ("al_tut_2x", 2.0)):
        s = kos(t, acilis, np.full(len(t), sabit), mm, nakit_r, borc)
        kiyas[ad] = {"tam": ozet(s), "ilk_yari": ozet(s, bit_ms=yari), "ikinci_yari": ozet(s, bas_ms=yari)}
    kosular, satir = {}, []
    for prm in izgara(d["izgara"]):
        t0 = time.perf_counter()
        ad = f"hedef={prm['hedef_vol']},pencere={prm['pencere_gun']},tavan={prm['tavan']}"
        s = kos(t, acilis, agirlik(kapanis, prm["hedef_vol"], prm["pencere_gun"], prm["tavan"]), mm, nakit_r, borc)
        kosular[ad] = s
        m = mt.hesapla(s).sozluk()
        satir.append({"ad": ad, "p": prm, "metrik": m, "tam": ozet(s), "ilk_yari": ozet(s, bit_ms=yari),
                      "ikinci_yari": ozet(s, bas_ms=yari), "yillar": yillar(s)})
        if defter is not None:
            defter.kaydet(p["kimlik"], "tarama", ad, p["aile"], prm, d["kimlik"], "1d", vh, m, time.perf_counter() - t0)
    aile_sr = [float(np.expm1(mt.haftalik_log(s.t, s.net)).mean() / np.expm1(mt.haftalik_log(s.t, s.net)).std(ddof=1))
               for s in kosular.values()]
    deneme = len(kosular) if defter is None else max(defter.deneme_sayisi(p["aile"]), len(kosular))
    wf = {tv: walk_forward({a: s for a, s in kosular.items() if a.endswith(f"tavan={tv}")},
                           d["walk_forward"]["is_yil"], d["walk_forward"]["oos_yil"]) for tv in d["izgara"]["tavan"]}
    o = d["olcut"]
    qt, q1, q2 = kiyas["al_tut"]["tam"], kiyas["al_tut"]["ilk_yari"], kiyas["al_tut"]["ikinci_yari"]
    for r in satir:
        s = kosular[r["ad"]]
        r["dsr"] = haftalik_dsr(s.t, s.net, deneme, aile_sr)
        r["wf"] = wf[r["p"]["tavan"]]
        tam, y1, y2 = r["tam"], r["ilk_yari"], r["ikinci_yari"]
        yp = r["yillar"]
        r["kapilar"] = {
            "dsr": r["dsr"]["dsr"] >= o["dsr_a"],
            "wf_oos": (r["wf"]["yillik_bilesik"] or -1) > o["oos_asgari_yillik"],
            "yil_pozitif": sum(v > 0 for v in yp.values()) / len(yp) >= o["yil_pozitif"],
            "en_kotu_hafta": tam["en_kotu_hafta"] >= o["en_kotu_hafta"],
            "acil_yok": tam["acil_ilk"] is None,
        }
        r["a"] = all(r["kapilar"].values())
        r["qqq_fazla_para"] = (tam["yillik_bilesik"] > qt["yillik_bilesik"] and y1["yillik_bilesik"] > q1["yillik_bilesik"]
                               and y2["yillik_bilesik"] > q2["yillik_bilesik"] and tam["en_kotu_dusus"] >= qt["en_kotu_dusus"])
        r["ayni_para_az_risk"] = all(
            x["yillik_bilesik"] >= o["para_oran"] * k["yillik_bilesik"]
            and x["en_kotu_dusus"] >= o["risk_oran"] * k["en_kotu_dusus"]
            for x, k in ((tam, qt), (y1, q1), (y2, q2)))
    return {"plan": p["kimlik"], "veri_hash": vh, "gun": int(len(t)), "kiyas": kiyas, "kollar": satir, "deneme": deneme}
