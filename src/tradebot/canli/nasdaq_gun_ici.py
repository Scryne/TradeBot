"""Nasdaq gün içi paper düğümü (dalga 20; QQQ). Nautilus dışı ayrı süreç (compose `nasdaq-gun-ici`), ~20 sn'de bir tur.

Akış (yalnız XNYS seansında işlem; gece pozisyon yok):
- **Sinyal:** QQQ'nun 1 dk barlarından (Yahoo, son 5 gün) UTC saat sınırlarında saatlik barlar kurulur ve backtest'in
  AYNI fonksiyonu (`gun_ici.gun_ici_ivme`) çağrılır (kural 3). Son kapanmış saatlik barın kararı pozitifse/negatifse
  sonraki saat o yönde tutulur. Saatlik barın kapanışı: o saatin son dakikasının kapanışı.
- **Boyut:** ağırlık = min(1, hedef_vol / σ), σ son `vol_pencere_gun` günün günlük getirilerinden yıllık (canlıda saatlik
  CFD serisi yok: aynı hedefin günlük tahmini; gözlem kolu farkı belgelenir). Brüt ≤ 1x (nakit hesap).
- **Giriş:** kararın verildiği saat sınırından sonra (ör. 15:00:20 NY) piyasa emri; **çıkış:** 15:59 NY'de bütün pozisyon
  (16:00 kapanışında normal seans biter; Alpaca'da seans sonrası yalnız limit emir). Seans 16:00'dan önce bitiyorsa (yarım
  gün) kol o gün işlem yapmaz: backtest'te de XNYS maskesi pozisyonu kapatır.
- **Yürütme:** Alpaca PAPER (anahtar varsa) piyasa `day` emri, dolum Alpaca'dan + `EK_KAYMA` aleyhte; yoksa iç simülasyon
  (Yahoo son fiyatı ± maliyet modeli `ABD:qqq_gun_ici`, taraf başı 2 bps). Günlük düğümün Alpaca'ya giden kolu varken
  Alpaca yasak (tek hesap, mutabakat çakışması); ayrı hesap gelirse ayrı anahtarla açılır.
- **İşaret** (saat başı; kalp atışı), elle/acil durdurmada hemen kapatma (kural 7), risk motoru (kural 5).
"""
from __future__ import annotations

import json
import math
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np

from tradebot import denetim
from tradebot.arastirma.maliyet import MODELLER, MaliyetModeli
from tradebot.arastirma.turnuva import STRATEJILER, Ayar
from tradebot.canli.defter import PaperDefter
from tradebot.canli.kollar import PaperKol, oku
from tradebot.canli.nasdaq import EK_KAYMA, Seans, duzenleyici_ucret, seanslar, sembol
from tradebot.cekirdek import Barlar, StratejiTanimi
from tradebot.cekirdek.boyut import kaldirac_dogrula
from tradebot.kayit import log
from tradebot.risk.motor import Durum, EmirIstegi, Piyasa, Portfoy, RiskAyar, RiskMotoru

DUGUM = "nasdaq_gun_ici"
SINIF = "etf"
KIMLIK = "ARCA:QQQ"
SAAT_MS = 3_600_000
DAKIKA_MS = 60_000
GUN_MS = 86_400_000
GIRIS_GECIKME_MS = 20_000          # saat sınırından sonra: son dakikanın barı oluşsun
CIKIS_ONCE_MS = 1 * DAKIKA_MS      # kapanıştan 1 dk önce çıkış
ADET_ADIMI = 0.0001
_log = log("nasdaq_gun_ici")


@dataclass(frozen=True)
class GunIciAyarlari:
    kol: PaperKol
    parametre: dict
    hedef_vol: float
    vol_pencere_gun: int
    risk: RiskAyar
    maliyet: MaliyetModeli
    yurutme: str


def ayarlar(d: dict | None = None) -> GunIciAyarlari | None:
    d = d or oku()
    b = d.get("nasdaq_gun_ici")
    if not b or not b.get("ad"):
        return None
    if b["strateji"] not in STRATEJILER:
        raise ValueError(f"bilinmeyen strateji: {b['strateji']}")
    bo = b["boyut"]
    kaldirac = kaldirac_dogrula(float(bo["kaldirac"]))
    if kaldirac > 1.0:
        raise ValueError("gün içi nakit kolu: brüt ≤ 1x")
    # Tek Alpaca paper hesabı: günlük düğümün mutabakatı yalnız kendi kollarını sayar, burada tutulan QQQ'yu fark görüp
    # günlük kolları durdurur (2026-10-19). Günlük düğümde Alpaca'ya giden kol varken bu kol iç simülasyonda olmalı.
    gunluk = d.get("nasdaq") or {}
    if b.get("yurutme", "otomatik") != "ic" and any(
            k.get("yurutme", gunluk.get("yurutme", "otomatik")) != "ic" for k in gunluk.get("kollar") or []):
        raise ValueError("gün içi kolu Alpaca hesabını günlük kollarla paylaşamaz: `yurutme: ic` gerekir")
    ayar = Ayar(hedef_vol=float(bo["hedef_vol"]), kaldirac=kaldirac, vol_pencere_gun=int(bo["vol_pencere_gun"]),
                frenler=bool(d.get("frenler", True)), bant=0.0)
    grup = {"dugum": DUGUM, "yon": "long_short" if b["parametre"].get("kisa") else "long", "kimlikler": [KIMLIK],
            "hesap": "Alpaca paper" if b.get("yurutme") != "ic" else "iç simülasyon", "veri": "Yahoo QQQ 1 dk"}
    kol = PaperKol(b["ad"], b["strateji"], "qqq", grup, "1h", ayar, dict(b["parametre"]), b.get("sinif", "B"),
                   float(b.get("baslangic_ozkaynak", 100_000)))
    return GunIciAyarlari(kol, dict(b["parametre"]), ayar.hedef_vol, ayar.vol_pencere_gun, RiskAyar(kaldirac=kaldirac),
                          MODELLER["ABD:qqq_gun_ici"], b.get("yurutme", "otomatik"))


# ---------------------------------------------------------------------------------------------------- saf yardımcılar
def saatlik(t_dk: np.ndarray, o: np.ndarray, h: np.ndarray, lo: np.ndarray, c: np.ndarray, simdi_ms: int) -> Barlar:
    """1 dk barları (açılış zamanlı) → UTC saat sınırlı saatlik barlar; yalnız TAMAMEN kapanmış saatler."""
    t = np.asarray(t_dk, dtype=np.int64)
    ok = np.isfinite(c) & np.isfinite(o)
    t, o, h, lo, c = t[ok], o[ok], h[ok], lo[ok], c[ok]
    kova = t // SAAT_MS * SAAT_MS
    tamam = kova + SAAT_MS <= simdi_ms
    t, o, h, lo, c, kova = t[tamam], o[tamam], h[tamam], lo[tamam], c[tamam], kova[tamam]
    if len(t) == 0:
        return Barlar(*(np.zeros(0) for _ in range(6)))
    u, bas = np.unique(kova, return_index=True)
    son = np.r_[bas[1:], len(t)] - 1
    return Barlar(u.astype(np.int64), o[bas], np.maximum.reduceat(h, bas), np.minimum.reduceat(lo, bas), c[son],
                  np.ones(len(u)))


def agirlik(gunluk_kapanis: np.ndarray, hedef_vol: float, pencere: int, azami: float) -> float:
    """min(azami, hedef / σ_yıllık); σ son `pencere` günlük log getiriden (tanımsızsa 0: bilinmeyen = nakit)."""
    c = np.asarray(gunluk_kapanis, dtype=float)
    c = c[np.isfinite(c) & (c > 0)]
    if len(c) < pencere + 1:
        return 0.0
    r = np.diff(np.log(c[-(pencere + 1):]))
    s = float(r.std(ddof=1)) * math.sqrt(252)
    return float(min(azami, hedef_vol / s)) if s > 0 else 0.0


# ---------------------------------------------------------------------------------------------------- dış dünya
class Kaynak:
    """QQQ 1 dk barları ve son fiyat (Yahoo); günlük kapanışlar (Yahoo)."""

    def __init__(self, yahoo_al: Callable[[str, dict], bytes]) -> None:
        self._al = yahoo_al

    def _chart(self, aralik: str, menzil: str) -> dict:
        return json.loads(self._al(f"https://query1.finance.yahoo.com/v8/finance/chart/{sembol(KIMLIK)}",
                                   {"interval": aralik, "range": menzil}))["chart"]["result"][0]

    def dakikalik(self) -> tuple[np.ndarray, ...]:
        d = self._chart("1m", "5d")
        q = d["indicators"]["quote"][0]
        f = lambda k: np.array([np.nan if x is None else float(x) for x in q[k]])  # noqa: E731
        return np.array(d["timestamp"], dtype=np.int64) * 1000, f("open"), f("high"), f("low"), f("close")

    def gunluk_kapanis(self) -> np.ndarray:
        d = self._chart("1d", "6mo")
        return np.array([np.nan if x is None else float(x) for x in d["indicators"]["quote"][0]["close"]])

    def son_fiyat(self) -> float:
        return float(self._chart("1m", "1d")["meta"]["regularMarketPrice"])


# ---------------------------------------------------------------------------------------------------- düğüm
class GunIciDugumu:
    def __init__(self, defter: PaperDefter, ay: GunIciAyarlari, kaynak: Kaynak, alpaca=None,
                 saat: Callable[[], float] = time.time) -> None:
        self.defter, self.ay, self.kaynak, self.saat = defter, ay, kaynak, saat
        self.alpaca = alpaca if ay.yurutme in ("alpaca", "otomatik") else None
        if ay.yurutme == "alpaca" and self.alpaca is None:
            raise RuntimeError("yurutme: alpaca ama Alpaca paper anahtarı yok")
        self.kol = ay.kol
        self.risk = RiskMotoru(ay.risk)
        _, fonk, _ = STRATEJILER[ay.kol.strateji]
        self.tanim = StratejiTanimi(ay.kol.strateji, STRATEJILER[ay.kol.strateji][0], fonk, ay.parametre,
                                    yon=ay.kol.yon)
        self._son_isaret = 0

    @property
    def mod(self) -> str:
        return "alpaca" if self.alpaca is not None else "ic"

    def ac(self) -> None:
        if self.defter.kol_ac(self.kol, int(self.saat() * 1000)):
            _log.info("kol_acildi", kol=self.kol.ad, yurutme=self.mod)

    def _durduruldu(self) -> bool:
        son = None
        for o in self.defter.kol_olaylari(self.kol.ad):
            if o.tur in ("durdur", "devam"):
                son = o.tur
        return son == "durdur"

    # ------------------------------------------------------------------ tur
    def tur(self) -> dict:
        simdi = int(self.saat() * 1000)
        ss = seanslar(simdi - 2 * GUN_MS, simdi + 2 * GUN_MS)
        bugun = next((s for s in ss if s.acilis_ms <= simdi < s.kapanis_ms), None)
        out: dict = {}
        d = self.defter.durum(self.kol)
        adet = d.adet.get(KIMLIK, 0.0)
        if adet and (bugun is None or simdi >= bugun.kapanis_ms - CIKIS_ONCE_MS or self._durduruldu()
                     or (d.izleyici is not None and d.izleyici.durum == Durum.ACIL_DURDURMA)):
            out["cikis"] = self._emir(d, -adet, simdi, "cikis" if not self._durduruldu() else "durdur", bugun)
        elif bugun is not None and simdi % SAAT_MS >= GIRIS_GECIKME_MS:
            karar_bar = simdi // SAAT_MS * SAAT_MS - SAAT_MS     # son kapanmış saatlik barın açılışı
            if not self.defter.karar_var(self.kol.ad, karar_bar) and simdi < bugun.kapanis_ms - 5 * DAKIKA_MS:
                out["karar"] = self._karar(d, karar_bar, simdi, bugun)
        if simdi - simdi % SAAT_MS > self._son_isaret:
            out["isaret"] = self._isaretle(simdi)
            self._son_isaret = simdi - simdi % SAAT_MS
        return out

    def _karar(self, d, karar_bar: int, simdi: int, s: Seans) -> dict:
        from sqlalchemy import insert

        from tradebot.db import paper_karar

        t, o, h, lo, c = self.kaynak.dakikalik()
        b = saatlik(t, o, h, lo, c, simdi)
        if len(b) == 0 or int(b.t[-1]) != karar_bar:
            return {"bekle": "saatlik bar yok"}
        sinyal = float(self.tanim.sinyal(b)[-1])
        w = agirlik(self.kaynak.gunluk_kapanis(), self.ay.hedef_vol, self.ay.vol_pencere_gun, self.ay.risk.kaldirac)
        hedef = sinyal * w if not self._durduruldu() else 0.0
        fiyat = float(b.close[-1])
        oz = d.isaretle({KIMLIK: fiyat})
        durum = d.izleyici.guncelle(oz / self.kol.baslangic_ozkaynak, simdi).value if d.izleyici else "normal"
        mevcut = d.adet.get(KIMLIK, 0.0)
        if durum != "normal" and abs(hedef) > 0 and not (mevcut and np.sign(mevcut) == np.sign(hedef)):
            hedef = 0.0                                          # fren: yeni risk yok
        ayr = {"kimlikler": [KIMLIK], "sinyal": sinyal, "agirlik": w, "hedef": [hedef], "etkin": [hedef],
               "fiyat": [fiyat], "ozkaynak": oz, "saatlik_bar": int(b.t[-1])}
        with self.defter.motor.begin() as bg:
            kid = int(bg.execute(insert(paper_karar).values(
                kol=self.kol.ad, bar_ms=karar_bar, karar_ms=simdi, kod_surumu=self.defter.kod,
                veri_hash=f"yahoo1m:{int(t[-1])}"[:64], durum=durum, ayrinti=ayr)).inserted_primary_key[0])
        if mevcut and hedef and np.sign(mevcut) == np.sign(hedef):
            q = 0.0                                              # aynı yönde tut (bant 0: yön değişmedikçe işlem yok)
        else:
            q = hedef * oz / fiyat - mevcut
            q = math.copysign(math.floor(abs(q) / ADET_ADIMI) * ADET_ADIMI, q) if abs(q) >= ADET_ADIMI else 0.0
        sonuc = self._emir(d, q, simdi, "karar", s, kid, fiyat) if q else {}
        _log.info("gun_ici_karar", bar_ms=karar_bar, sinyal=sinyal, agirlik=round(w, 3), durum=durum, adet=q)
        return {"karar_id": kid, "sinyal": sinyal, "agirlik": round(w, 3), **sonuc}

    def _emir(self, d, q: float, simdi: int, tur: str, s: Seans | None, karar_id: int | None = None,
              fiyat: float | None = None) -> dict:
        """Risk onayı → anında yürütme (Alpaca piyasa emri ya da iç simülasyon)."""
        if s is None:   # seans dışı: kapatma da bekler (gece pozisyon kalmamalı; bekçi işaretten görür)
            _log.error("gun_ici_seans_disi_pozisyon", adet=q)
            return {"bekle": "seans dışı"}
        fiyat = fiyat or self.kaynak.son_fiyat()
        mevcut = d.adet.get(KIMLIK, 0.0)
        pf = Portfoy(d.isaretle({KIMLIK: fiyat}), dict(d.adet), {KIMLIK: fiyat}, {KIMLIK: SINIF},
                     d.izleyici.durum if d.izleyici else Durum.NORMAL, {self.kol.ad} if self._durduruldu() else set())
        istemci = f"GI{simdi // DAKIKA_MS}-{uuid.uuid4().hex[:8]}"
        r = self.risk.onayla(EmirIstegi(KIMLIK, SINIF, q, fiyat, self.kol.ad, simdi, istemci),
                             Piyasa(fiyat, simdi - simdi % SAAT_MS - SAAT_MS, SAAT_MS, True, ADET_ADIMI), pf)
        onay = (q if r.risk_azaltan and r.miktar == q else r.miktar) if r.onay else 0.0
        eid = self.defter.emir_yaz(self.kol.ad, karar_id, istemci, KIMLIK, q, onay, fiyat, tur,
                                   {"onay": r.onay, "gerekceler": list(r.gerekceler), "risk_azaltan": r.risk_azaltan},
                                   zaman_ms=simdi)
        if not onay:
            self.defter.olay_yaz(eid, self.kol.ad, "ret", KIMLIK, 0.0, None, 0.0, simdi,
                                 {"gerekceler": list(r.gerekceler)})
            return {"ret": list(r.gerekceler)}
        if self.mod == "alpaca":
            return self._alpaca(eid, istemci, onay, simdi)
        mm = self.ay.maliyet
        k = (mm.yari_spread_bps + mm.kayma_bps) / 1e4
        px = fiyat * (1 + k) if onay > 0 else fiyat * (1 - k)
        self.defter.olay_yaz(eid, self.kol.ad, "dolum", KIMLIK, onay, px, abs(onay) * px * mm.ucret_bps / 1e4, simdi,
                             {"yurutme": "ic", "referans": fiyat, "kayma_bps": k * 1e4, "mevcut": mevcut})
        return {"dolum": onay, "fiyat": round(px, 4)}

    def _alpaca(self, eid: int, istemci: str, adet: float, simdi: int) -> dict:
        try:
            self.alpaca.emir_gonder(sembol(KIMLIK), adet, istemci, "day")
        except Exception as e:  # noqa: BLE001 — ret olarak yazılır; sonraki turda yeniden karar yok (çift emir riski)
            self.defter.olay_yaz(eid, self.kol.ad, "ret", KIMLIK, 0.0, None, 0.0, simdi, {"gerekceler": [str(e)[:300]]})
            _log.error("gun_ici_alpaca_hatasi", hata=f"{type(e).__name__}: {e}"[:200])
            return {"ret": [str(e)[:120]]}
        for _ in range(10):                      # piyasa emri saniyeler içinde dolar
            time.sleep(1)
            dol = self.alpaca.emir(istemci)
            if dol is not None and dol.durum == "filled":
                px = dol.fiyat * (1 + EK_KAYMA) if dol.adet > 0 else dol.fiyat * (1 - EK_KAYMA)
                self.defter.olay_yaz(eid, self.kol.ad, "dolum", KIMLIK, dol.adet, px, duzenleyici_ucret(dol.adet, px),
                                     int(self.saat() * 1000), {"yurutme": "alpaca", "alpaca_id": dol.emir_id,
                                                                "alpaca_fiyat": dol.fiyat})
                return {"dolum": dol.adet, "fiyat": round(px, 4)}
        _log.error("gun_ici_alpaca_dolmadi", istemci=istemci)
        return {"bekle": "dolmadı"}

    def _isaretle(self, simdi: int) -> dict:
        d = self.defter.durum(self.kol)
        fiyat = {}
        if d.adet:
            try:
                fiyat = {KIMLIK: self.kaynak.son_fiyat()}
            except Exception as e:  # noqa: BLE001
                _log.error("gun_ici_fiyat_yok", hata=f"{type(e).__name__}: {e}"[:160])
                return {}
        d.isaretle(fiyat)
        self.defter.ozkaynak_yaz(self.kol.ad, simdi - simdi % SAAT_MS, d, fiyat)
        if d.izleyici is not None and d.izleyici.durum == Durum.ACIL_DURDURMA:
            denetim.kaydet(self.defter.motor, DUGUM, "acil_durdurma", {"kol": self.kol.ad, "ozkaynak": d.ozkaynak})
        return {"ozkaynak": round(d.ozkaynak, 2)}


def calistir(sure_sn: float | None = None, dongu_sn: float = 20.0) -> None:
    import os

    from tradebot.ayar import ayarlar as sistem
    from tradebot.canli.nasdaq import alpaca_istemci
    from tradebot.db import motor as db_motor
    from tradebot.veri.http import NazikIstemci

    ay = ayarlar()
    while ay is None:   # kol henüz tanımlı değil: çökme döngüsü yerine bekle
        _log.warning("gun_ici_kol_tanimsiz", bilgi="config/paper.yaml `nasdaq_gun_ici` yok; 10 dk sonra yeniden okunur")
        time.sleep(600)
        ay = ayarlar()
    a = sistem()
    defter = PaperDefter(db_motor(a), os.environ.get("TRADEBOT_KOD_SURUMU", "yerel"))
    alp = alpaca_istemci(a) if ay.yurutme != "ic" else None
    http = NazikIstemci("yahoo_gun_ici", aralik_sn=0.3, basliklar={"User-Agent": "Mozilla/5.0"}, deneme=3)
    dugum = GunIciDugumu(defter, ay, Kaynak(http.al), alp)
    dugum.ac()
    _log.info("gun_ici_basladi", kol=ay.kol.ad, yurutme=dugum.mod)
    bas = time.monotonic()
    while sure_sn is None or time.monotonic() - bas < sure_sn:
        try:
            r = dugum.tur()
            if r:
                _log.info("gun_ici_tur", **r)
        except Exception as e:  # noqa: BLE001
            _log.error("gun_ici_tur_hatasi", hata=f"{type(e).__name__}: {e}"[:300])
        time.sleep(dongu_sn)
