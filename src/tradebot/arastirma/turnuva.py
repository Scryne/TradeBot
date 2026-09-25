"""Turnuva (Faz 5): kol = strateji × piyasa grubu × zaman dilimi. Eleme hunisi aşama 1–3 (Final Doküman §Turnuva).

Önceden yazılı plan: `config/turnuva/dalga1.yaml` (ızgaralar, gruplar, boyut, ölçüt) ve `docs/turnuva/Dalga-1.md`
(gerekçe). Plan dosyası koşudan ÖNCE commit edilir; plan kimliği deneme defterinde, kod sürümü her kayıtta.

Aşama 1: ızgaradaki her varyant (maliyet, frenler, oynaklık hedefi dahil) → deneme defteri.
Aşama 2: en iyi varyant için DSR (ailenin TÜM denemeleri), plato, walk-forward (IS'te seç, OOS'ta ölç), yıllık kırılım,
         rejim kırılımı (grup endeksinin son 26 haftası yukarı/aşağı).
Aşama 3: yürütme stresi (maliyet 2 kat; dolum bir bar geç). Nautilus parity motor düzeyinde kalıcı testtir
         (tests/test_nautilus_parity.py); kolların Nautilus'la yaşaması paper'dadır (Final Doküman §7).
Karar (A / B / KALDI) `karar()` içinde, dalga planındaki ölçütle birebir.
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import yaml

from tradebot.arastirma import dogrulama as dg
from tradebot.arastirma import metrik as mt
from tradebot.arastirma.backtest import Sonuc
from tradebot.arastirma.defter import Defter
from tradebot.arastirma.maliyet import MaliyetModeli, model
from tradebot.arastirma.panel import (
    GrupVerisi,
    calistir_panel,
    evren_maskesi,
    grup_yukle,
    izgaraya,
    kripto_dislanir_mi,
    kripto_ek_kayma_bps,
    kur_cevir,
    taraf_matrisi,
)
from tradebot.cekirdek import StratejiTanimi, nedensellik_testi, ornek
from tradebot.cekirdek import aileler as al
from tradebot.cekirdek.boyut import kaldirac_dogrula, panel_oynaklik_hedefi, yarim_kelly_tavani
from tradebot.risk.motor import PortfoyIzleyici, RiskAyar
from tradebot.veri.depo import BarDepo
from tradebot.veri.takvim import ZAMAN_DILIMI_MS

YIL_MS = int(365.25 * 86_400_000)

# ad → (aile, fonksiyon, tür)
STRATEJILER = {
    "tsmom": ("trend", ornek.tsmom, "tek"),
    "ma_yon": ("trend", al.ma_yon, "tek"),
    "donchian_ls": ("trend", al.donchian_ls, "tek"),
    "zskor_donus": ("ortalamaya_donus", al.zskor_donus, "tek"),
    "rsi_donus": ("ortalamaya_donus", al.rsi_donus, "tek"),
    "ay_donumu": ("takvim", al.ay_donumu, "tek"),
    "kesitsel_momentum": ("kesitsel_momentum", al.kesitsel_momentum, "panel"),
}


@dataclass(frozen=True)
class Olcut:
    """Dalga planındaki geçme ölçütü (config/turnuva/dalga1.yaml → olcut)."""
    dsr_a: float = 0.95
    dsr_b: float = 0.80
    yil_pozitif: float = 0.60
    rejim_t: float = -2.0
    stres_maliyet: float = 2.0


@dataclass
class Ayar:
    hedef_vol: float = 0.20
    kaldirac: float = 3.0
    vol_pencere_gun: int = 30
    frenler: bool = True
    bant: float = 0.25
    is_yil: float = 3.0
    oos_yil: float = 1.0
    olcut: Olcut = field(default_factory=Olcut)


def bar_gun(zd: str, takvim_adi: str) -> float:
    """Bir işlem gününde bar sayısı. 24 saatlik piyasalar (kripto, FX/CFD) için gün / zd; borsalarda yalnız 1d."""
    if takvim_adi in ("kripto_7x24", "fx_24x5"):
        return 86_400_000 / ZAMAN_DILIMI_MS[zd]
    if zd != "1d":
        raise ValueError(f"{takvim_adi} için yalnız 1d (gün içi borsa verisi yok)")
    return 1.0


def bar_yil(zd: str, takvim_adi: str) -> float:
    gun_yil = {"kripto_7x24": 365.25, "fx_24x5": 260.0}.get(takvim_adi, 252.0)
    return gun_yil * bar_gun(zd, takvim_adi)


def cevir(p: dict, bg: float) -> dict:
    """`*_gun` parametrelerini bara çevirir (en az 1)."""
    out = {}
    for k, v in p.items():
        if k.endswith("_gun"):
            out[k.removesuffix("_gun")] = max(1, int(round(v * bg)))
        else:
            out[k] = v
    return out


def kol_kimligi(strateji: str, grup: str, zd: str) -> str:
    return f"{strateji}@{grup}@{zd}"


def varyant_kimligi(aile: str, strateji: str, p: dict) -> str:
    return f"{aile}/{strateji}(" + ",".join(f"{k}={v}" for k, v in sorted(p.items())) + ")"


# ------------------------------------------------------------------ grup hazırlığı
@dataclass
class HazirGrup:
    g: GrupVerisi
    evrende: np.ndarray
    taraf: np.ndarray
    modeller: list[MaliyetModeli]
    takvim: str


def grup_hazirla(depo: BarDepo, kayit: dict[str, dict], tanim: dict, zd: str, bit_ms: int | None = None) -> HazirGrup:
    """`tanim`: dalga planındaki grup (kimlikler listesi ya da `dinamik: kripto|bist` + ilk_n; `kur`: USD'ye çevirme)."""
    if tanim.get("dinamik") == "kripto":
        adaylar = sorted(k for k, v in kayit.items() if v["piyasa"] == "BINANCE" and not kripto_dislanir_mi(k))
    elif tanim.get("dinamik") == "bist":
        adaylar = sorted(k for k, v in kayit.items() if v["piyasa"] == "BIST" and v["sinif"] == "hisse")
    else:
        adaylar = [k for k in tanim["kimlikler"] if k in kayit]
    ev = {k: tanim[k] for k in ("ilk_n", "likidite_gun", "asgari_gecmis_gun", "asgari_oynaklik") if k in tanim}
    if tanim.get("ilk_n"):
        # önce günlükte evren: hiç evrene girmeyenleri yüksek çözünürlükte yüklemeyelim
        gd = grup_yukle(depo, adaylar, "1d", bit_ms=bit_ms)
        e, _ = evren_maskesi(gd, **ev)
        adaylar = [k for j, k in enumerate(gd.kimlikler) if e[:, j].any()]
    g = grup_yukle(depo, adaylar, zd, bit_ms=bit_ms)
    evrende, lik = evren_maskesi(g, **ev)  # likidite yerel para cinsinden (sıralama için yeterli)
    if tanim.get("kur"):
        g = kur_cevir(g, depo, tanim["kur"])
    modeller = [model(kayit[k]["piyasa"], kayit[k]["sinif"]) for k in g.kimlikler]
    ek = kripto_ek_kayma_bps(lik) * np.array([kayit[k]["piyasa"] == "BINANCE" for k in g.kimlikler])
    takvimler = {kayit[k]["takvim"] for k in g.kimlikler}
    return HazirGrup(g, evrende, taraf_matrisi(g, modeller, ek), modeller, sorted(takvimler)[0])


# ------------------------------------------------------------------ koşu
def hedef_uret(h: HazirGrup, strateji: str, p: dict, yon: str, ayar: Ayar, nedensellik: bool = True) -> np.ndarray:
    aile, fonk, tur = STRATEJILER[strateji]
    g = h.g
    by, bg = bar_yil(g_zd(g), h.takvim), bar_gun(g_zd(g), h.takvim)
    if tur == "tek":
        tanim = StratejiTanimi(strateji, aile, fonk, p, yon=yon)
        if nedensellik:
            j = int(np.argmax([len(b) for b in g.barlar]))
            nedensellik_testi(tanim, g.barlar[j], deneme=3)
        s = np.column_stack([izgaraya(g, j, tanim.sinyal(b)) for j, b in enumerate(g.barlar)])
        olcekle = True
    else:
        pn = al.Panel(g.t, g.kapanis, h.evrende)
        if nedensellik:
            al.panel_nedensellik_testi(fonk, pn, deneme=3, **p)
        s = fonk(pn, **p)
        s = np.clip(s, -1.0 if yon == "long_short" else 0.0, 1.0)
        olcekle = False
    s = np.where(h.evrende, s, 0.0)
    return panel_oynaklik_hedefi(s, g.kapanis, h.evrende, ayar.hedef_vol, by, pencere=max(2, int(ayar.vol_pencere_gun * bg)),
                                 azami=ayar.kaldirac, varlik_olcekle=olcekle)


def g_zd(g: GrupVerisi) -> str:
    return next(z for z, v in ZAMAN_DILIMI_MS.items() if v == g.bar_ms)


def kos(h: HazirGrup, hedef: np.ndarray, ayar: Ayar, maliyet_carpani: float = 1.0) -> Sonuc:
    iz = (PortfoyIzleyici(RiskAyar(kaldirac=ayar.kaldirac), baslangic_ms=int(h.g.t[0]), acil_kalici=False)
          if ayar.frenler else None)
    return calistir_panel(h.g, hedef, h.taraf * maliyet_carpani, h.modeller, bant=ayar.bant, izleyici=iz)


def olc(s: Sonuc) -> dict:
    m = mt.hesapla(s)
    hs = np.expm1(mt.haftalik_log(s.t, s.net))
    sr_h = float(hs.mean() / hs.std(ddof=1)) if len(hs) > 1 and hs.std(ddof=1) > 0 else 0.0
    durum = s.durum if s.durum is not None else np.zeros(0)
    acil = int((durum == 3).sum())
    d = m.sozluk() | {"sharpe_haftalik": sr_h, "fren_bar": int((durum > 0).sum()), "acil_sayisi": acil,
                      "yarim_kelly": yarim_kelly_tavani(hs)}
    d["kapilar_gecti"] = bool(d["kapilar_gecti"] and acil == 0)
    return d


def rejim_kirilimi(h: HazirGrup, s: Sonuc, hafta_geri: int = 26) -> dict:
    """Grup endeksi (evrendeki enstrümanların eşit ağırlıklı getirisi) son `hafta_geri` haftada yukarı mı aşağı mı;
    her rejimde stratejinin haftalık log büyüme ortalaması ve t istatistiği."""
    c = h.g.kapanis
    with np.errstate(invalid="ignore", divide="ignore"):
        r = np.vstack([np.zeros((1, c.shape[1])), c[1:] / c[:-1] - 1.0])
    ev = h.evrende & np.isfinite(r)
    endeks = np.where(ev.any(axis=1), np.where(ev, r, 0.0).sum(axis=1) / np.maximum(ev.sum(axis=1), 1), 0.0)[:-1]
    e_h = mt.haftalik_log(s.t, endeks)
    st = mt.haftalik_log(s.t, s.net)
    geri = np.convolve(e_h, np.ones(hafta_geri), mode="full")[: len(e_h)]
    geri = np.r_[np.nan, geri[:-1]]  # hafta w'nin rejimi: w'den ÖNCEKİ haftalar
    out = {}
    for ad, m in (("yukari", geri > 0), ("asagi", geri <= 0)):
        x = st[m]
        out[ad] = {"hafta": int(m.sum()), "ort": float(x.mean()) if len(x) else 0.0,
                   "t": float(x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) if len(x) > 2 and x.std(ddof=1) > 0 else 0.0}
    return out


def karar(r: dict, o: Olcut) -> str:
    e, w, st = r["en_iyi"], r["walk_forward"], r["stres"]
    tam = e["kapilar_gecti"]
    wf = bool(w.get("pencere")) and w["oos_en_kotu_hafta"] >= mt.KAPI_EN_KOTU_HAFTA \
        and w["oos_en_kotu_dusus"] >= mt.KAPI_EN_KOTU_DUSUS and w["oos_yillik"] > 0
    yil = r["yil_pozitif_orani"] >= o.yil_pozitif
    rejim = all(v["t"] > o.rejim_t for v in r["rejim"].values())
    stres = st["maliyet_2x_puan"] > 0 and st["gecikme_puan"] > 0
    dsr = r["dsr"].get("dsr", float("nan"))
    ortak = tam and wf and yil and rejim and stres
    if ortak and dsr >= o.dsr_a and r["plato"]["plato_var"]:
        return "B" if r.get("en_fazla") == "B" else "A"  # veri yanlılığı bilinen grup A olamaz
    if ortak and dsr >= o.dsr_b:
        return "B"
    return "KALDI"


def kol_kos(defter: Defter, h: HazirGrup, plan: str, strateji: str, grup: str, izgara: dict, yon: str, ayar: Ayar,
            veri_etiketi: str = "", izin_kirli: bool = False, en_fazla: str = "A") -> dict:
    aile, _, _ = STRATEJILER[strateji]
    zd = g_zd(h.g)
    bg = bar_gun(zd, h.takvim)
    kol = kol_kimligi(strateji, grup, zd)
    kosular, puanlar, satirlar, hedefler = {}, {}, [], {}
    for p0 in dg.izgara(izgara):
        p = cevir(p0, bg)
        vk = varyant_kimligi(aile, strateji, p0)
        t0 = time.perf_counter()
        hedef = hedef_uret(h, strateji, p, yon, ayar)
        s = kos(h, hedef, ayar)
        m = olc(s)
        defter.kaydet(plan, "tarama", vk, aile, p0 | {"_bar": p, "boyut": {"hedef_vol": ayar.hedef_vol,
                      "kaldirac": ayar.kaldirac, "bant": ayar.bant}, "yon": yon}, f"kol:{grup}", zd,
                      h.g.veri_hash, m | {"kol": kol, "enstruman_sayisi": len(h.g.kimlikler)}, time.perf_counter() - t0,
                      izin_kirli=izin_kirli)
        kosular[vk] = {"net": s.net, "pozisyon": s.pozisyon, "t": s.t}
        puanlar[vk] = m["puan"]
        hedefler[vk] = hedef
        satirlar.append({"varyant": vk, **m})
    en_iyi = max(satirlar, key=lambda r: r["puan"])
    vk = en_iyi["varyant"]
    ek = kosular[vk]
    aile_sr = [float(x) for x in _aile_haftalik_sr(defter, aile)]
    dsr = dg.haftalik_dsr(ek["t"], ek["net"], defter.deneme_sayisi(aile), aile_sr)
    plato = dg.plato(izgara, puanlar, lambda p: varyant_kimligi(aile, strateji, p))
    ort_taraf = float(np.nanmean(h.taraf))
    wf = dg.walk_forward(ek["t"], kosular, int(ayar.is_yil * YIL_MS), int(ayar.oos_yil * YIL_MS),
                         puan=lambda t, n: float(np.mean(mt.haftalik_log(t, n))) if len(n) else -1.0,
                         taraf_maliyet=ort_taraf)
    wf_ozet = {"pencere": wf.get("pencere", 0), "farkli_secim": wf.get("farkli_secim", 0)}
    if wf.get("pencere"):
        z = np.zeros(len(wf["net"]))
        wm = mt.hesapla(Sonuc(wf["t"], z, wf["net"], z, wf["net"], z, wf["ozkaynak"]))
        wf_ozet |= {"oos_puan": wm.puan, "oos_yillik": wm.yillik_bilesik, "oos_en_kotu_dusus": wm.en_kotu_dusus,
                    "oos_en_kotu_hafta": wm.en_kotu_hafta, "oos_sharpe": wm.sharpe, "oos_hafta": wm.hafta,
                    "secimler": [x["secilen"] for x in wf["secimler"]]}
    yillik = dg.yillik_kirilim(ek["t"], ek["net"])
    tam_yillar = [v for y, v in yillik.items() if _tam_yil(ek["t"], y)]
    # aşama 3: yürütme stresi
    hedef = hedefler[vk]
    s2 = kos(h, hedef, ayar, maliyet_carpani=ayar.olcut.stres_maliyet)
    gec = np.vstack([np.zeros((1, hedef.shape[1])), hedef[:-1]])
    s3 = kos(h, gec, ayar)
    stres = {"maliyet_2x_puan": mt.hesapla(s2).puan, "maliyet_2x_yillik": mt.hesapla(s2).yillik_bilesik,
             "gecikme_puan": mt.hesapla(s3).puan, "gecikme_yillik": mt.hesapla(s3).yillik_bilesik}
    r = {"kol": kol, "aile": aile, "strateji": strateji, "grup": grup, "zd": zd, "yon": yon, "plan": plan,
         "enstruman": len(h.g.kimlikler), "bar": len(h.g.t), "veri_hash": h.g.veri_hash[:12], "veri": veri_etiketi,
         "donem": [int(h.g.t[0]), int(h.g.t[-1])],
         "en_iyi": en_iyi, "satirlar": sorted(satirlar, key=lambda x: -x["puan"]), "dsr": dsr, "plato": plato,
         "walk_forward": wf_ozet, "yillik": yillik,
         "yil_pozitif_orani": float(np.mean([v > 0 for v in tam_yillar])) if tam_yillar else 0.0,
         "rejim": rejim_kirilimi(h, Sonuc(ek["t"], ek["pozisyon"], ek["net"], ek["net"] * 0, ek["net"],
                                          ek["net"] * 0, np.cumprod(1 + ek["net"]))),
         "stres": stres, "en_fazla": en_fazla}
    r["karar"] = karar(r, ayar.olcut)
    return r


def _tam_yil(t: np.ndarray, yil: int) -> bool:
    ilk = np.datetime64(int(t[0]), "ms").astype("datetime64[Y]").astype(int) + 1970
    son = np.datetime64(int(t[-1]), "ms").astype("datetime64[Y]").astype(int) + 1970
    return ilk < yil < son


def _aile_haftalik_sr(defter: Defter, aile: str) -> list[float]:
    from sqlalchemy import select

    from tradebot.db import deneme

    with defter.motor.connect() as b:
        return [m.get("sharpe_haftalik", 0.0) for m in
                b.execute(select(deneme.c.metrik).where(deneme.c.aile == aile, deneme.c.tur == "tarama")).scalars()]


# ------------------------------------------------------------------ dalga dosyası
def dalga_oku(yol: Path) -> dict:
    d = yaml.safe_load(Path(yol).read_text(encoding="utf-8"))
    b = d["boyut"]
    kaldirac_dogrula(b["kaldirac"])
    d["_ayar"] = Ayar(hedef_vol=b["hedef_vol"], kaldirac=b["kaldirac"], vol_pencere_gun=b["vol_pencere_gun"],
                      frenler=d["frenler"], bant=b["bant"], is_yil=d["walk_forward"]["is_yil"],
                      oos_yil=d["walk_forward"]["oos_yil"], olcut=Olcut(**d["olcut"]))
    return d


def kollar(d: dict) -> list[dict]:
    """Dalga dosyasındaki her (strateji, grup, zd) kolu."""
    out = []
    for k in d["kollar"]:
        for grup in k["gruplar"]:
            for zd in k["zd"]:
                if zd not in d["gruplar"][grup].get("zd", [zd]):
                    continue
                out.append({"strateji": k["strateji"], "grup": grup, "zd": zd, "izgara": k["izgara"],
                            "yon": "long" if k.get("yon") == "long" else d["gruplar"][grup].get("yon", "long"),
                            "en_fazla": d["gruplar"][grup].get("en_fazla", "A"),
                            "plan": d["planlar"][STRATEJILER[k["strateji"]][0]]["kimlik"]})
    return out


def sonuc_yaz(r: dict, dizin: Path) -> Path:
    dizin.mkdir(parents=True, exist_ok=True)
    y = dizin / f"{r['kol'].replace('@', '__')}.json"
    y.write_text(json.dumps(r, ensure_ascii=False, indent=1, default=_json), encoding="utf-8")
    return y


def _json(x):
    if isinstance(x, np.generic):
        return x.item()
    if isinstance(x, np.ndarray):
        return x.tolist()
    return str(x)
