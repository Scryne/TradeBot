"""Altın M15 scalping kolu — MT5 demo düğümü (EA tarzı gün içi XAUUSD; ileriye dönük GÖZLEM kolu). Compose `altin`.

Scryne (2026-09-30): videolardaki gibi XAUUSD'de sürekli al-sat. Kanıt bir kez gösterildi (Altın M15 turnuvası: altı
aile de maliyet sonrası eksi; videodaki "katlama" ~200–850x kaldıraç + pozisyon yığma, kural 6 gereği hiçbir modda
yok); Scryne kurallar içinde demo kolunu seçti. Strateji turnuvada test edilen `kanal_kirilim` (n = 48, stop 2 ATR,
hedef 2R, en uzun 192 bar, günlük ±3R, 3 ardışık kayıpta gün kilidi; en iyi varyant): günde birkaç işlem. Beklenen
getirisi negatiftir (turnuvada Sharpe −0,18); kol bir kazanç iddiası değil, EA yaklaşımının ileriye dönük ölçümüdür.

Akış (her tur ~20 sn):
- Her M15 bar kapanışından sonra: NCM `GOLD` M15 barları (yalnız kapanmış; sabit çapadan, yol belirlenimci) →
  turnuvanın AYNI fonksiyonu (`cekirdek.altin.kanal_kirilim`, kural 3) → hedef pozisyon ∈ {−1, 0, +1} × `lot` → karar
  emirden ÖNCE deftere → risk motoru (kural 5) → MT5 demo piyasa emri → gerçek dolum deftere.
- Saat başı: finansman tahakkuku + orta fiyatla özkaynak işareti (kalp atışı) + MT5 mutabakatı. Kol durdurulduysa ya da
  acil durdurma eşiği aşıldıysa pozisyon hemen kapanır; fren (günlük −%3, haftalık −%8) yeni risk açtırmaz.

Boyut: backtest oynaklık hedefliydi (%20, 3x). 10.000 USD demo hesapta altının en küçük birimi (0,01 lot = 1 ons
≈ 4.600 USD) risk motorunun enstrüman tavanının (özkaynağın %50'si) sınırında: kol sabit 0,01 lot işlem yapar. Sinyal
ve zamanlama backtest'le aynı, ölçek farklı. Döviz koluyla aynı demo hesabı paylaşır (sihirli sayı ayrı; defterler
ayrı; hesap brütü ~1,5x, sabit 3x tavanın altında).

Maliyet (aleyhte, kural 4): MT5 dolum fiyatı `kayma_bps` kadar aleyhe kaydırılarak deftere yazılır; finansman backtest
modeliyle (CFD metal, yıllık %4 brüt maruziyet üzerinden) saatlik tahakkuk eder.

Bilinen boşluk (v1): stop ve hedef backtest gibi bar kapanışında denetlenir; aracı kurumda sunucu tarafı stop yok.
Düğüm donarsa pozisyon açık kalır; bekçi kalp atışıyla bildirir. Demo hesap: kayıp sanal.
"""
from __future__ import annotations

import math
import time
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from sqlalchemy import insert, select
from sqlalchemy.engine import Engine

from tradebot import denetim
from tradebot.arastirma.panel import riski_artirma
from tradebot.arastirma.turnuva import STRATEJILER, Ayar
from tradebot.canli.defter import PaperDefter
from tradebot.canli.karar import KolDurum
from tradebot.canli.kilit import izleyici
from tradebot.canli.kollar import PaperKol, oku
from tradebot.cekirdek.temel import Barlar
from tradebot.db import paper_emir, paper_emir_olay, paper_karar, paper_ozkaynak
from tradebot.kayit import log
from tradebot.risk.motor import Durum, EmirIstegi, Piyasa, Portfoy, RiskAyar, RiskMotoru

DUGUM = "altin"
SINIF = "metal"
BAR_MS = 900_000
SAAT_MS = 3_600_000
GUN_MS = 86_400_000
YIL_MS = 365.25 * GUN_MS
KARAR_GECIKME_MS = 20_000              # bar kapanışından sonra (köprü yalnız kapanmış barı verir)
CAPA_GUN = 30                          # yol çapası: kol başlangıcından 30 gün önce (ATR/kanal ısınması)
_log = log("altin")


@dataclass(frozen=True)
class AltinAyarlari:
    kol: PaperKol
    sembol: str
    kimlik: str
    strateji: str
    parametre: dict
    lot: float
    ons_lot: float
    risk: RiskAyar
    kayma_bps: float
    finansman_yillik: float
    magic: int


def ayarlar(d: dict | None = None) -> AltinAyarlari | None:
    """`config/paper.yaml` `altin` bloğu. Blok yoksa None (düğüm çalışmaz)."""
    d = d or oku()
    b = d.get("altin")
    if not b:
        return None
    risk = RiskAyar(kaldirac=float(b["risk"]["kaldirac"]))
    ayar = Ayar(hedef_vol=0.0, kaldirac=risk.kaldirac, vol_pencere_gun=0, frenler=bool(d.get("frenler", True)), bant=0.0)
    kimlik = f"NCMFX:{b['sembol']}"
    grup = {"dugum": DUGUM, "yon": "long_short", "kimlikler": [kimlik], "sembol": b["sembol"], "lot": b["lot"],
            "maliyet": b["maliyet"], "hesap": "NCM forex demo", "zd": "15m"}
    kol = PaperKol(b["ad"], b["strateji"], "xau_m15", grup, "15m", ayar, dict(b["parametre"]), b.get("sinif", "B"),
                   float(b.get("baslangic_ozkaynak", 10_000)))
    return AltinAyarlari(kol, b["sembol"], kimlik, b["strateji"], dict(b["parametre"]), float(b["lot"]),
                         float(b.get("ons_lot", 100.0)), risk, float(b["maliyet"]["kayma_bps"]),
                         float(b["maliyet"]["finansman_yillik"]), int(b["magic"]))


def hedef_pozisyon(ay: AltinAyarlari, b: Barlar) -> float:
    """Son kapanmış barda turnuva fonksiyonunun pozisyonu ∈ {−1, 0, 1}."""
    _, fonk, _ = STRATEJILER[ay.strateji]
    return float(np.sign(fonk(b, **ay.parametre)[-1]))


def barlar_df(df) -> Barlar:
    return Barlar(df["acilis_ms"].to_numpy().astype(np.int64), *(df[c].to_numpy().astype(float)
                                                                  for c in ("open", "high", "low", "close")),
                  df["tick_volume"].to_numpy().astype(float))


@dataclass
class AltinDurum:
    nakit: float
    adet: float                          # ons (işaretli)
    lot: float                           # MT5 net lot (dolumlardan)
    gecmis: list[tuple[int, float]]
    son_fonlama: int
    durdurulmus: bool
    son_karar_bar: int
    son_fiyat: float

    def ozkaynak(self, fiyat: float | None) -> float:
        return self.nakit + self.adet * (fiyat if fiyat else self.son_fiyat)


def durum_kur(defter: PaperDefter, ay: AltinAyarlari) -> AltinDurum:
    kol = ay.kol.ad
    with defter.motor.connect() as b:
        olay = list(b.execute(select(paper_emir_olay.c.tur, paper_emir_olay.c.miktar, paper_emir_olay.c.fiyat,
                                     paper_emir_olay.c.ucret, paper_emir_olay.c.ayrinti)
                              .where(paper_emir_olay.c.kol == kol, paper_emir_olay.c.tur.in_(("dolum", "fonlama")))
                              .order_by(paper_emir_olay.c.id)))
        isaret = list(b.execute(select(paper_ozkaynak.c.zaman_ms, paper_ozkaynak.c.ozkaynak, paper_ozkaynak.c.fiyat)
                                .where(paper_ozkaynak.c.kol == kol).order_by(paper_ozkaynak.c.zaman_ms)))
        son_karar = b.execute(select(paper_karar.c.bar_ms).where(paper_karar.c.kol == kol)
                              .order_by(paper_karar.c.bar_ms.desc()).limit(1)).scalar()
    nakit, adet, lot, son_fon, son_px = ay.kol.baslangic_ozkaynak, 0.0, 0.0, 0, 0.0
    for tur, q, p, u, a in olay:
        a = a or {}
        if tur == "fonlama":
            nakit -= u
            son_fon = max(son_fon, int(a.get("bit_ms", 0)))
            continue
        adet += q
        nakit -= q * p + u
        lot += sum(float(x["lot"]) for x in a.get("mt5", []))
        son_px = p
    if isaret and isaret[-1][2]:
        son_px = float(isaret[-1][2].get(ay.kimlik, son_px))
    son_elle = None
    for o in defter.kol_olaylari(kol):
        if o.tur == "devam" or (o.tur == "durdur" and o.ayrinti.get("neden") != "mutabakat"):
            son_elle = o.tur
    return AltinDurum(nakit, adet if abs(adet) > 1e-9 else 0.0, round(lot, 8), [(int(t), float(o)) for t, o, _ in isaret],
                      son_fon, son_elle == "durdur", int(son_karar or 0), son_px)


class AltinDugumu:
    def __init__(self, defter: PaperDefter, ay: AltinAyarlari, ist, saat: Callable[[], float] = time.time):
        self.defter, self.ay, self.ist, self.saat = defter, ay, ist, saat
        self.m: Engine = defter.motor
        self.kol = ay.kol
        self.risk = RiskMotoru(ay.risk)
        self._denenen = 0                  # veri çekilmiş son bar (hafta sonu her turda köprüyü yormasın)
        self._kurtarildi = False

    def ac(self) -> None:
        if self.defter.kol_ac(self.kol, int(self.saat() * 1000)):
            _log.info("kol_acildi", kol=self.kol.ad)

    def _d(self) -> AltinDurum:
        return durum_kur(self.defter, self.ay)

    def _capa(self) -> int:
        b = self.defter.kol_baslangic(self.kol.ad) or int(self.saat() * 1000)
        return (b - CAPA_GUN * GUN_MS) // GUN_MS * GUN_MS

    def _kotasyon(self) -> tuple[float, float, int] | None:
        q = self.ist.kotasyon([self.ay.sembol])["kotasyon"].get(self.ay.sembol)
        if not q or q["bid"] <= 0 or q["ask"] <= 0:
            return None
        return q["bid"], q["ask"], int(q["tik_ms"])

    # ------------------------------------------------------------------ tur
    def tur(self) -> dict:
        simdi = int(self.saat() * 1000)
        d = self._d()
        out: dict = {}
        saat_bas = simdi // SAAT_MS * SAAT_MS
        if not d.gecmis or d.gecmis[-1][0] < saat_bas:
            out["isaret"] = self._saatlik(d, saat_bas)
            d = self._d()
        if not self._kurtarildi:
            k = self._kurtar()
            self._kurtarildi = True
            if k:
                out["kurtarma"] = k
                d = self._d()
        bar = simdi // BAR_MS * BAR_MS - BAR_MS            # son kapanmış barın açılışı
        if bar > max(d.son_karar_bar, self._denenen) and simdi - (bar + BAR_MS) >= KARAR_GECIKME_MS:
            k = self._karar(d, bar, simdi)
            if k:
                out["karar"] = k
        return out

    # ------------------------------------------------------------------ saatlik
    def _saatlik(self, d: AltinDurum, saat_bas: int) -> dict:
        kot = self._kotasyon()
        px = (kot[0] + kot[1]) / 2 if kot else d.son_fiyat
        fon = 0.0
        if d.adet and d.gecmis and px:
            bas = max(d.son_fonlama, d.gecmis[-1][0])
            if saat_bas > bas:
                v = d.adet * px
                fon = abs(v) * self.ay.finansman_yillik * (saat_bas - bas) / YIL_MS
                self.defter.olay_yaz(0, self.kol.ad, "fonlama", self.ay.kimlik, 0.0, px, fon, saat_bas,
                                     {"bas_ms": bas, "bit_ms": saat_bas, "deger_usd": v,
                                      "finansman_yillik": self.ay.finansman_yillik})
                d = self._d()
        oz = d.ozkaynak(px)
        adet = {self.ay.kimlik: d.adet} if d.adet else {}
        self.defter.ozkaynak_yaz(self.kol.ad, saat_bas, KolDurum(oz, d.nakit, adet), {self.ay.kimlik: px})
        _, gecis = izleyici(d.gecmis + [(saat_bas, oz)], self.kol.baslangic_ozkaynak, self.ay.risk)
        neden = "durdur" if d.durdurulmus else ("acil_durdurma" if gecis == Durum.ACIL_DURDURMA else None)
        kapat = None
        if neden and d.lot and kot:
            kapat = self._yurut(d, None, saat_bas, 0.0, kot, "K", neden)
            if neden == "acil_durdurma":
                denetim.kaydet(self.m, "altin", "acil_durdurma_kapatma", {"kol": self.kol.ad, "ozkaynak": oz})
        return {"ozkaynak": round(oz, 2), "fonlama": round(-fon, 4), "mutabakat": self._mutabakat(d),
                **({"kapatilan": kapat} if kapat else {})}

    def _mutabakat(self, d: AltinDurum) -> dict:
        try:
            mt5 = sum(float(x["hacim"]) for x in self.ist.pozisyonlar(self.ay.magic) if x["sembol"] == self.ay.sembol)
        except Exception as e:  # noqa: BLE001
            return {"hata": f"{type(e).__name__}: {e}"[:120]}
        if abs(mt5 - d.lot) > 0.005:
            _log.error("altin_mutabakat_farki", defter=d.lot, mt5=round(mt5, 2))
            return {"fark": {"defter": d.lot, "mt5": round(mt5, 2)}}
        return {"tamam": True}

    # ------------------------------------------------------------------ karar
    def _karar(self, d: AltinDurum, bar: int, simdi: int) -> dict | None:
        df = self.ist.mumlar(self.ay.sembol, "M15", self._capa(), bar + BAR_MS)
        self._denenen = bar
        if df.is_empty() or int(df["acilis_ms"][-1]) != bar:
            return None                                   # piyasa kapalı ya da bar henüz yok: karar yazılmaz
        b = barlar_df(df)
        poz = hedef_pozisyon(self.ay, b)
        iz, _ = izleyici(d.gecmis, self.kol.baslangic_ozkaynak, self.ay.risk)
        durum = iz.durum.value
        hedef = 0.0 if d.durdurulmus or durum == "acil_durdurma" else poz * self.ay.lot
        if durum not in ("normal", "acil_durdurma"):
            hedef = float(riski_artirma(np.array([hedef]), np.array([d.lot]))[0])
        ayr = {"tur": self.ay.strateji, "kimlikler": [self.ay.kimlik], "poz": poz, "hedef_lot": hedef, "lot_once": d.lot,
               "bar_sayisi": len(b), "capa_ms": self._capa(), "kapanis": float(b.close[-1])}
        with self.m.begin() as c:
            kid = int(c.execute(insert(paper_karar).values(
                kol=self.kol.ad, bar_ms=bar, karar_ms=simdi, kod_surumu=self.defter.kod,
                veri_hash=f"{bar}:{len(b)}:{float(b.close[-1])}"[:64], durum=durum, ayrinti=ayr)).inserted_primary_key[0])
        if abs(hedef - d.lot) < 1e-9:
            return {"karar_id": kid, "poz": poz, "islem": False}
        kot = self._kotasyon()
        if kot is None:
            return {"karar_id": kid, "poz": poz, "islem": False, "hata": "kotasyon yok"}
        sonuc = self._yurut(d, kid, bar, hedef, kot, "D")
        _log.info("altin_karar", bar=bar, poz=poz, hedef_lot=hedef, lot_once=d.lot, **sonuc)
        return {"karar_id": kid, "poz": poz, "islem": True, **sonuc}

    def _kurtar(self) -> dict | None:
        """Başlangıçta: emri yazılmış ama olayı olmayan emirler (süreç emirle dolum kaydı arasında durdu) MT5 işlem
        geçmişinde aynı yorumla aranır; bulunursa dolum deftere yazılır (çift emir gönderilmez), bulunmazsa ret."""
        with self.m.connect() as b:
            emirler = list(b.execute(select(paper_emir.c.id, paper_emir.c.istemci_emir_id, paper_emir.c.zaman_ms)
                                     .where(paper_emir.c.kol == self.kol.ad)))
            olayli = set(b.execute(select(paper_emir_olay.c.emir_id).where(
                paper_emir_olay.c.kol == self.kol.ad)).scalars())
        eksik = [e for e in emirler if e[0] not in olayli]
        if not eksik:
            return None
        simdi = int(self.saat() * 1000)
        islemler = self.ist.islemler(self.ay.magic, simdi - 7 * GUN_MS)
        out = {"kurtarilan": 0, "bulunamayan": 0}
        for eid, ist_id, _ in eksik:
            ds = [x for x in islemler if x["yorum"] == ist_id and x["sembol"] == self.ay.sembol]
            if not ds:
                self.defter.olay_yaz(eid, self.kol.ad, "ret", self.ay.kimlik, 0.0, None, 0.0, simdi,
                                     {"gerekceler": ["yeniden başlatma: MT5'te işlem bulunamadı"]})
                out["bulunamayan"] += 1
                continue
            dolumlar = [{"lot": float(x["hacim"]), "fiyat": float(x["fiyat"]), "islem": x["bilet"]} for x in ds]
            q = sum(x["lot"] for x in dolumlar) * self.ay.ons_lot
            px = sum(x["lot"] * x["fiyat"] for x in dolumlar) * self.ay.ons_lot / q
            k = self.ay.kayma_bps / 1e4
            self.defter.olay_yaz(eid, self.kol.ad, "dolum", self.ay.kimlik, q, px * (1 + k if q > 0 else 1 - k), 0.0,
                                 simdi, {"sembol": self.ay.sembol, "mt5": dolumlar, "fiyat_mt5": px, "kurtarma": True})
            out["kurtarilan"] += 1
        _log.warning("altin_kurtarma", **out)
        return out

    # ------------------------------------------------------------------ yürütme
    def _yurut(self, d: AltinDurum, karar_id: int | None, zaman: int, hedef_lot: float,
               kot: tuple[float, float, int], onek: str, neden: str | None = None) -> dict:
        """Hedefe ulaşmak için gereken lot. Ters yöne geçişte önce kapatma, sonra açılış (iki emir; ilki riski azaltır)."""
        bid, ask, tik_ms = kot
        orta = (bid + ask) / 2
        adimlar = []
        if d.lot and (hedef_lot == 0 or math.copysign(1, hedef_lot) != math.copysign(1, d.lot)):
            adimlar.append(-d.lot)
            if hedef_lot:
                adimlar.append(hedef_lot)
        else:
            adimlar.append(round(hedef_lot - d.lot, 8))
        oz = d.ozkaynak(orta)
        iz, _ = izleyici(d.gecmis, self.kol.baslangic_ozkaynak, self.ay.risk)
        pf = Portfoy(oz, {self.ay.kimlik: d.adet} if d.adet else {}, {self.ay.kimlik: orta},
                     {self.ay.kimlik: SINIF}, iz.durum, {self.kol.ad} if d.durdurulmus else set())
        out = {"dolum": 0, "ret": []}
        for i, lot in enumerate(adimlar):
            if abs(lot) < 1e-9:
                continue
            q = lot * self.ay.ons_lot
            eid = f"AL{onek}{zaman // BAR_MS}-{i}"[:31]
            simdi = int(self.saat() * 1000)
            r = self.risk.onayla(EmirIstegi(self.ay.kimlik, SINIF, q, orta, self.kol.ad, simdi, eid),
                                 Piyasa(orta, tik_ms, SAAT_MS, True), pf)
            onay_lot = lot if (r.onay and r.risk_azaltan) else (
                _adima(r.miktar / self.ay.ons_lot, 0.01) if r.onay else 0.0)
            risk = {"onay": r.onay, "gerekceler": list(r.gerekceler), "risk_azaltan": r.risk_azaltan, "lot": lot,
                    "onay_lot": onay_lot}
            emir_id = self.defter.emir_yaz(self.kol.ad, karar_id, eid, self.ay.kimlik, q, onay_lot * self.ay.ons_lot,
                                           orta, "karar" if karar_id else (neden or "kapat"), risk, gonderim_fiyati=orta)
            if not r.onay or onay_lot == 0:
                self.defter.olay_yaz(emir_id, self.kol.ad, "ret", self.ay.kimlik, q, None, 0.0, simdi,
                                     {"gerekceler": list(r.gerekceler) or ["lot adımının altı"]})
                out["ret"].append(list(r.gerekceler))
                break
            try:
                cevap = self.ist.emir(self.ay.sembol, onay_lot, eid, self.ay.magic)
            except Exception as e:  # noqa: BLE001
                self.defter.olay_yaz(emir_id, self.kol.ad, "ret", self.ay.kimlik, q, None, 0.0, simdi,
                                     {"gerekceler": [f"köprü: {type(e).__name__}: {e}"[:200]]})
                out["ret"].append([str(e)[:120]])
                _log.error("altin_emir_hatasi", hata=f"{type(e).__name__}: {e}"[:200])
                break
            tamam = [x for x in cevap["sonuc"] if x.get("retcode") in (10008, 10009, 10010) and x.get("hacim")]
            if not tamam:
                self.defter.olay_yaz(emir_id, self.kol.ad, "ret", self.ay.kimlik, q, None, 0.0, simdi,
                                     {"gerekceler": [f"MT5 {x.get('retcode')} {x.get('yorum_mt5')}" for x in cevap["sonuc"]]})
                out["ret"].append(["MT5 reddetti"])
                break
            dolumlar = [{"lot": math.copysign(x["hacim"], x["lot"]), "fiyat": x["fiyat"], "islem": x["islem"]}
                        for x in tamam]
            q_f = sum(x["lot"] for x in dolumlar) * self.ay.ons_lot
            px = sum(x["lot"] * x["fiyat"] for x in dolumlar) * self.ay.ons_lot / q_f
            k = self.ay.kayma_bps / 1e4
            self.defter.olay_yaz(emir_id, self.kol.ad, "dolum", self.ay.kimlik, q_f, px * (1 + k if q_f > 0 else 1 - k),
                                 0.0, int(self.saat() * 1000),
                                 {"sembol": self.ay.sembol, "mt5": dolumlar, "fiyat_mt5": px, "bid": bid, "ask": ask,
                                  "kayma_bps": self.ay.kayma_bps, "neden": neden})
            pf.pozisyonlar[self.ay.kimlik] = pf.pozisyonlar.get(self.ay.kimlik, 0.0) + q_f
            out["dolum"] += 1
        return out


def _adima(x: float, adim: float) -> float:
    n = math.floor(abs(x) / adim + 1e-9)
    return round(math.copysign(n * adim, x), 8) if n else 0.0


def calistir(sure_sn: float | None = None, dongu_sn: float = 20.0) -> None:
    """compose `altin` servisi."""
    import os

    from tradebot.ayar import ayarlar as sistem
    from tradebot.db import motor as db_motor
    from tradebot.mt5.istemci import Mt5Istemci

    ay = ayarlar()
    if ay is None:
        raise SystemExit("config/paper.yaml içinde `altin` bloğu yok")
    a = sistem()
    if not a.mt5_kopru_forex:
        raise SystemExit("TRADEBOT_MT5_KOPRU_FOREX tanımlı değil")
    defter = PaperDefter(db_motor(a), os.environ.get("TRADEBOT_KOD_SURUMU", "yerel"))
    dugum = AltinDugumu(defter, ay, Mt5Istemci(a.mt5_kopru_forex))
    dugum.ac()
    bas = time.monotonic()
    while sure_sn is None or time.monotonic() - bas < sure_sn:
        try:
            r = dugum.tur()
            if r:
                _log.info("altin_tur", **{k: v for k, v in r.items() if k != "isaret"}, isaret=r.get("isaret"))
        except Exception as e:  # noqa: BLE001
            _log.error("altin_tur_hatasi", hata=f"{type(e).__name__}: {e}"[:300])
        time.sleep(dongu_sn)
