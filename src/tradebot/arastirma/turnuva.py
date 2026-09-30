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
from dataclasses import dataclass, field, replace
from functools import partial
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
    veto_maskesi,
)
from tradebot.cekirdek import StratejiTanimi, altin, nedensellik_testi, ornek
from tradebot.cekirdek import aileler as al
from tradebot.cekirdek import doviz_akis as da
from tradebot.cekirdek.boyut import kaldirac_dogrula, panel_oynaklik_hedefi, yarim_kelly_tavani
from tradebot.risk.motor import PortfoyIzleyici, RiskAyar
from tradebot.veri.depo import BarDepo
from tradebot.veri.takvim import ZAMAN_DILIMI_MS

YIL_MS = int(365.25 * 86_400_000)
YALNIZ_LONG_PIYASALAR = {"BINANCE", "BIST"}  # spot kripto ve BIST: açığa satış yok (grup yönü long_short olsa bile)

# ad → (aile, fonksiyon, tür)
STRATEJILER = {
    "tsmom": ("trend", ornek.tsmom, "tek"),
    "ma_yon": ("trend", al.ma_yon, "tek"),
    "donchian_ls": ("trend", al.donchian_ls, "tek"),
    "zskor_donus": ("ortalamaya_donus", al.zskor_donus, "tek"),
    "rsi_donus": ("ortalamaya_donus", al.rsi_donus, "tek"),
    "ay_donumu": ("takvim", al.ay_donumu, "tek"),
    "kesitsel_momentum": ("kesitsel_momentum", al.kesitsel_momentum, "panel"),
    "acilis_araligi": ("gun_ici_kirilim", al.acilis_araligi_kirilim, "tek"),
    "tasima": ("tasima", al.tasima, "tek"),   # VİOP 2: TL taşıma (docs/turnuva/VIOP-2.md)
    # Dalga 9: G10 döviz kesitseli (docs/turnuva/Dalga-9-Doviz.md); dört ölçüt tek aile (DSR bütün denemelerle)
    "doviz_tasima": ("doviz_kesitsel", partial(al.doviz_kesitsel, olcut="tasima"), "panel"),
    "doviz_momentum": ("doviz_kesitsel", partial(al.doviz_kesitsel, olcut="momentum"), "panel"),
    "doviz_birlesik": ("doviz_kesitsel", partial(al.doviz_kesitsel, olcut="birlesik"), "panel"),
    "doviz_dolar": ("doviz_kesitsel", partial(al.doviz_kesitsel, olcut="dolar"), "panel"),
    # Dalga 10: döviz akış ve olay primleri (docs/turnuva/Dalga-10-Akis.md); üç strateji tek aile
    "fomc_dolar": ("doviz_akis", da.fomc_dolar, "panel"),
    "ay_sonu_hedge": ("doviz_akis", da.ay_sonu_hedge, "panel"),
    "seans_para": ("doviz_akis", da.seans_para, "panel"),
    # Altın M15 (EA karşılığı; docs/turnuva/Altin-M15.md): giriş ailesi + EA risk katmanları
    "seans_kirilim": ("altin_m15", altin.seans_kirilim, "tek"),
    "kanal_kirilim": ("altin_m15", altin.kanal_kirilim, "tek"),
    "trend_geri_cekilme": ("altin_m15", altin.trend_geri_cekilme, "tek"),
    "bant_donus": ("altin_m15", altin.bant_donus, "tek"),
    "sikisma_kirilim": ("altin_m15", altin.sikisma_kirilim, "tek"),
    "ea_birlesik": ("altin_m15", altin.ea_birlesik, "tek"),
    # Altın M15 aynası (docs/turnuva/Altin-M15-Ters.md): AYNI aile — DSR orijinal 32 denemeyle birlikte sayılır
    "ters_seans_kirilim": ("altin_m15", altin.ters_seans_kirilim, "tek"),
    "ters_kanal_kirilim": ("altin_m15", altin.ters_kanal_kirilim, "tek"),
    "ters_trend_geri_cekilme": ("altin_m15", altin.ters_trend_geri_cekilme, "tek"),
    "ters_bant_donus": ("altin_m15", altin.ters_bant_donus, "tek"),
    "ters_sikisma_kirilim": ("altin_m15", altin.ters_sikisma_kirilim, "tek"),
    "ters_ea_birlesik": ("altin_m15", altin.ters_ea_birlesik, "tek"),
}


@dataclass(frozen=True)
class Olcut:
    """Dalga planındaki geçme ölçütü (config/turnuva/dalga1.yaml → olcut)."""
    dsr_a: float = 0.95
    dsr_b: float = 0.80  # ≤ 0: B için DSR şartı yok (Scryne kararı 2026-09-26, Dalga-1 ek 3)
    yil_pozitif: float = 0.60
    rejim_t: float = -2.0
    stres_maliyet: float = 2.0
    # Walk-forward OOS yıllık getirinin geçmesi gereken çıta (2026-09-28 kararı, Denetim-2026-09-28): risksiz faiz.
    # Varsayılan 0 = eski dalgaların ölçütü (geriye dönük değişmez, kural 10). USD dalgalarında T-bill; vadeli
    # sürekli seriler faiz farkını zaten içerdiği için orada 0.
    risksiz_yillik: float = 0.0


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
    jev_veto: bool = False  # True: zekâ katmanı vetoları backtest'te uygulanır (Jev'li kol; A/B için aynı kol iki kez)


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
    bar_yil_olcu: float | None = None  # karışık takvimli grup: ızgaradaki yıllık bar sayısı (veriden)
    yalniz_long: np.ndarray | None = None  # [k] bu enstrümanlarda negatif ağırlık yok
    veto: np.ndarray | None = None  # [n, k] zekâ katmanı vetoları (point-in-time)
    tasima: np.ndarray | None = None  # [n, k] döviz grubu: yıllık faiz farkı (dalga 9)
    para_yon: np.ndarray | None = None  # [k] döviz grubu: +1 XXXUSD, −1 USDXXX
    paralar: tuple[str, ...] | None = None  # [k] döviz akış grubu (dalga 10): USD dışındaki para


def grup_hazirla(depo: BarDepo, kayit: dict[str, dict], tanim: dict, zd: str, bit_ms: int | None = None,
                 vetolar: list[tuple[str, int, int | None]] | None = None) -> HazirGrup:
    """`tanim`: dalga planındaki grup (kimlikler listesi ya da `dinamik: kripto|bist` + ilk_n; `kur`: USD'ye çevirme;
    `seans`: pozisyon yalnız bu borsa takviminin seansında)."""
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
    if tanim.get("seans"):  # yalnız borsa seansında pozisyon (tatil, yarım gün dahil; çekirdek dışı takvim)
        from tradebot.veri.takvim import takvim

        evrende &= takvim(tanim["seans"]).acik_maske(g.t)[:, None]
    if tanim.get("kur"):
        g = kur_cevir(g, depo, tanim["kur"])
    if tanim.get("maliyet_modeli"):  # dalga 10: uygulama aracı kurumunun (NCM) sabit maliyeti, veri spread'i yerine
        from tradebot.arastirma.maliyet import MODELLER

        modeller = [MODELLER[tanim["maliyet_modeli"]] for _ in g.kimlikler]
    else:
        modeller = [model(kayit[k]["piyasa"], kayit[k]["sinif"]) for k in g.kimlikler]
    ek = kripto_ek_kayma_bps(lik) * np.array([kayit[k]["piyasa"] == "BINANCE" for k in g.kimlikler])
    takvimler = {kayit[k]["takvim"] for k in g.kimlikler}
    # Karışık takvim (ör. kripto 7/24 + ABD ETF): tek takvimin yıllık bar sayısı yanlış olur; ızgaradan ölçülür.
    # ETF'in hafta sonu barları ileri doldurulmuş (getiri 0) olduğundan ızgara başına yıllıklaştırma doğrudur.
    olcu = (len(g.t) - 1) / ((g.t[-1] - g.t[0]) / YIL_MS) if len(takvimler) > 1 and len(g.t) > 1 else None
    yl = np.array([kayit[k]["piyasa"] in YALNIZ_LONG_PIYASALAR for k in g.kimlikler])
    vm = veto_maskesi(g, vetolar) if vetolar is not None else None
    tas = yon_ = None
    if tanim.get("doviz"):  # dalga 9: USD karşılı döviz vekilleri; taşıma farkı serinin kendisinden (veri/vadeli.py)
        from tradebot.veri import vadeli as vd

        tas = np.column_stack([vd.tasima_farki(depo, k, g.t) for k in g.kimlikler])
        yon_ = np.array([vd.para_yonu(k) for k in g.kimlikler])
    paralar = None
    if tanim.get("para"):  # dalga 10: USD karşılı spot pariteler (DUKASCOPY:EURUSD …)
        yon_, paralar = para_bilgisi(g.kimlikler)
    if tanim.get("endeksler"):  # dalga 10 ay sonu: hisse endeksi günlük kapanışları (çekirdeğe dışarıdan verilir)
        g = replace(g, veri_hash=_endeks_yukle(depo, tanim["endeksler"], bit_ms, g.veri_hash))
    return HazirGrup(g, evrende, taraf_matrisi(g, modeller, ek), modeller, sorted(takvimler)[0], olcu, yl, vm, tas,
                     yon_, paralar)


def para_bilgisi(kimlikler: list[str]) -> tuple[np.ndarray, tuple[str, ...]]:
    """USD karşılı paritelerde yabancı paranın yönü ve adı: EURUSD → (+1, EUR), USDJPY → (−1, JPY)."""
    yon, ad = [], []
    for k in kimlikler:
        s = k.split(":")[-1]
        if len(s) != 6 or "USD" not in (s[:3], s[3:]):
            raise ValueError(f"{k}: USD karşılı parite değil")
        yon.append(1.0 if s[3:] == "USD" else -1.0)
        ad.append(s[:3] if s[3:] == "USD" else s[3:])
    return np.array(yon), tuple(ad)


def _endeks_yukle(depo: BarDepo, endeksler: dict[str, str], bit_ms: int | None, veri_hash: str) -> str:
    import hashlib

    import polars as pl

    seriler, hashler = {}, [veri_hash]
    for para, kimlik in sorted(endeksler.items()):
        df = depo.oku(kimlik, "1d").sort("acilis_ms")
        if bit_ms is not None:
            df = df.filter(pl.col("acilis_ms") < bit_ms)
        seriler[para] = (df["acilis_ms"].to_numpy(), df["close"].to_numpy())
        hashler.append(f"{kimlik}:{hashlib.sha256(depo.yol(kimlik, '1d').read_bytes()).hexdigest()}")
    da.endeks_ayarla(seriler)
    return hashlib.sha256("|".join(hashler).encode()).hexdigest()


# ------------------------------------------------------------------ koşu
def hedef_uret(h: HazirGrup, strateji: str, p: dict, yon: str, ayar: Ayar, nedensellik: bool = True) -> np.ndarray:
    aile, fonk, tur = STRATEJILER[strateji]
    g = h.g
    by, bg = h.bar_yil_olcu or bar_yil(g_zd(g), h.takvim), bar_gun(g_zd(g), h.takvim)
    if tur == "tek":
        tanim = StratejiTanimi(strateji, aile, fonk, p, yon=yon)
        if nedensellik:
            j = int(np.argmax([len(b) for b in g.barlar]))
            nedensellik_testi(tanim, g.barlar[j], deneme=3)
        s = np.column_stack([izgaraya(g, j, tanim.sinyal(b)) for j, b in enumerate(g.barlar)])
        olcekle = True
    else:
        pn = al.Panel(g.t, g.kapanis, h.evrende, h.tasima, h.para_yon, h.paralar)
        if nedensellik:
            al.panel_nedensellik_testi(fonk, pn, deneme=3, **p)
        s = fonk(pn, **p)
        s = np.clip(s, -1.0 if yon == "long_short" else 0.0, 1.0)
        olcekle = False
    s = np.where(h.evrende, s, 0.0)
    if h.yalniz_long is not None and h.yalniz_long.any():
        s[:, h.yalniz_long] = np.maximum(s[:, h.yalniz_long], 0.0)
    return panel_oynaklik_hedefi(s, g.kapanis, h.evrende, ayar.hedef_vol, by, pencere=max(2, int(ayar.vol_pencere_gun * bg)),
                                 azami=ayar.kaldirac, varlik_olcekle=olcekle,
                                 varlik_tavani=RiskAyar(kaldirac=ayar.kaldirac).enstruman_tavani)


def g_zd(g: GrupVerisi) -> str:
    return next(z for z, v in ZAMAN_DILIMI_MS.items() if v == g.bar_ms)


def kos(h: HazirGrup, hedef: np.ndarray, ayar: Ayar, maliyet_carpani: float = 1.0) -> Sonuc:
    iz = (PortfoyIzleyici(RiskAyar(kaldirac=ayar.kaldirac), baslangic_ms=int(h.g.t[0]), acil_kalici=False)
          if ayar.frenler else None)
    return calistir_panel(h.g, hedef, h.taraf * maliyet_carpani, h.modeller, bant=ayar.bant, izleyici=iz,
                          veto=h.veto if ayar.jev_veto else None)


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
        and w["oos_en_kotu_dusus"] >= mt.KAPI_EN_KOTU_DUSUS and w["oos_yillik"] > o.risksiz_yillik
    yil = r["yil_pozitif_orani"] >= o.yil_pozitif
    rejim = all(v["t"] > o.rejim_t for v in r["rejim"].values())
    stres = st["maliyet_2x_puan"] > 0 and st["gecikme_puan"] > 0
    dsr = r["dsr"].get("dsr", float("nan"))
    ortak = tam and wf and yil and rejim and stres
    if ortak and dsr >= o.dsr_a and r["plato"]["plato_var"]:
        return "B" if r.get("en_fazla") == "B" else "A"  # veri yanlılığı bilinen grup A olamaz
    if ortak and (o.dsr_b <= 0 or dsr >= o.dsr_b):
        return "B"
    return "KALDI"


def kol_kos(defter: Defter, h: HazirGrup, plan: str, strateji: str, grup: str, izgara: dict, yon: str, ayar: Ayar,
            veri_etiketi: str = "", izin_kirli: bool = False, en_fazla: str = "A") -> dict:
    aile, _, _ = STRATEJILER[strateji]
    zd = g_zd(h.g)
    bg = bar_gun(zd, h.takvim)
    kol = kol_kimligi(strateji, grup, zd) + ("+jev" if ayar.jev_veto else "")
    kosular, puanlar, satirlar, hedefler = {}, {}, [], {}
    for p0 in dg.izgara(izgara):
        p = cevir(p0, bg)
        vk = varyant_kimligi(aile, strateji, p0)
        t0 = time.perf_counter()
        hedef = hedef_uret(h, strateji, p, yon, ayar)
        s = kos(h, hedef, ayar)
        m = olc(s)
        defter.kaydet(plan, "tarama", vk, aile, p0 | {"_bar": p, "boyut": {"hedef_vol": ayar.hedef_vol,
                      "kaldirac": ayar.kaldirac, "bant": ayar.bant}, "yon": yon, "jev_veto": ayar.jev_veto}, f"kol:{grup}", zd,
                      h.g.veri_hash, m | {"kol": kol, "enstruman_sayisi": len(h.g.kimlikler)}, time.perf_counter() - t0,
                      izin_kirli=izin_kirli)
        kosular[vk] = {"net": s.net, "pozisyon": s.pozisyon, "t": s.t}
        puanlar[vk] = m["puan"]
        hedefler[vk] = hedef
        satirlar.append({"varyant": vk, **m})
    def stres_fonk(vk: str) -> tuple[Sonuc, Sonuc]:
        hedef = hedefler[vk]
        gec = np.vstack([np.zeros((1, hedef.shape[1])), hedef[:-1]])
        return kos(h, hedef, ayar, maliyet_carpani=ayar.olcut.stres_maliyet), kos(h, gec, ayar)

    def rejim_fonk(ek: dict) -> dict:
        return rejim_kirilimi(h, Sonuc(ek["t"], ek["pozisyon"], ek["net"], ek["net"] * 0, ek["net"], ek["net"] * 0,
                                       np.cumprod(1 + ek["net"])))

    r = {"kol": kol, "aile": aile, "strateji": strateji, "grup": grup, "zd": zd, "yon": yon, "plan": plan,
         "enstruman": len(h.g.kimlikler), "bar": len(h.g.t), "veri_hash": h.g.veri_hash[:12], "veri": veri_etiketi,
         "donem": [int(h.g.t[0]), int(h.g.t[-1])], "en_fazla": en_fazla}
    r |= degerlendir(defter, aile, strateji, izgara, kosular, puanlar, satirlar, ayar, float(np.nanmean(h.taraf)),
                     stres_fonk, rejim_fonk)
    r["karar"] = karar(r, ayar.olcut)
    return r


def degerlendir(defter: Defter, aile: str, strateji: str, izgara: dict, kosular: dict, puanlar: dict, satirlar: list,
                ayar: Ayar, ort_taraf: float, stres_fonk, rejim_fonk) -> dict:
    """Aşama 2–3 (kol türünden bağımsız): en iyi varyant, DSR, plato, walk-forward, yıllık, rejim, stres."""
    en_iyi = max(satirlar, key=lambda r: r["puan"])
    vk = en_iyi["varyant"]
    ek = kosular[vk]
    aile_sr = [float(x) for x in _aile_haftalik_sr(defter, aile)]
    dsr = dg.haftalik_dsr(ek["t"], ek["net"], defter.deneme_sayisi(aile), aile_sr)
    plato = dg.plato(izgara, puanlar, lambda p: varyant_kimligi(aile, strateji, p))
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
    s2, s3 = stres_fonk(vk)
    m2, m3 = mt.hesapla(s2), mt.hesapla(s3)
    haftalik = {"tam": _haftalik_seri(ek["t"], ek["net"])}
    if wf.get("pencere"):
        haftalik["oos"] = _haftalik_seri(wf["t"], wf["net"])
    return {"haftalik": haftalik,
            "en_iyi": en_iyi, "satirlar": sorted(satirlar, key=lambda x: -x["puan"]), "dsr": dsr, "plato": plato,
            "walk_forward": wf_ozet, "yillik": yillik,
            "yil_pozitif_orani": float(np.mean([v > 0 for v in tam_yillar])) if tam_yillar else 0.0,
            "rejim": rejim_fonk(ek),
            "stres": {"maliyet_2x_puan": m2.puan, "maliyet_2x_yillik": m2.yillik_bilesik,
                      "gecikme_puan": m3.puan, "gecikme_yillik": m3.yillik_bilesik}}


def _haftalik_seri(t: np.ndarray, net: np.ndarray) -> dict:
    """Portföy birleştirme için: {hafta numarası (UTC Pazartesi), haftalık log büyüme}."""
    h = (np.asarray(t, dtype=np.int64) - mt.PAZARTESI_KAYMA_MS) // mt.HAFTA_MS
    return {"hafta": [int(x) for x in np.unique(h)], "log": [round(float(x), 8) for x in mt.haftalik_log(t, net)]}


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
                      oos_yil=d["walk_forward"]["oos_yil"], olcut=Olcut(**d["olcut"]),
                      jev_veto=bool(d.get("jev_veto", False)))
    if d.get("haber_takvimi"):  # altın M15: haber filtresi (çekirdek G/Ç yapmaz; anlar buradan verilir)
        from tradebot.veri.haber_takvimi import yukle

        altin.haber_ayarla(yukle())
    if d.get("fomc_takvimi"):  # dalga 10: planlı FOMC karar günleri (önceden ilan edilir; olağanüstüler yok)
        da.fomc_ayarla(fomc_gunleri(Path(d["fomc_takvimi"])))
    return d


def fomc_gunleri(yol: Path) -> list[int]:
    from datetime import UTC, datetime

    g = yaml.safe_load(Path(yol).read_text(encoding="utf-8"))["gunler"]
    return [int(datetime.strptime(str(x), "%Y%m%d").replace(tzinfo=UTC).timestamp() * 1000) for x in g]


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


def dsr_sonlandir(defter: Defter, r: dict, o: Olcut) -> dict:
    """Dalga sonunda: DSR'ı ailenin NİHAİ deneme sayısı ve Sharpe varyansıyla yeniden hesaplar, kararı yeniler.
    Koşu anındaki DSR `dsr_kosu`'da kalır. (Koşu sırası sonucu etkilemesin: erken koşan kol daha az denemeyle
    ölçülmüş olmasın. Yalnız sıkılaştırır: deneme sayısı koşudan sonra yalnız artar.)"""
    d = r.get("dsr_kosu", r["dsr"])
    if "sr_haftalik" not in d:
        return r
    n = defter.deneme_sayisi(r["aile"])
    srs = [float(x) for x in _aile_haftalik_sr(defter, r["aile"])]
    v = float(np.var(srs, ddof=1)) if len(srs) > 1 else 0.0
    yeni = d | {"dsr": dg.dsr(d["sr_haftalik"], d["hafta"], max(n, 1), v, d["carpiklik"], d["basiklik"]),
                "sr_esik": dg.beklenen_max_sr(n, v), "deneme": n, "nihai": True}
    r = r | {"dsr_kosu": d, "dsr": yeni}
    r["karar"] = karar(r, o)
    return r


def carry_kol_kos(defter: Defter, plan: str, oranlar: dict, izgara: dict, ayar: Ayar, spot_taraf_bps: float,
                  veri_hash: str, bit_ms: int | None = None, notional: float = 0.5, veri_etiketi: str = "",
                  izin_kirli: bool = False) -> dict:
    """Funding carry kolu (dalga 1b). Frenler uygulanmaz (yönden bağımsız, düşük oynaklık); baz riski modellenmediği
    için en fazla B (arastirma/carry.py)."""
    from tradebot.arastirma import carry as cr

    aile, strateji, grup = "carry", "funding_carry", "kripto_funding"
    t, o, adlar = cr.funding_izgarasi(oranlar, bit_ms)
    kosular, puanlar, satirlar, sinyaller = {}, {}, [], {}
    for p0 in dg.izgara(izgara):
        vk = varyant_kimligi(aile, strateji, p0)
        t0 = time.perf_counter()
        s = cr.funding_sinyali(t, o, p0["pencere_gun"], p0["esik_yillik"])
        son = cr.calistir_carry(t, o, s, spot_taraf_bps, notional)
        m = olc(son)
        defter.kaydet(plan, "tarama", vk, aile, p0 | {"notional": notional}, f"kol:{grup}", "funding", veri_hash,
                      m | {"kol": f"{strateji}@{grup}", "enstruman_sayisi": len(adlar)}, time.perf_counter() - t0,
                      izin_kirli=izin_kirli)
        kosular[vk] = {"net": son.net, "pozisyon": son.pozisyon, "t": son.t}
        puanlar[vk] = m["puan"]
        sinyaller[vk] = s
        satirlar.append({"varyant": vk, **m})

    def stres_fonk(vk: str):
        s = sinyaller[vk]
        return (cr.calistir_carry(t, o, s, spot_taraf_bps, notional, maliyet_carpani=ayar.olcut.stres_maliyet),
                cr.calistir_carry(t, o, s, spot_taraf_bps, notional, gecikme=1))

    r = {"kol": f"{strateji}@{grup}@funding", "aile": aile, "strateji": strateji, "grup": grup, "zd": "funding",
         "yon": "notr", "plan": plan, "enstruman": len(adlar), "bar": len(t), "veri_hash": veri_hash[:12],
         "veri": veri_etiketi, "donem": [int(t[0]), int(t[-1])], "en_fazla": "B"}
    r |= degerlendir(defter, aile, strateji, izgara, kosular, puanlar, satirlar, ayar,
                     (spot_taraf_bps + cr.PERP_TARAF_BPS) / 1e4, stres_fonk, lambda ek: {})
    r["karar"] = karar(r, ayar.olcut)
    return r
