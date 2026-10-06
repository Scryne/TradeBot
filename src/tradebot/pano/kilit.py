"""Pano › kilit açılımı kolu (2026-10-06'dan beri ana bot): paper ve Demo kolları, olay başına sonuç, karar günlüğü,
kanıt kapısı ve takvimden yaklaşan açılımlar. Saf okuma; yazma yok.

Olay sonucu dolumlardan kurulur: olayın bacaklarına giden nakit (fiyat × adet + ücret) + açık bacakların son işaret
fiyatıyla değeri. Funding enstrüman başına tahakkuk ettiği için olaya bölünmez (kol düzeyinde ayrı yazılır); olay
sonucu "fonlama hariç"tir. Gerçek (Demo) kolda BTC koruması netlenir, olaya bağlı değildir: o kolda olay sonucu yalnız
token bacağıdır (`btc_dahil` yanlış).

Yaklaşan açılımlar düğümün o gün ham depoya yazdığı DefiLlama sayfasından ve Binance `exchangeInfo`'dan yeniden üretilir
(kural 9: tablo hamdan). Ayrıştırma pahalı: sonuç iki dosyanın hash'iyle önbellekte tutulur.
"""
from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.engine import Engine

from tradebot.canli import rapor
from tradebot.db import paper_emir_olay, paper_karar, paper_kol_olay

GUN_MS = 86_400_000
KARAR_GECIKME_MS = 5 * 60_000      # canli/kilit.KARAR_GECIKME_MS ile aynı (00:05 UTC)
YAKLASAN_GUN = 30
KAPANAN_LIMIT = 20
KARAR_LIMIT = 10
STRATEJI = "kilit_kisa"
_onbellek: dict[tuple[str, str, tuple, float], list[dict]] = {}


def durduruldu(olaylar: list[tuple[str, dict]]) -> bool:
    """canli/kilit.durum_kur ile aynı kural: son elle olay `durdur` mu (mutabakat durdurmaları sayılmaz)."""
    son = None
    for tur, ayr in olaylar:
        if tur == "devam" or (tur == "durdur" and (ayr or {}).get("neden") != "mutabakat"):
            son = tur
    return son == "durdur"


def _dusus(seri: list[tuple[int, float]]) -> float:
    tepe, en = 0.0, 0.0
    for _, v in seri:
        tepe = max(tepe, v)
        en = min(en, v / tepe - 1 if tepe else 0.0)
    return en


def _seyrek(seri: list[tuple[int, float]], azami: int = 400) -> list[list[float]]:
    """Çizgi için en çok ~`azami` nokta; son nokta her zaman dahil."""
    s = [list(x) for x in seri[:: max(1, len(seri) // azami)]]
    if seri and s[-1][0] != seri[-1][0]:
        s.append(list(seri[-1]))
    return s


def _olaylar(satirlar, fiyat: dict[str, float]) -> tuple[list[dict], float]:
    """Dolum + fonlama satırları → (olaylar, toplam fonlama nakdi). Olay = (sembol, açılım günü)."""
    ev: dict[tuple[str, int], dict] = {}
    net: dict[str, float] = defaultdict(float)
    fon = 0.0
    for tur, kim, q, p, u, zaman, ay in satirlar:
        ay = ay or {}
        if tur == "fonlama":
            fon -= float(u)
            continue
        q, p, u = float(q), float(p), float(u)
        net[kim] += q
        if "olay_ms" not in ay:
            continue
        e = ev.setdefault((ay["sembol"], int(ay["olay_ms"])), {
            "sembol": ay["sembol"], "olay_ms": int(ay["olay_ms"]), "giris_ms": None, "cikis_ms": int(ay["cikis_ms"]),
            "kapanis_ms": None, "neden": None, "notional": float(ay["notional"]), "nominal": 0.0, "nakit": 0.0,
            "adet": defaultdict(float), "perp": None, "btc_dahil": False})
        e["nakit"] -= q * p + u
        e["adet"][kim] += q
        if ay.get("bacak") == "token":
            e["perp"] = e["perp"] or kim
        else:
            e["btc_dahil"] = True
        if ay.get("islem") == "ac":
            e["giris_ms"] = e["giris_ms"] or int(ay["gun_ms"])
            if ay.get("bacak") == "token":
                e["nominal"] += abs(q * p)
        elif ay.get("islem") == "kapat":
            e["kapanis_ms"], e["neden"] = int(zaman), ay.get("neden") or "cikis"
    out = []
    for e in ev.values():
        token = e["adet"].get(e["perp"], 0.0) if e["perp"] else 0.0
        acik = abs(token) > 1e-12 and abs(net.get(e["perp"], 0.0)) > 1e-12
        kalan = {k: a for k, a in e["adet"].items() if abs(a) > 1e-12}
        eksik = [k for k in kalan if not fiyat.get(k)]
        sonuc = None if eksik else e["nakit"] + sum(a * fiyat[k] for k, a in kalan.items())
        out.append({k: e[k] for k in ("sembol", "olay_ms", "giris_ms", "cikis_ms", "notional", "btc_dahil")}
                   | {"acik": acik, "kapanis_ms": None if acik else e["kapanis_ms"], "neden": None if acik else e["neden"],
                      "nominal": round(e["nominal"], 2), "sonuc": None if sonuc is None else round(sonuc, 2),
                      "sonuc_oran": None if sonuc is None or not e["nominal"] else sonuc / e["nominal"]})
    return out, fon


def _kol(motor: Engine, r, isaret: list, simdi_ms: int) -> dict:
    ad, t = r.kol, r.tanim or {}
    bas = float(r.baslangic_ozkaynak)
    seri = [(x[0], x[1]) for x in isaret]
    fiyat = {k: float(v) for k, v in (isaret[-1][3] if isaret else {}).items()}
    with motor.connect() as b:
        satir = b.execute(select(paper_emir_olay.c.tur, paper_emir_olay.c.enstruman, paper_emir_olay.c.miktar,
                                 paper_emir_olay.c.fiyat, paper_emir_olay.c.ucret, paper_emir_olay.c.zaman_ms,
                                 paper_emir_olay.c.ayrinti)
                          .where(paper_emir_olay.c.kol == ad, paper_emir_olay.c.tur.in_(("dolum", "fonlama")))
                          .order_by(paper_emir_olay.c.id)).all()
        kararlar = b.execute(select(paper_karar.c.bar_ms, paper_karar.c.karar_ms, paper_karar.c.durum,
                                    paper_karar.c.ayrinti)
                             .where(paper_karar.c.kol == ad).order_by(paper_karar.c.bar_ms.desc()).limit(KARAR_LIMIT)).all()
        ret = b.execute(select(paper_emir_olay.c.zaman_ms, paper_emir_olay.c.enstruman, paper_emir_olay.c.ayrinti)
                        .where(paper_emir_olay.c.kol == ad, paper_emir_olay.c.tur == "ret")
                        .order_by(paper_emir_olay.c.id.desc()).limit(KARAR_LIMIT)).all()
    olaylar, fon = _olaylar(satir, fiyat)
    acik = sorted((e for e in olaylar if e["acik"]), key=lambda e: (e["olay_ms"], e["sembol"]))
    kapanan = sorted((e for e in olaylar if not e["acik"] and e["kapanis_ms"]), key=lambda e: -e["kapanis_ms"])
    girilen = {(e["sembol"], e["giris_ms"]) for e in olaylar}     # karardaki açılış dolduysa olay o gün girilmiştir
    oz = seri[-1][1] if seri else bas
    grup = t.get("grup_tanim") or {}
    return {
        "kol": ad, "gercek": ad.endswith("#gercek"), "ortam": grup.get("ortam"),
        "baslangic_ozkaynak": bas, "baslangic_ms": int(r.baslangic_ms), "ozkaynak": oz, "toplam": oz / bas - 1,
        "en_kotu_dusus": _dusus(seri), "fonlama": round(fon, 2),
        "son_isaret_ms": seri[-1][0] if seri else None,
        "durum": kararlar[0].durum if kararlar else None,
        "seri": _seyrek(seri),
        "kapi": rapor.kanit_kapisi(seri, simdi_ms),
        "acik": acik, "kapanan": kapanan[:KAPANAN_LIMIT],
        "kapanan_ozet": {"adet": len(kapanan), "kazanan": sum(1 for e in kapanan if (e["sonuc"] or 0) > 0),
                         "toplam": round(sum(e["sonuc"] or 0 for e in kapanan), 2)},
        "kararlar": [{"gun_ms": int(k.bar_ms), "karar_ms": int(k.karar_ms), "durum": k.durum,
                      "olay_sayisi": (k.ayrinti or {}).get("olay_sayisi"),
                      "ac": [{"sembol": x["sembol"], "dolum": (x["sembol"], int(k.bar_ms)) in girilen}
                             for x in (k.ayrinti or {}).get("ac", [])],
                      "kapat": [x["sembol"] for x in (k.ayrinti or {}).get("kapat", [])],
                      "red": [{"sembol": x["sembol"], "neden": x.get("neden")} for x in (k.ayrinti or {}).get("red", [])],
                      "takvim_hatasi": (k.ayrinti or {}).get("takvim_hatasi"),
                      "gecikmeli": bool((k.ayrinti or {}).get("gecikmeli"))} for k in kararlar],
        "retler": [{"zaman_ms": int(z), "enstruman": kim.split(":")[-1],
                    "gerekce": "; ".join((a or {}).get("gerekceler") or [])[:200]} for z, kim, a in ret],
    }


def _ham_son(motor: Engine, kaynak: str, on_ek: str) -> tuple[str, Path, str] | None:
    from tradebot.veri.depo import HamDepo

    d = HamDepo(Path("."), motor).dosyalar(kaynak, on_ek)
    return d[-1] if d else None


def _yaklasan(motor: Engine, simdi_ms: int, kural: dict, acik: set[tuple[str, int]],
              kapanan: dict[tuple[str, int], str]) -> dict | None:
    """Son takvim + son perp listesi → bugünden itibaren `YAKLASAN_GUN` gün içindeki eşik üstü açılımlar. Durum
    paper koluna göre: acik | kapandi (girildi, çıkış gününden önce kapandı; `neden`) | perp_yok | kacti | bekliyor."""
    import json

    from tradebot.arastirma import kilit as kl
    from tradebot.veri import binance_vadeli as bv
    from tradebot.veri import kilit as vk

    tk = _ham_son(motor, "defillama", "unlocks/gunluk/")
    px = _ham_son(motor, "binancef", "exchangeInfo")
    if tk is None:
        return None
    olay = kural.get("olay") or {}
    kat, asgari = tuple(olay.get("kategoriler") or ()), float(olay.get("asgari_oran") or 0)
    anahtar = (tk[2], px[2] if px else "", kat, asgari)
    if anahtar not in _onbellek:
        try:
            ev = kl.olaylar(vk.coz(Path(tk[1]).read_bytes()), list(kat), asgari)
            perp = bv.usdt_perpler(lambda _: Path(px[1]).read_bytes()) if px else {}
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            return {"takvim_gun_ms": int(tk[0].rsplit("/", 1)[-1]), "olaylar": [], "hata": "takvim okunamadı"}
        _onbellek.clear()
        _onbellek[anahtar] = [{"sembol": s, "olay_ms": int(g), "oran": float(o), "kategori": k,
                               "perp": bool(perp.get(s)) and perp[s].get("durum") == "TRADING"
                               and not perp[s].get("teslim_ms")}
                              for s, g, o, k in ev.select("sembol", "gun_ms", "oran", "kategori").iter_rows()]
    bugun = simdi_ms // GUN_MS * GUN_MS
    giris = int((kural.get("parametre") or {}).get("giris", -7))
    out = []
    for e in _onbellek[anahtar]:
        if not bugun <= e["olay_ms"] <= bugun + YAKLASAN_GUN * GUN_MS:
            continue
        g = e["olay_ms"] + giris * GUN_MS
        a = (e["sembol"], e["olay_ms"])
        durum = ("acik" if a in acik else "kapandi" if a in kapanan else "perp_yok" if not e["perp"]
                 else "kacti" if g < bugun or (g == bugun and simdi_ms - bugun >= KARAR_GECIKME_MS) else "bekliyor")
        out.append(e | {"giris_ms": g, "durum": durum, "neden": kapanan.get(a)})
    return {"takvim_gun_ms": int(tk[0].rsplit("/", 1)[-1]), "olaylar": out, "hata": None}


def kilit(motor: Engine, simdi_ms: int, kayit: dict, isaret: dict[str, list]) -> dict:
    """`kayit`: kol → paper_kol satırı; `isaret`: kol → [(zaman, özkaynak, pozisyon, fiyat)] (veri.pano'dan)."""
    adlar = [k for k, r in kayit.items() if (r.tanim or {}).get("strateji") == STRATEJI]
    with motor.connect() as b:
        ko = b.execute(select(paper_kol_olay.c.kol, paper_kol_olay.c.tur, paper_kol_olay.c.ayrinti)
                       .where(paper_kol_olay.c.kol.in_(adlar)).order_by(paper_kol_olay.c.zaman_ms)).all() if adlar else []
    elle: dict[str, list] = defaultdict(list)
    for k, tur, ayr in ko:
        elle[k].append((tur, ayr))
    aktif = [k for k in adlar if not durduruldu(elle[k])]
    kollar = sorted((_kol(motor, kayit[k], isaret.get(k, []), simdi_ms) for k in aktif),
                    key=lambda x: (x["gercek"], x["kol"]))
    kural = dict(kayit[aktif[0]].tanim or {}) if aktif else {}
    paper = [k for k in kollar if not k["gercek"]]
    acik = {(e["sembol"], e["olay_ms"]) for k in paper for e in k["acik"]}
    kapanan = {(e["sembol"], e["olay_ms"]): e["neden"] for k in paper for e in k["kapanan"]}
    gun = simdi_ms // GUN_MS * GUN_MS
    sonraki = gun + KARAR_GECIKME_MS if simdi_ms < gun + KARAR_GECIKME_MS else gun + GUN_MS + KARAR_GECIKME_MS
    par = kural.get("parametre") or {}
    olay = (kural.get("grup_tanim") or {}).get("olay") or {}
    return {
        "kollar": kollar,
        "kural": {"giris": par.get("giris"), "cikis": par.get("cikis"), "notional": par.get("notional"),
                  "azami_brut": par.get("azami_brut"), "azami_btc": par.get("azami_btc"),
                  "asgari_oran": olay.get("asgari_oran"), "kategoriler": olay.get("kategoriler") or []},
        "kapi": {"asgari_hafta": rapor.KANIT_ASGARI_HAFTA, "psr": rapor.KANIT_PSR},
        "sonraki_karar_ms": sonraki,
        "yaklasan": _yaklasan(motor, simdi_ms, {"parametre": par, "olay": olay}, acik, kapanan) if aktif else None,
    }
