"""Döviz taşıma kolu — MT5 demo düğümü (Dalga 9, ileriye dönük gözlem kolu). Nautilus dışı ayrı süreç (compose `doviz`).

Dalga 9 KALDI (docs/turnuva/Dalga-9-Doviz.md): ön kayıttaki kural gereği ailenin DSR'ı en yüksek varyantı
(`doviz_tasima`, n = 1) NCM forex DEMO hesabında çalışır. Beklenen getirisi sıfıra yakındır; amaç emir yolunun ve
ileriye dönük ölçümün (gerçek para kapısı: paper haftalarında PSR(0) ≥ 0,95 ve ≥ 26 hafta) çalışmasıdır.

Akış (her tur ~60 sn; `tur()` kaldığı yerden devam eder):
- Saat başı: kurum payı dahil taşıma tahakkuku (`fonlama`, aşağıda) → orta fiyatla özkaynak işareti (kalp atışı) →
  MT5 pozisyonlarıyla mutabakat (fark varsa log; defter esastır). Kol durdurulduysa ya da acil durdurma eşiği aşıldıysa
  pozisyonlar hemen kapanır (riski azaltan her şey otomatik, kural 7).
- İş günü `yurutme_saat_utc`'de (07:00, Londra açılışı; 21:00 UTC devir saatinde spread geniş) günde bir karar: NCM
  günlük barları (yalnız kapanmış; seans gününe etiketli) + OECD faizi (ham depoya, PIT, iki ay gecikmeli) →
  backtest'in AYNI fonksiyonları (`doviz_kesitsel`, `panel_oynaklik_hedefi`, `dengele_adim`; kural 3) → karar emirden
  ÖNCE deftere → her emir risk motorundan (kural 5) → MT5 demo piyasa emri → gerçek dolum deftere.

Defter para uzayında tutulur: enstrüman `PARA:EUR`, `PARA:JPY`…, miktar o paranın birimi, fiyat 1 biriminin USD değeri
(XXXUSD'de P, USDXXX'te 1/P). Böylece özkaynak = nakit (USD) + Σ adet × fiyat doğrusaldır; risk motoru USD nominaliyle
çalışır. USDJPY'de 0,10 lot alış = 10.000 USD uzun = 10.000 × P JPY kısa.

Maliyet (aleyhte, kural 4): MT5 dolum fiyatı `kayma_bps` kadar aleyhe kaydırılarak deftere yazılır (demo dolumu
iyimser olabilir; gerçek fiyat ayrıntıda). NCM demo hesabında majör swap'ları 0 (2026-09-30 ölçüldü): taşıma geliri ve
kurum payı demo özkaynağında yok. Defter bunu backtest'le aynı modelle tahakkuk eder: nakit += V × (r_para − r_USD) × dt
− |V| × kurum_payi × dt (V: pozisyonun USD değeri; faiz OECD, iki ay gecikmeli). Bu yüzden kolun özkaynağı MT5 demo
özkaynağından farklıdır; kapı defterle ölçülür.

Bilinen boşluk (v1): bağımsız gözetmen (katman 5) bu düğümün MT5 pozisyonlarını kapatamaz; donma bekçi kalp atışıyla
(Telegram) bildirilir. Demo hesap: kayıp sanal.
"""
from __future__ import annotations

import hashlib
import math
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
import polars as pl
from sqlalchemy import insert, select
from sqlalchemy.engine import Engine

from tradebot import denetim
from tradebot.arastirma.panel import dengele_adim
from tradebot.arastirma.turnuva import STRATEJILER, Ayar, bar_yil, cevir
from tradebot.canli.defter import PaperDefter
from tradebot.canli.karar import KolDurum
from tradebot.canli.kilit import izleyici
from tradebot.canli.kollar import PaperKol, oku
from tradebot.cekirdek import aileler as al
from tradebot.cekirdek.boyut import panel_oynaklik_hedefi
from tradebot.db import paper_emir, paper_emir_olay, paper_karar, paper_ozkaynak
from tradebot.kayit import log
from tradebot.risk.motor import Durum, EmirIstegi, Piyasa, Portfoy, RiskAyar, RiskMotoru
from tradebot.veri import faiz as fz
from tradebot.veri import vadeli as vd

DUGUM = "doviz"
ONEK = "PARA:"
SINIF = "doviz"
LOT = 100_000.0
GUN_MS = 86_400_000
SAAT_MS = 3_600_000
YIL_MS = 365.25 * GUN_MS
ASGARI_GECMIS = 60                     # evren: en az 60 günlük bar (dalga 9 grup tanımı)
GECMIS_GUN = 500                       # karar için istenen geçmiş (vol 90 + ısınma)
_log = log("doviz")


@dataclass(frozen=True)
class Para:
    kimlik: str        # vekil kimliği (VADELI:USDJPY): backtest serisi
    sembol: str        # MT5 sembolü
    para: str          # yabancı para (JPY)
    taban: str
    kote: str

    @property
    def xxxusd(self) -> bool:
        return self.kote == "USD"

    @property
    def yon(self) -> float:
        return 1.0 if self.xxxusd else -1.0

    def usd(self, p: float) -> float:
        """Yabancı paranın 1 biriminin USD değeri."""
        return p if self.xxxusd else 1.0 / p

    def lot_para(self, lot: float, p: float) -> float:
        """İşaretli lot (çift) → yabancı para adedi."""
        return lot * LOT if self.xxxusd else -lot * LOT * p

    def para_lot(self, q: float, p: float) -> float:
        return q / LOT if self.xxxusd else -q / (LOT * p)


@dataclass(frozen=True)
class DovizAyarlari:
    kol: PaperKol
    paralar: tuple[Para, ...]
    strateji: str
    parametre: dict
    hedef_vol: float
    vol_pencere_gun: int
    bant: float
    risk: RiskAyar
    kayma_bps: float
    kurum_payi_yillik: float
    yurutme_saat_utc: int
    magic: int
    lot_adimi: float = 0.01


def ayarlar(d: dict | None = None) -> DovizAyarlari | None:
    """`config/paper.yaml` `doviz` bloğu. Blok yoksa None (düğüm çalışmaz)."""
    d = d or oku()
    b = d.get("doviz")
    if not b:
        return None
    risk = RiskAyar(kaldirac=float(b["risk"]["kaldirac"]))
    paralar = []
    for kimlik, sembol in b["semboller"].items():
        _, taban, kote, _ = vd.VEKIL[kimlik.removeprefix("VADELI:")]
        paralar.append(Para(kimlik, sembol, taban if kote == "USD" else kote, taban, kote))
    bo = b["boyut"]
    ayar = Ayar(hedef_vol=float(bo["hedef_vol"]), kaldirac=risk.kaldirac, vol_pencere_gun=int(bo["vol_pencere_gun"]),
                frenler=bool(d.get("frenler", True)), bant=float(bo["bant"]))
    grup = {"dugum": DUGUM, "yon": "long_short", "doviz": True, "kimlikler": [p.kimlik for p in paralar],
            "semboller": dict(b["semboller"]), "maliyet": b["maliyet"], "yurutme_saat_utc": b["yurutme_saat_utc"],
            "hesap": "NCM forex demo"}
    kol = PaperKol(b["ad"], b["strateji"], "g10_doviz", grup, "1d", ayar, dict(b["parametre"]), b.get("sinif", "B"),
                   float(b.get("baslangic_ozkaynak", 10_000)))
    return DovizAyarlari(kol, tuple(paralar), b["strateji"], dict(b["parametre"]), ayar.hedef_vol, ayar.vol_pencere_gun,
                         ayar.bant, risk, float(b["maliyet"]["kayma_bps"]), float(b["maliyet"]["kurum_payi_yillik"]),
                         int(b["yurutme_saat_utc"]), int(b["magic"]))


# ---------------------------------------------------------------------------------------------------- saf karar
def seriler(barlar: dict[str, pl.DataFrame], paralar: tuple[Para, ...],
            aylik: dict[str, dict[tuple[int, int], float]]) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """NCM günlük barları (seans gününe etiketli) + OECD aylık faiz → ortak ızgara (t, close [n,k] vekil = spot + PIT
    taşıma, taşıma farkı [n,k], evrende [n,k]). Backtest'in vekil serisiyle aynı yöntem (`vadeli.fazla_getiri`)."""
    t = np.unique(np.concatenate([barlar[p.sembol]["acilis_ms"].to_numpy() for p in paralar]))
    k = len(paralar)
    close, tas, var = np.full((len(t), k), np.nan), np.full((len(t), k), np.nan), np.zeros((len(t), k), dtype=bool)
    for j, p in enumerate(paralar):
        df = barlar[p.sembol].sort("acilis_ms")
        g = df["acilis_ms"].to_numpy()
        rt = fz.gunluk(aylik.get(fz.PARA[p.taban], {}), g)
        rk = fz.gunluk(aylik.get(fz.PARA[p.kote], {}), g)
        seri, _ = vd.fazla_getiri(df, rt, rk)
        i = np.searchsorted(t, g)
        close[i, j], tas[i, j], var[i, j] = seri["close"].to_numpy(), rt - rk, True
    for x in (close, tas):   # ileri doldur (bar yoksa getiri 0)
        for j in range(k):
            son = np.nan
            for i in range(len(t)):
                if np.isnan(x[i, j]):
                    x[i, j] = son
                else:
                    son = x[i, j]
    evrende = np.cumsum(var, axis=0) >= ASGARI_GECMIS
    return t, close, tas, evrende


def hedef_agirlik(ay: DovizAyarlari, t: np.ndarray, close: np.ndarray, tas: np.ndarray, evrende: np.ndarray) -> np.ndarray:
    """Son barın kapanışındaki hedef çift ağırlıkları [k] (özkaynağa oran). `turnuva.hedef_uret`'in panel yolu."""
    _, fonk, _ = STRATEJILER[ay.strateji]
    yon = np.array([p.yon for p in ay.paralar])
    pn = al.Panel(t, close, evrende, tas, yon)
    s = np.clip(fonk(pn, **cevir(ay.parametre, 1.0)), -1.0, 1.0)
    s = np.where(evrende, s, 0.0)
    h = panel_oynaklik_hedefi(s, close, evrende, ay.hedef_vol, bar_yil("1d", "fx_24x5"), pencere=ay.vol_pencere_gun,
                              azami=ay.risk.kaldirac, varlik_olcekle=False, varlik_tavani=ay.risk.enstruman_tavani)
    return h[-1]


# ---------------------------------------------------------------------------------------------------- dış dünya
class Kaynak:
    """MT5 köprüsü (barlar, kotasyon, emir) + OECD faizi. `ist`: Mt5Istemci; `faiz_al() -> bytes`; `ham`: HamDepo."""

    def __init__(self, ist, faiz_al: Callable[[], bytes], ham=None) -> None:
        self.ist, self.faiz_al, self.ham = ist, faiz_al, ham
        self._aylik: dict | None = None
        self._faiz_gun: int | None = None
        self._sha = ""

    def aylik(self, gun: int) -> tuple[dict, str]:
        """OECD aylık faiz; günde bir indirilir, ham depoya yazılır (hash = kimlik). İndirilemezse son kayıtlı sürüm."""
        if self._faiz_gun != gun:
            try:
                icerik = self.faiz_al()
                if self.ham is not None:
                    self._sha = self.ham.kaydet("oecd", "IR3TIB/aylik", icerik, "csv")[1]
                else:
                    self._sha = hashlib.sha256(icerik).hexdigest()
                self._aylik, self._faiz_gun = fz.coz(icerik), gun
            except Exception as e:  # noqa: BLE001
                _log.warning("faiz_indirilemedi", hata=f"{type(e).__name__}: {e}"[:200])
                if self._aylik is None and self.ham is not None:
                    son = self.ham.dosyalar("oecd", "IR3TIB/aylik")
                    if son:
                        self._aylik, self._sha = fz.coz(son[-1][1].read_bytes()), son[-1][2]
        if self._aylik is None:
            raise RuntimeError("faiz verisi yok")
        return self._aylik, self._sha

    def gunluk(self, paralar: tuple[Para, ...], simdi_ms: int) -> dict[str, pl.DataFrame]:
        from tradebot.veri.mt5 import katalog_barlari

        fark = int(self.ist.saglik()["fark_sn"]) * 1000
        ozellik = self.ist.semboller([p.sembol for p in paralar])
        out = {}
        for p in paralar:
            df = self.ist.mumlar(p.sembol, "D1", simdi_ms - GECMIS_GUN * GUN_MS, simdi_ms)
            out[p.sembol] = katalog_barlari(df, "1d", fark, False, float(ozellik[p.sembol]["point"]))
        return out

    def kotasyon(self, paralar: tuple[Para, ...]) -> dict[str, dict]:
        return self.ist.kotasyon([p.sembol for p in paralar])["kotasyon"]


# ---------------------------------------------------------------------------------------------------- durum
@dataclass
class DovizDurum:
    nakit: float
    adet: dict[str, float]                  # PARA:XXX → adet
    gecmis: list[tuple[int, float]]         # özkaynak işaretleri
    son_fonlama: int                        # son tahakkuk zamanı (ms; 0 = hiç)
    durdurulmus: bool
    kararlar: dict[int, int] = field(default_factory=dict)       # gün → karar id
    son_fiyat: dict[str, float] = field(default_factory=dict)
    etkin: dict[str, float] = field(default_factory=dict)        # son kararın etkin hedefi (çift ağırlığı)
    lot: dict[str, float] = field(default_factory=dict)          # MT5 sembolü → defterdeki net lot (dolumlardan)

    def ozkaynak(self, fiyat: dict[str, float]) -> float:
        return self.nakit + sum(a * fiyat.get(k, self.son_fiyat.get(k, 0.0)) for k, a in self.adet.items())


def durum_kur(defter: PaperDefter, kol: str, baslangic: float) -> DovizDurum:
    m = defter.motor
    with m.connect() as b:
        olay = list(b.execute(select(paper_emir_olay.c.tur, paper_emir_olay.c.enstruman, paper_emir_olay.c.miktar,
                                     paper_emir_olay.c.fiyat, paper_emir_olay.c.ucret, paper_emir_olay.c.ayrinti)
                              .where(paper_emir_olay.c.kol == kol, paper_emir_olay.c.tur.in_(("dolum", "fonlama")))
                              .order_by(paper_emir_olay.c.id)))
        isaretler = list(b.execute(select(paper_ozkaynak.c.zaman_ms, paper_ozkaynak.c.ozkaynak, paper_ozkaynak.c.fiyat)
                                   .where(paper_ozkaynak.c.kol == kol).order_by(paper_ozkaynak.c.zaman_ms)))
        kararlar = list(b.execute(select(paper_karar.c.bar_ms, paper_karar.c.id, paper_karar.c.ayrinti)
                                  .where(paper_karar.c.kol == kol).order_by(paper_karar.c.bar_ms)))
    nakit, adet, son_fon, lot = baslangic, defaultdict(float), 0, defaultdict(float)
    for tur, kim, q, p, u, ay in olay:
        ay = ay or {}
        if tur == "fonlama":
            nakit -= u
            son_fon = max(son_fon, int(ay.get("bit_ms", 0)))
            continue
        adet[kim] += q
        nakit -= q * p + u
        for x in ay.get("mt5", []):
            lot[ay["sembol"]] += float(x["lot"])
    son_elle = None
    for o in defter.kol_olaylari(kol):
        if o.tur == "devam" or (o.tur == "durdur" and o.ayrinti.get("neden") != "mutabakat"):
            son_elle = o.tur
    etkin = {}
    for _, _, ay in kararlar:
        if ay and "etkin" in ay:
            etkin = dict(zip(ay["kimlikler"], ay["etkin"], strict=True))
    return DovizDurum(nakit, {k: v for k, v in adet.items() if abs(v) > 1e-9}, [(int(t), float(o)) for t, o, _ in isaretler],
                      son_fon, son_elle == "durdur", {int(g): int(i) for g, i, _ in kararlar},
                      dict(isaretler[-1][2] or {}) if isaretler else {}, etkin,
                      {s: round(v, 8) for s, v in lot.items() if abs(v) > 1e-9})


# ---------------------------------------------------------------------------------------------------- düğüm
class DovizDugumu:
    def __init__(self, defter: PaperDefter, ay: DovizAyarlari, kaynak: Kaynak, saat: Callable[[], float] = time.time):
        self.defter, self.ay, self.kaynak, self.saat = defter, ay, kaynak, saat
        self.m: Engine = defter.motor
        self.kol = ay.kol
        self.risk = RiskMotoru(ay.risk)

    def ac(self) -> None:
        if self.defter.kol_ac(self.kol, int(self.saat() * 1000)):
            _log.info("kol_acildi", kol=self.kol.ad)

    def _d(self) -> DovizDurum:
        return durum_kur(self.defter, self.kol.ad, self.kol.baslangic_ozkaynak)

    # ------------------------------------------------------------------ tur
    def tur(self) -> dict:
        simdi = int(self.saat() * 1000)
        d = self._d()
        out: dict = {}
        saat_bas = simdi // SAAT_MS * SAAT_MS
        if not d.gecmis or d.gecmis[-1][0] < saat_bas:
            out["isaret"] = self._saatlik(d, saat_bas)
            d = self._d()
        gun = simdi // GUN_MS * GUN_MS
        is_gunu = ((gun // GUN_MS) + 3) % 7 < 5          # 1970-01-01 Perşembe → Pazartesi = 0
        if gun in d.kararlar:
            devam = self._devam(d.kararlar[gun])
            if devam:
                out["devam"] = devam
        elif is_gunu and simdi - gun >= self.ay.yurutme_saat_utc * SAAT_MS and gun >= self._ilk_gun():
            out["karar"] = self._gunluk(d, gun, simdi)
        return out

    def _ilk_gun(self) -> int:
        b = self.defter.kol_baslangic(self.kol.ad) or 0
        return b // GUN_MS * GUN_MS

    def _fiyatlar(self) -> tuple[dict[str, float], dict[str, tuple[float, float, int]]]:
        """PARA:XXX → USD değeri (orta fiyat) ve sembol → (bid, ask, tik_ms)."""
        kot = self.kaynak.kotasyon(self.ay.paralar)
        fiyat, ham = {}, {}
        for p in self.ay.paralar:
            q = kot.get(p.sembol)
            if q and q["bid"] > 0 and q["ask"] > 0:
                ham[p.sembol] = (q["bid"], q["ask"], int(q["tik_ms"]))
                fiyat[ONEK + p.para] = p.usd((q["bid"] + q["ask"]) / 2)
        return fiyat, ham

    # ------------------------------------------------------------------ saatlik
    def _saatlik(self, d: DovizDurum, saat_bas: int) -> dict:
        fiyat, ham = self._fiyatlar()
        fon = self._fonlama(d, fiyat, saat_bas)
        if fon:
            d = self._d()
        oz = d.ozkaynak(fiyat)
        self.defter.ozkaynak_yaz(self.kol.ad, saat_bas, KolDurum(oz, d.nakit, dict(d.adet)),
                                 {k: fiyat.get(k, d.son_fiyat.get(k, 0.0)) for k in d.adet})
        _, gecis = izleyici(d.gecmis + [(saat_bas, oz)], self.kol.baslangic_ozkaynak, self.ay.risk)
        neden = "durdur" if d.durdurulmus else ("acil_durdurma" if gecis == Durum.ACIL_DURDURMA else None)
        kapat = {}
        if neden and d.adet:
            kapat = self._yurut(d, None, saat_bas, {p.para: 0.0 for p in self.ay.paralar}, fiyat, ham, "K", neden)
            if neden == "acil_durdurma":
                denetim.kaydet(self.m, "doviz", "acil_durdurma_kapatma", {"kol": self.kol.ad, "ozkaynak": oz})
        return {"ozkaynak": round(oz, 2), "fonlama": round(fon, 4), "mutabakat": self._mutabakat(d),
                **({"kapatilan": kapat} if kapat else {})}

    def _fonlama(self, d: DovizDurum, fiyat: dict[str, float], bit: int) -> float:
        """Son işaretten `bit`'e kadar taşıma − kurum payı (backtest modeli; pozisyon aralıkta sabit sayılır). Faiz yoksa
        aralık atlanır ve loglanır (faiz günde bir iner, olmazsa ham depodaki son sürüm kullanılır). Dönüş: nakit etkisi."""
        if not d.adet or not d.gecmis:
            return 0.0
        bas = max(d.son_fonlama, d.gecmis[-1][0])
        if bit <= bas:
            return 0.0
        try:
            aylik, _ = self.kaynak.aylik(bit // GUN_MS * GUN_MS)
        except Exception as e:  # noqa: BLE001
            _log.error("doviz_fonlama_atlandi", bas=bas, bit=bit, hata=f"{type(e).__name__}: {e}"[:120])
            return 0.0
        dt = (bit - bas) / YIL_MS
        an = np.array([bit])
        r_usd = float(np.nan_to_num(fz.gunluk(aylik.get(fz.PARA["USD"], {}), an)[0]))
        toplam = 0.0
        for p in self.ay.paralar:
            kim = ONEK + p.para
            a = d.adet.get(kim, 0.0)
            if abs(a) < 1e-9:
                continue
            r = float(np.nan_to_num(fz.gunluk(aylik.get(fz.PARA[p.para], {}), an)[0]))
            v = a * fiyat.get(kim, d.son_fiyat.get(kim, 0.0))
            etki = v * (r - r_usd) * dt - abs(v) * self.ay.kurum_payi_yillik * dt
            self.defter.olay_yaz(0, self.kol.ad, "fonlama", kim, 0.0, fiyat.get(kim), -etki, bit,
                                 {"bas_ms": bas, "bit_ms": bit, "deger_usd": v, "r_para": r, "r_usd": r_usd,
                                  "kurum_payi": self.ay.kurum_payi_yillik})
            toplam += etki
        return toplam

    def _mutabakat(self, d: DovizDurum) -> dict:
        """Defter ile MT5 demo pozisyonları (bu kolun sihirli sayısı) karşılaştırılır; fark loglanır, düzeltilmez."""
        try:
            poz = self.kaynak.ist.pozisyonlar(self.ay.magic)
        except Exception as e:  # noqa: BLE001
            return {"hata": f"{type(e).__name__}: {e}"[:120]}
        mt5 = defaultdict(float)
        for x in poz:
            mt5[x["sembol"]] += float(x["hacim"])
        fark = {}
        for p in self.ay.paralar:
            defter_lot = d.lot.get(p.sembol, 0.0)
            if abs(defter_lot - mt5.get(p.sembol, 0.0)) > self.ay.lot_adimi / 2 + 1e-9:
                fark[p.sembol] = {"defter": round(defter_lot, 2), "mt5": round(mt5.get(p.sembol, 0.0), 2)}
        if fark:
            _log.error("doviz_mutabakat_farki", fark=fark)
        return {"fark": fark} if fark else {"tamam": True}

    # ------------------------------------------------------------------ günlük
    def _gunluk(self, d: DovizDurum, gun: int, simdi: int) -> dict:
        aylik, sha = self.kaynak.aylik(gun)
        barlar = self.kaynak.gunluk(self.ay.paralar, simdi)
        t, close, tas, evrende = seriler(barlar, self.ay.paralar, aylik)
        hedef = hedef_agirlik(self.ay, t, close, tas, evrende)
        fiyat, ham = self._fiyatlar()
        oz = d.ozkaynak(fiyat)
        kaymis = np.array([d.adet.get(ONEK + p.para, 0.0) * fiyat.get(ONEK + p.para, 0.0) * p.yon / oz
                           for p in self.ay.paralar])
        iz, _ = izleyici(d.gecmis, self.kol.baslangic_ozkaynak, self.ay.risk)
        durum = iz.durum.value
        onceki = np.array([d.etkin.get(p.kimlik, 0.0) for p in self.ay.paralar])
        k = len(self.ay.paralar)
        islem_ok = np.array([p.sembol in ham for p in self.ay.paralar])
        hedef_d = np.zeros(k) if d.durdurulmus else hedef
        yeni, etkin, islem = dengele_adim(hedef_d, kaymis, onceki, not d.etkin, islem_ok, np.zeros(k, dtype=bool),
                                          durum, None, self.ay.bant)
        ayr = {"tur": self.ay.strateji, "kimlikler": [p.kimlik for p in self.ay.paralar], "hedef": hedef.tolist(),
               "etkin": etkin.tolist(), "kaymis": kaymis.tolist(), "yeni": yeni.tolist(),
               "islem": [bool(x) for x in islem], "son_bar_ms": int(t[-1]), "tasima": tas[-1].tolist(),
               "ozkaynak": oz, "faiz_sha": sha, "gecikmeli": False}
        veri_hash = f"{int(t[-1])}:{sha[:24]}"
        with self.m.begin() as b:
            kid = int(b.execute(insert(paper_karar).values(
                kol=self.kol.ad, bar_ms=gun, karar_ms=int(self.saat() * 1000), kod_surumu=self.defter.kod,
                veri_hash=veri_hash[:64], durum=durum, ayrinti=ayr)).inserted_primary_key[0])
        hedef_para = {p.para: float(yeni[j] * p.yon) for j, p in enumerate(self.ay.paralar) if islem[j]}
        sonuc = self._yurut(d, kid, gun, hedef_para, fiyat, ham, "D")
        hedef_l = [round(float(x), 3) for x in hedef]
        _log.info("doviz_karar", gun=gun, durum=durum, hedef=hedef_l, islem=int(islem.sum()))
        return {"karar_id": kid, "hedef": hedef_l, **sonuc}

    def _devam(self, karar_id: int) -> dict | None:
        """Karar yazılıp emir sonucu deftere geçmeden süreç durduysa: emri yazılmış ama olayı olmayan her emir için MT5
        işlem geçmişinde aynı yorum aranır; bulunursa dolum deftere yazılır (çift emir gönderilmez)."""
        with self.m.connect() as b:
            emirler = list(b.execute(select(paper_emir.c.id, paper_emir.c.istemci_emir_id, paper_emir.c.enstruman,
                                            paper_emir.c.zaman_ms).where(paper_emir.c.karar_id == karar_id)))
            olayli = set(b.execute(select(paper_emir_olay.c.emir_id).where(
                paper_emir_olay.c.emir_id.in_([e[0] for e in emirler]))).scalars()) if emirler else set()
            gun = int(b.execute(select(paper_karar.c.bar_ms).where(paper_karar.c.id == karar_id)).scalar())
        eksik = [e for e in emirler if e[0] not in olayli]
        if not eksik:
            return None
        islemler = self.kaynak.ist.islemler(self.ay.magic, gun - GUN_MS)
        out = {"kurtarilan": 0, "bulunamayan": 0}
        for eid, ist_id, kim, _ in eksik:
            p = next(x for x in self.ay.paralar if ONEK + x.para == kim)
            ds = [x for x in islemler if x["yorum"] == ist_id and x["sembol"] == p.sembol]
            if ds:
                self._dolum_yaz(eid, p, [{"lot": x["hacim"], "fiyat": x["fiyat"], "islem": x["bilet"]} for x in ds],
                                {"kurtarma": True})
                out["kurtarilan"] += 1
            else:
                self.defter.olay_yaz(eid, self.kol.ad, "ret", kim, 0.0, None, 0.0, int(self.saat() * 1000),
                                     {"gerekceler": ["yeniden başlatma: MT5'te işlem bulunamadı"]})
                out["bulunamayan"] += 1
        _log.warning("doviz_karar_devam", karar_id=karar_id, **out)
        return out

    # ------------------------------------------------------------------ yürütme
    def _yurut(self, d: DovizDurum, karar_id: int | None, zaman: int, hedef_para: dict[str, float],
               fiyat: dict[str, float], ham: dict[str, tuple[float, float, int]], onek: str,
               neden: str | None = None) -> dict:
        """hedef_para: yabancı para → hedef ağırlık (para uzayı, özkaynağa oran). Önce riski azaltanlar."""
        oz = d.ozkaynak(fiyat)
        iz, _ = izleyici(d.gecmis, self.kol.baslangic_ozkaynak, self.ay.risk)
        pf = Portfoy(oz, dict(d.adet), dict(fiyat), {k: SINIF for k in fiyat}, iz.durum,
                     {self.kol.ad} if d.durdurulmus else set())
        planlar = []
        for p in self.ay.paralar:
            if p.para not in hedef_para or p.sembol not in ham:
                continue
            kim = ONEK + p.para
            bid, ask, _ = ham[p.sembol]
            orta = (bid + ask) / 2
            mevcut = d.adet.get(kim, 0.0)
            hedef_q = hedef_para[p.para] * oz / fiyat[kim]
            lot = _adima(p.para_lot(hedef_q - mevcut, orta), self.ay.lot_adimi)
            if hedef_para[p.para] == 0.0:                           # tam kapanış: açık lotun tamamı
                lot = round(-d.lot.get(p.sembol, 0.0), 8)
            if lot == 0:
                continue
            q = p.lot_para(lot, orta)
            acik = d.lot.get(p.sembol, 0.0)
            planlar.append((abs(acik + lot) < abs(acik), p, kim, lot, q, orta))
        out = {"dolum": 0, "ret": []}
        for _, p, kim, lot, q, orta in sorted(planlar, key=lambda x: not x[0]):
            self._emir(karar_id, pf, p, kim, lot, q, orta, ham[p.sembol], zaman, onek, out, neden)
        return out

    def _emir(self, karar_id, pf: Portfoy, p: Para, kim: str, lot: float, q: float, orta: float,
              kot: tuple[float, float, int], zaman: int, onek: str, out: dict, neden: str | None) -> None:
        bid, ask, tik_ms = kot
        u = p.usd(orta)
        eid_ist = f"DV{onek}{zaman // SAAT_MS}-{p.para}"[:31]
        simdi = int(self.saat() * 1000)
        r = self.risk.onayla(EmirIstegi(kim, SINIF, q, u, self.kol.ad, simdi, eid_ist),
                             Piyasa(u, tik_ms, SAAT_MS, True), pf)
        onay_lot = _adima(p.para_lot(r.miktar, orta), self.ay.lot_adimi, asagi=True) if r.onay else 0.0
        if r.onay and r.risk_azaltan:
            onay_lot = lot
        risk = {"onay": r.onay, "gerekceler": list(r.gerekceler), "risk_azaltan": r.risk_azaltan, "lot": lot,
                "onay_lot": onay_lot}
        emir_id = self.defter.emir_yaz(self.kol.ad, karar_id, eid_ist, kim, q, p.lot_para(onay_lot, orta), u,
                                       "karar" if karar_id else (neden or "kapat"), risk, gonderim_fiyati=u)
        if not r.onay or onay_lot == 0:
            self.defter.olay_yaz(emir_id, self.kol.ad, "ret", kim, q, None, 0.0, simdi,
                                 {"gerekceler": list(r.gerekceler) or ["lot adımının altı"]})
            out["ret"].append({"para": p.para, "gerekce": list(r.gerekceler)})
            return
        try:
            cevap = self.kaynak.ist.emir(p.sembol, onay_lot, eid_ist, self.ay.magic)
        except Exception as e:  # noqa: BLE001 — ret olarak yazılır; yeniden denemez (çift emir riski)
            self.defter.olay_yaz(emir_id, self.kol.ad, "ret", kim, q, None, 0.0, simdi,
                                 {"gerekceler": [f"köprü: {type(e).__name__}: {e}"[:200]]})
            out["ret"].append({"para": p.para, "gerekce": [str(e)[:120]]})
            _log.error("doviz_emir_hatasi", para=p.para, hata=f"{type(e).__name__}: {e}"[:200])
            return
        tamam = [x for x in cevap["sonuc"] if x.get("retcode") in (10008, 10009, 10010) and x.get("hacim")]
        if not tamam:
            self.defter.olay_yaz(emir_id, self.kol.ad, "ret", kim, q, None, 0.0, simdi,
                                 {"gerekceler": [f"MT5 {x.get('retcode')} {x.get('yorum_mt5')}" for x in cevap["sonuc"]]})
            out["ret"].append({"para": p.para, "gerekce": ["MT5 reddetti"]})
            return
        dolumlar = [{"lot": math.copysign(x["hacim"], x["lot"]), "fiyat": x["fiyat"], "islem": x["islem"]}
                    for x in tamam]
        self._dolum_yaz(emir_id, p, dolumlar, {"bid": bid, "ask": ask, "orta": orta, "neden": neden,
                                               "sonuc": cevap["sonuc"]})
        pf.pozisyonlar[kim] = pf.pozisyonlar.get(kim, 0.0) + sum(p.lot_para(x["lot"], x["fiyat"]) for x in tamam)
        out["dolum"] += 1

    def _dolum_yaz(self, emir_id: int, p: Para, dolumlar: list[dict], ek: dict) -> None:
        """MT5 dolumları (çift, işaretli lot) → para uzayında tek dolum; fiyat kayma kadar aleyhe (kural 4).
        USDXXX çifti tamamen kapandıysa yabancı parada kalan bakiye (gerçekleşen kâr/zarar) orta fiyatla USD'ye çevrilir:
        aracı kurum da kapanışta böyle yapar."""
        q = sum(p.lot_para(x["lot"], x["fiyat"]) for x in dolumlar)
        deger = sum(p.lot_para(x["lot"], x["fiyat"]) * p.usd(x["fiyat"]) for x in dolumlar)
        if abs(q) < 1e-9:
            return
        u = deger / q
        k = self.ay.kayma_bps / 1e4
        u_def = u * (1 + k) if q > 0 else u * (1 - k)
        self.defter.olay_yaz(emir_id, self.kol.ad, "dolum", ONEK + p.para, q, u_def, 0.0, int(self.saat() * 1000),
                             {"sembol": p.sembol, "mt5": dolumlar, "usd_fiyat_mt5": u, "kayma_bps": self.ay.kayma_bps,
                              **ek})
        if not p.xxxusd:
            d = self._d()
            artik = d.adet.get(ONEK + p.para, 0.0)
            if d.lot.get(p.sembol, 0.0) == 0 and abs(artik) > 1e-9:
                self.defter.olay_yaz(emir_id, self.kol.ad, "dolum", ONEK + p.para, -artik, u, 0.0,
                                     int(self.saat() * 1000), {"sembol": p.sembol, "donusum": True, "mt5": []})


def _adima(x: float, adim: float, asagi: bool = False) -> float:
    """Lot adımına yuvarla (asagi: sıfıra doğru)."""
    n = math.floor(abs(x) / adim + 1e-9) if asagi else round(abs(x) / adim)
    return round(math.copysign(n * adim, x), 8) if n else 0.0


def calistir(sure_sn: float | None = None, dongu_sn: float = 60.0) -> None:
    """compose `doviz` servisi: her `dongu_sn`'de bir tur. Hata turu atlar (log), bir sonraki tur yeniden dener."""
    import os

    from tradebot.ayar import ayarlar as sistem
    from tradebot.db import motor as db_motor
    from tradebot.mt5.istemci import Mt5Istemci
    from tradebot.veri.depo import HamDepo
    from tradebot.veri.http import NazikIstemci

    ay = ayarlar()
    if ay is None:
        raise SystemExit("config/paper.yaml içinde `doviz` bloğu yok")
    a = sistem()
    if not a.mt5_kopru_forex:
        raise SystemExit("TRADEBOT_MT5_KOPRU_FOREX tanımlı değil")
    m = db_motor(a)
    defter = PaperDefter(m, os.environ.get("TRADEBOT_KOD_SURUMU", "yerel"))
    http = NazikIstemci("oecd", zaman_asimi=120)
    kaynak = Kaynak(Mt5Istemci(a.mt5_kopru_forex), lambda: http.al(fz.URL.format(ulkeler="+".join(fz.ULKELER))),
                    HamDepo(a.veri_dizini, m))
    dugum = DovizDugumu(defter, ay, kaynak)
    dugum.ac()
    bas = time.monotonic()
    while sure_sn is None or time.monotonic() - bas < sure_sn:
        try:
            r = dugum.tur()
            if r:
                _log.info("doviz_tur", **{k: v for k, v in r.items() if k != "isaret"}, isaret=r.get("isaret"))
        except Exception as e:  # noqa: BLE001
            _log.error("doviz_tur_hatasi", hata=f"{type(e).__name__}: {e}"[:300])
        time.sleep(dongu_sn)
