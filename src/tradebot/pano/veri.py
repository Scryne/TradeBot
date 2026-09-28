"""Pano verisi: defterden ve olay tablosundan türetilen salt okunur özet (saf okuma; yazma yok).

Kol getirileri haftalık raporla aynı hesaptır (`canli/rapor.ozetle`): pano ile Telegram raporu aynı sayıyı gösterir.
Karar şeridi saatliktir: hücre = o saatin son özkaynak işaretindeki brüt maruziyet (Σ|adet × fiyat| / özkaynak); veto ve
fren o saatte verilen kararlardan, işlem o saatteki dolumlardan gelir.
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path
from statistics import median

from sqlalchemy import func, select
from sqlalchemy.engine import Engine

from tradebot.canli import rapor
from tradebot.cekirdek.boyut import KALDIRAC_TAVANI
from tradebot.db import (
    deneme,
    jev_yargi,
    olay,
    paper_dagitim,
    paper_emir,
    paper_emir_olay,
    paper_karar,
    paper_kol,
    paper_kol_olay,
    paper_ozkaynak,
    test_plani,
)
from tradebot.risk.motor import RiskAyar

SAAT_MS = 3_600_000
GUN_MS = 24 * SAAT_MS
TURNUVA_GUN = 84          # 12 hafta (Final Doküman: paper turnuvası)
SERIT_SAAT = 72
BAYAT_MS = 2 * SAAT_MS    # son işaret bundan eskiyse pano "veri bayat" der (sağlık bekçisinin hata eşiği)
PAPER_ENSTRUMANLARI = ("BINANCE:BTCUSDT", "BINANCE:ETHUSDT")


def kol_bilgi(kol: str) -> dict:
    """Kol adından görünen parçalar: `d2:donchian_ls@kripto_btc_eth@4h+jev` → strateji, dalga, zaman dilimi, Jev."""
    jev = kol.endswith("+jev")
    taban = kol[: -len("+jev")] if jev else kol
    dalga, govde = (taban.split(":", 1) + [""])[:2] if ":" in taban else ("d1", taban)
    parca = govde.split("@")
    strateji = parca[0]
    zd = parca[2] if len(parca) > 2 else None
    tur = "agresif" if strateji == "agresif" else ("portfoy" if strateji == "portfoy" else "kol")
    return {"kol": kol, "taban": taban, "jev": jev, "strateji": strateji, "dalga": dalga, "zd": zd, "grup": parca[1]
            if len(parca) > 1 else "", "tur": tur}


def _maruziyet(ozkaynak: float, pozisyon: dict, fiyat: dict) -> tuple[float, dict[str, float]]:
    if not ozkaynak:
        return 0.0, {}
    oran = {k: float(a) * float(fiyat.get(k, 0.0)) / ozkaynak for k, a in (pozisyon or {}).items() if a}
    return sum(abs(x) for x in oran.values()), oran


def _seyrelt(seri: list[tuple[int, float]], adim_ms: int) -> list[list[float]]:
    """Her `adim_ms` aralığının son noktası (+ en son nokta): liste çizgisi için yeterli, JSON'u küçük tutar."""
    out: dict[int, tuple[int, float]] = {}
    for t, v in seri:
        out[t // adim_ms] = (t, v)
    s = [list(x) for x in out.values()]
    if seri and (not s or s[-1][0] != seri[-1][0]):
        s.append(list(seri[-1]))
    return s


def _turnuva(motor: Engine, simdi_ms: int) -> dict:
    with motor.connect() as b:
        bas = b.execute(select(func.min(paper_kol.c.baslangic_ms))).scalar()
    if bas is None:
        return {"bas_ms": None, "bit_ms": None, "gun": 0, "toplam_gun": TURNUVA_GUN}
    bas = int(bas)
    gun = min(TURNUVA_GUN, max(1, (simdi_ms - bas) // GUN_MS + 1))
    return {"bas_ms": bas, "bit_ms": bas + TURNUVA_GUN * GUN_MS, "gun": int(gun), "toplam_gun": TURNUVA_GUN,
            "hafta": int((gun - 1) // 7 + 1)}


def _isaretler(motor: Engine, simdi_ms: int) -> dict[str, list]:
    with motor.connect() as b:
        rows = b.execute(select(paper_ozkaynak.c.kol, paper_ozkaynak.c.zaman_ms, paper_ozkaynak.c.ozkaynak,
                                paper_ozkaynak.c.pozisyon, paper_ozkaynak.c.fiyat)
                         .where(paper_ozkaynak.c.zaman_ms <= simdi_ms).order_by(paper_ozkaynak.c.zaman_ms)).all()
    out: dict[str, list] = defaultdict(list)
    for r in rows:
        out[r.kol].append((int(r.zaman_ms), float(r.ozkaynak), r.pozisyon or {}, r.fiyat or {}))
    return out


def _serit(motor: Engine, isaret: dict[str, list], kollar: list[str], simdi_ms: int) -> dict:
    son_saat = simdi_ms // SAAT_MS * SAAT_MS
    saatler = [son_saat - (SERIT_SAAT - 1 - i) * SAAT_MS for i in range(SERIT_SAAT)]
    ilk = saatler[0]
    with motor.connect() as b:
        kararlar = b.execute(select(paper_karar.c.kol, paper_karar.c.karar_ms, paper_karar.c.durum, paper_karar.c.ayrinti)
                             .where(paper_karar.c.karar_ms >= ilk)).all()
        dolumlar = b.execute(select(paper_emir_olay.c.kol, paper_emir_olay.c.zaman_ms)
                             .where(paper_emir_olay.c.zaman_ms >= ilk, paper_emir_olay.c.tur != "ret")).all()
    veto, fren, islem = defaultdict(int), {}, defaultdict(int)
    for r in kararlar:
        h = (r.kol, int(r.karar_ms) // SAAT_MS * SAAT_MS)
        if (r.ayrinti or {}).get("veto"):
            veto[h] += 1
        if r.durum != "normal":
            fren[h] = r.durum
    for r in dolumlar:
        islem[(r.kol, int(r.zaman_ms) // SAAT_MS * SAAT_MS)] += 1
    satirlar = []
    for k in kollar:
        saatlik = {}
        for t, oz, poz, fy in isaret.get(k, []):
            if t >= ilk:
                saatlik[t // SAAT_MS * SAAT_MS] = _maruziyet(oz, poz, fy)[0]
        satirlar.append({"kol": k, "hucreler": [
            {"m": None if h not in saatlik else round(saatlik[h], 4), "v": veto.get((k, h), 0),
             "f": fren.get((k, h)), "i": islem.get((k, h), 0)} for h in saatler]})
    return {"saatler": saatler, "satirlar": satirlar}


def _olaylar(motor: Engine, simdi_ms: int) -> dict:
    from datetime import UTC, datetime

    bas = datetime.fromtimestamp((simdi_ms - 7 * GUN_MS) / 1000, UTC)
    with motor.connect() as b:
        sayim = b.execute(select(olay.c.rol, olay.c.tur, func.count()).where(olay.c.zaman >= bas)
                          .group_by(olay.c.rol, olay.c.tur)).all()
        liste = b.execute(select(olay).where(olay.c.tur.in_(("veto", "uyari")))
                          .order_by(olay.c.zaman.desc()).limit(30)).all()
        aktif = b.execute(select(olay).where(olay.c.tur == "veto", olay.c.enstruman.in_(PAPER_ENSTRUMANLARI),
                                             olay.c.gecerli_ms <= simdi_ms,
                                             (olay.c.bitis_ms.is_(None)) | (olay.c.bitis_ms > simdi_ms))).all()
        gun_once = datetime.fromtimestamp((simdi_ms - GUN_MS) / 1000, UTC)
        yargi = b.execute(select(jev_yargi.c.saglayici, jev_yargi.c.gecikme_ms, jev_yargi.c.hata)
                          .where(jev_yargi.c.zaman >= gun_once)).all()

    def _satir(r) -> dict:
        a = r.ayrinti or {}
        return {"id": int(r.id), "zaman_ms": int(r.zaman.timestamp() * 1000), "tur": r.tur, "rol": r.rol,
                "enstruman": r.enstruman, "neden": r.neden, "guven": a.get("guven"), "baslik": a.get("baslik"),
                "canli": a.get("canli"), "gecerli_ms": int(r.gecerli_ms),
                "bitis_ms": None if r.bitis_ms is None else int(r.bitis_ms)}

    gecikme = [float(r.gecikme_ms) for r in yargi if r.gecikme_ms is not None]
    return {"sayim_7g": [{"rol": r, "tur": t, "adet": int(n)} for r, t, n in sayim],
            "son": [_satir(r) for r in liste], "aktif_veto": [_satir(r) for r in aktif],
            "yargi_24s": {"adet": len(yargi), "hata": sum(1 for r in yargi if r.hata),
                          "nvidia": sum(1 for r in yargi if r.saglayici == "nvidia"),
                          "gecikme_medyan_ms": round(median(gecikme)) if gecikme else None}}


def _turnuva_sonuclari(veri_dizini: Path | None) -> dict[str, list[dict]]:
    """data/turnuva/*/*.json → plan kimliği başına kol kararları (KALDI / B / A)."""
    out: dict[str, list[dict]] = defaultdict(list)
    if veri_dizini is None:
        return out
    for y in sorted((Path(veri_dizini) / "turnuva").glob("*/*.json")):
        try:
            r = json.loads(y.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        en = r.get("en_iyi") or {}
        out[r.get("plan", "")].append({"kol": r.get("kol"), "karar": r.get("karar"), "sharpe": en.get("sharpe"),
                                       "yillik": en.get("yillik_bilesik"), "dsr": (r.get("dsr") or {}).get("dsr"),
                                       "dalga": y.parent.name})
    return out


def _defter(motor: Engine, veri_dizini: Path | None) -> dict:
    with motor.connect() as b:
        planlar = b.execute(select(test_plani.c.kimlik, test_plani.c.zaman, test_plani.c.aile, test_plani.c.hipotez,
                                   test_plani.c.durum, test_plani.c.sonuc).order_by(test_plani.c.zaman.desc())).all()
        sayi = dict(b.execute(select(deneme.c.plan, func.count()).group_by(deneme.c.plan)).all())
    sonuc = _turnuva_sonuclari(veri_dizini)
    out = []
    for p in planlar:
        kollar = sonuc.get(p.kimlik, [])
        kararlar = [k["karar"] for k in kollar]
        ozet = p.sonuc.split("\n", 1)[0][:220] if p.sonuc else None
        karar = ("A" if "A" in kararlar else "B" if "B" in kararlar else "KALDI" if kararlar else None)
        out.append({"kimlik": p.kimlik, "zaman_ms": int(p.zaman.timestamp() * 1000), "aile": p.aile,
                    "hipotez": p.hipotez[:400], "durum": p.durum, "sonuc": ozet, "deneme": int(sayi.get(p.kimlik, 0)),
                    "karar": karar, "kollar": kollar})
    return {"planlar": out, "deneme_toplam": int(sum(sayi.values()))}


def pano(motor: Engine, simdi_ms: int, veri_dizini: Path | None = None, kod_surumu: str = "") -> dict:
    """Ana sayfa verisi (tek istek). Sağlık ayrı uçtan gelir: ağ ölçümleri saniyeler sürer."""
    tv = _turnuva(motor, simdi_ms)
    isaret = _isaretler(motor, simdi_ms)
    with motor.connect() as b:
        kayit = {r.kol: r for r in b.execute(select(paper_kol))}
        son_karar = {r.kol: r for r in b.execute(
            select(paper_karar.c.kol, paper_karar.c.durum, paper_karar.c.karar_ms)
            .where(paper_karar.c.id.in_(select(func.max(paper_karar.c.id)).group_by(paper_karar.c.kol))))}
        kol_olay = b.execute(select(paper_kol_olay).order_by(paper_kol_olay.c.zaman_ms.desc()).limit(20)).all()
        dagitim = b.execute(select(paper_dagitim).order_by(paper_dagitim.c.hafta_ms.desc()).limit(1)).first()
        son24 = b.execute(select(func.count()).select_from(paper_karar)
                          .where(paper_karar.c.karar_ms >= simdi_ms - GUN_MS)).scalar()
        emir_ret = b.execute(select(func.count()).select_from(paper_emir)
                             .where(paper_emir.c.zaman_ms >= simdi_ms - GUN_MS, paper_emir.c.onaylanan == 0)).scalar()

    bas = tv["bas_ms"] or simdi_ms
    toplam = {k["kol"]: k for k in rapor.ozetle(rapor.topla(motor, bas, simdi_ms + 1))["kollar"]}
    gunluk = {k["kol"]: k for k in rapor.ozetle(rapor.topla(motor, simdi_ms - GUN_MS, simdi_ms + 1))["kollar"]}

    kollar = []
    for ad in sorted(kayit):
        r, t, g = kayit[ad], toplam.get(ad, {}), gunluk.get(ad, {})
        seri = [(x[0], x[1]) for x in isaret.get(ad, [])]
        brut, oran = (_maruziyet(*isaret[ad][-1][1:]) if isaret.get(ad) else (0.0, {}))
        sk = son_karar.get(ad)
        kollar.append({**kol_bilgi(ad), "sinif": r.sinif, "baslangic_ozkaynak": float(r.baslangic_ozkaynak),
                       "baslangic_ms": int(r.baslangic_ms), "ozkaynak": t.get("ozkaynak", float(r.baslangic_ozkaynak)),
                       "toplam": t.get("toplam", 0.0), "gun": g.get("hafta", 0.0), "en_kotu_dusus": t.get("en_kotu_dusus", 0.0),
                       "islem": t.get("islem", 0), "karar": t.get("karar", 0), "yurutme_bps": t.get("yurutme_bps"),
                       "gecikme_bps": t.get("gecikme_bps"), "fren": t.get("fren", 0), "veto": t.get("veto", 0),
                       "durum": sk.durum if sk else None, "son_karar_ms": int(sk.karar_ms) if sk else None,
                       "maruziyet": round(brut, 4), "pozisyon": {k: round(v, 4) for k, v in oran.items()},
                       "seri": _seyrelt(seri, 4 * SAAT_MS)})

    son_isaret = max((v[-1][0] for v in isaret.values() if v), default=None)
    son_karar_ms = max((k["son_karar_ms"] for k in kollar if k["son_karar_ms"]), default=None)
    durumlar = [k["durum"] for k in kollar if k["durum"]]
    return {
        "simdi_ms": simdi_ms, "kod_surumu": kod_surumu, "turnuva": tv,
        "durum": {"son_isaret_ms": son_isaret, "son_karar_ms": son_karar_ms,
                  "bayat": son_isaret is None or simdi_ms - son_isaret > BAYAT_MS,
                  "kol": len(kollar), "normal": durumlar.count("normal"),
                  "fren": sum(1 for d in durumlar if d.startswith("fren")), "acil": durumlar.count("acil_durdurma"),
                  "karar_24s": int(son24 or 0), "ret_24s": int(emir_ret or 0),
                  "islem_24s": sum(k["islem"] for k in gunluk.values()),
                  "veto_24s": sum(k["veto"] for k in gunluk.values())},
        "kollar": kollar,
        "serit": _serit(motor, isaret, sorted(kayit), simdi_ms),
        "tavan": {"enstruman": RiskAyar().enstruman_tavani, "sinif": RiskAyar().sinif_tavani,
                  "kaldirac": KALDIRAC_TAVANI, "gunluk_fren": RiskAyar().gunluk_fren,
                  "haftalik_fren": RiskAyar().haftalik_fren, "acil_durdurma": RiskAyar().acil_durdurma},
        "kol_olaylari": [{"kol": r.kol, "zaman_ms": int(r.zaman_ms), "tur": r.tur} for r in kol_olay],
        "dagitim": None if dagitim is None else {"portfoy": dagitim.portfoy, "hafta_ms": int(dagitim.hafta_ms),
                                                  "kaldirac": float(dagitim.kaldirac),
                                                  "kollar": (dagitim.ayrinti or {}).get("kollar", {})},
        "olaylar": _olaylar(motor, simdi_ms),
        "defter": _defter(motor, veri_dizini),
    }


def kol(motor: Engine, ad: str, simdi_ms: int) -> dict | None:
    """Kol çekmecesi: saatlik özkaynak (kolun ve ikizinin), son kararlar, son dolumlar, kol tanımı."""
    b_ = kol_bilgi(ad)
    ikiz = b_["taban"] if b_["jev"] else b_["taban"] + "+jev"
    with motor.connect() as b:
        r = b.execute(select(paper_kol).where(paper_kol.c.kol == ad)).first()
        if r is None:
            return None
        seriler = {}
        for k in (ad, ikiz):
            seriler[k] = [[int(x.zaman_ms), float(x.ozkaynak)] for x in b.execute(
                select(paper_ozkaynak.c.zaman_ms, paper_ozkaynak.c.ozkaynak)
                .where(paper_ozkaynak.c.kol == k, paper_ozkaynak.c.zaman_ms <= simdi_ms)
                .order_by(paper_ozkaynak.c.zaman_ms))]
        kararlar = b.execute(select(paper_karar).where(paper_karar.c.kol == ad)
                             .order_by(paper_karar.c.bar_ms.desc()).limit(48)).all()
        dolumlar = b.execute(select(paper_emir_olay, paper_emir.c.karar_fiyati, paper_emir.c.gonderim_fiyati,
                                    paper_emir.c.risk)
                             .join(paper_emir, paper_emir.c.id == paper_emir_olay.c.emir_id)
                             .where(paper_emir_olay.c.kol == ad).order_by(paper_emir_olay.c.zaman_ms.desc()).limit(40)).all()
    tanim = dict(r.tanim or {})
    return {
        **b_, "ikiz": ikiz if seriler.get(ikiz) else None, "sinif": r.sinif, "tanim": tanim,
        "baslangic_ozkaynak": float(r.baslangic_ozkaynak), "kod_surumu": r.kod_surumu,
        "seri": seriler[ad], "ikiz_seri": seriler.get(ikiz) or [],
        "kararlar": [{"bar_ms": int(k.bar_ms), "karar_ms": int(k.karar_ms), "durum": k.durum,
                      "veto": (k.ayrinti or {}).get("veto") or [], "hedef": (k.ayrinti or {}).get("hedef"),
                      "yeni": (k.ayrinti or {}).get("yeni"), "kimlikler": (k.ayrinti or {}).get("kimlikler"),
                      "gecikmeli": bool((k.ayrinti or {}).get("gecikmeli")), "kod_surumu": k.kod_surumu,
                      "veri_hash": k.veri_hash[:12]} for k in kararlar],
        "dolumlar": [{"zaman_ms": int(d.zaman_ms), "tur": d.tur, "enstruman": d.enstruman, "miktar": float(d.miktar),
                      "fiyat": None if d.fiyat is None else float(d.fiyat), "ucret": float(d.ucret),
                      "karar_fiyati": float(d.karar_fiyati), "gonderim_fiyati": d.gonderim_fiyati,
                      "risk_gerekce": (d.risk or {}).get("gerekceler") or []} for d in dolumlar],
    }
