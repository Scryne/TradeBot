"""Nasdaq paper düğümü (dalga 19; günlük kollar). Nautilus dışı ayrı süreç (compose `nasdaq`), her ~60 sn bir tur.

Akış:
- **Karar** (XNYS işlem günü, kapanış + `KARAR_GECIKME_MS`): bugünkü üyelerin Yahoo günlük barları güncellenir →
  backtest'in AYNI zinciri (`karar.hazirla` → `turnuva.grup_hazirla` [PIT üyelik + dönem kapsamı] → `hedef_uret` →
  `panel.dengele_adim`; kural 3) → karar emirden ÖNCE deftere → her emir `RiskMotoru.onayla`'dan (kural 5) → onaylı emir
  bekleyen olarak deftere (kesirli adet 1e-4, sıfıra doğru yuvarlanır; satışlar önce).
- **Yürütme** (ertesi seansın açılışı; kural 4: karar kapanmış barla, dolum sonraki açılışta):
  - `alpaca`: açılıştan `GONDER_MS` sonra Alpaca PAPER hesabına kesirli `day` piyasa emri. Açılış müzayedesi (`opg`)
    kullanılmaz: Alpaca paper onu müzayede fiyatıyla değil anlık bid/ask'tan dolduruyor ve kesirli adet kabul etmiyor;
    ilk dakikanın piyasa emri aynı şeyi daha öngörülebilir yapar. Dolum Alpaca'dan okunur; deftere `EK_KAYMA` kadar
    aleyhte kaydırılmış fiyat ve düzenleyici ücretlerle yazılır (paper dolumu piyasa etkisini görmez). Kesirli adet
    reddedilirse tam adetle yeniden gönderilir.
  - `ic`: aracı kurum yok; dolum açılış fiyatından (Yahoo 1 dk; yoksa günlük barın açılışı), maliyet modeliyle aleyhte
    (taraf başı 5,5 bps; backtest'le aynı model).
  - Karar kapanıştan sonra kaçırıldıysa (düğüm kapalıydı) ertesi açılıştan önce telafi edilir; açılış geçtiyse o günün
    kararı atlanır (geç karar dolumu bir gün kaydırır, backtest'le çelişir).
- **İşaret** (saat başı; kalp atışı): özkaynak son fiyatlarla deftere. Kol elle durdurulduysa ya da acil durdurma
  eşiği aşıldıysa pozisyonlar hemen kapatılır (seans açıksa hemen, değilse sonraki açılışta; kural 7).
- **Mutabakat** (`alpaca`): kolların toplam adedi ↔ Alpaca pozisyonları; fark loglanır (bekçi KRİTİK bildirir), kolların
  yeni riski durdurulur (`durdur`, neden `mutabakat`; pozisyon tutulur).

Defter `PaperDefter` tablolarıdır: kol tanımı + karar + emir + olay (`gonderildi`, `dolum`, `ret`, `iptal`) + özkaynak.
Yeniden başlatmada durum defterden kurulur; final olayı olmayan emir bekleyen sayılır (Alpaca'da istemci kimliğiyle
sorgulanır: çift emir gönderilmez).
"""
from __future__ import annotations

import math
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

import numpy as np
from sqlalchemy import select
from sqlalchemy.engine import Engine

from tradebot import denetim
from tradebot.arastirma.maliyet import MaliyetModeli, model
from tradebot.arastirma.turnuva import STRATEJILER, Ayar
from tradebot.canli import karar as kr
from tradebot.canli.defter import PaperDefter
from tradebot.canli.karar import KolDurum
from tradebot.canli.kollar import PaperKol, oku
from tradebot.cekirdek.boyut import kaldirac_dogrula
from tradebot.db import paper_emir, paper_emir_olay
from tradebot.kayit import log
from tradebot.risk.motor import Durum, EmirIstegi, Piyasa, Portfoy, RiskAyar, RiskMotoru

DUGUM = "nasdaq"
SINIF = "hisse"
GUN_MS = 86_400_000
SAAT_MS = 3_600_000
DAKIKA_MS = 60_000
KARAR_GECIKME_MS = 25 * DAKIKA_MS    # Yahoo günlük barı kapanış + 15 dk'da tamam sayılır (yahoo.tamamlanmamis_at)
ACILIS_BEKLE_MS = 3 * DAKIKA_MS      # iç yürütme: açılış fiyatı ilk dakika barından (biraz bekle)
GONDER_MS = 1 * DAKIKA_MS            # Alpaca: açılıştan sonra emir gönderimi
ADET_ADIMI = 0.0001                  # kesirli hisse (Alpaca 9 haneye kadar; 4 hane yeter)
EK_KAYMA = 0.0001                    # Alpaca paper dolumuna ek aleyhte kayma (piyasa etkisi yok sayılıyor)
SEC_UCRET = 20.6e-6                  # satış notional'ı başına (2026-04-04'ten)
TAF_HISSE, TAF_TAVAN = 0.000166, 8.30
FINAL = ("dolum", "ret", "iptal")
# Risk motorunun bayatlık birimi (2 birim = eşik). Borsa günlük barı takvim gününe değil seansa bağlıdır: Cuma barıyla
# Pazar verilen telafi kararı 2 takvim gününü aşar (2026-10-18: ilk kararın 100 emri "veri bayat" ile reddedildi).
# 3 gün × 2 = 6 gün hafta sonu + tatili kapsar; barın son kapanmış seansa ait olduğu ayrıca `_kol_karar`'da denetlenir.
BAYAT_BIRIM_MS = 3 * GUN_MS
_log = log("nasdaq")


@dataclass(frozen=True)
class NasdaqAyarlari:
    kollar: tuple[PaperKol, ...]
    yurutme: str                     # "alpaca" | "ic" | "otomatik" (anahtar varsa alpaca)
    risk: RiskAyar
    maliyet: MaliyetModeli
    kol_yurutme: dict = field(default_factory=dict)   # kol adı → yürütme (kol satırında `yurutme` verildiyse)


def ayarlar(d: dict | None = None) -> NasdaqAyarlari | None:
    """`config/paper.yaml` `nasdaq` bloğu (yoksa None: düğüm çalışmaz)."""
    d = d or oku()
    b = d.get("nasdaq")
    if not b or not b.get("kollar"):
        return None
    bo = b["boyut"]
    kaldirac = kaldirac_dogrula(float(bo["kaldirac"]))
    if kaldirac > 1.0:
        raise ValueError("Nasdaq nakit kolu: brüt ≤ 1x (kaldıraç yok)")
    kollar, kol_yurutme = [], {}
    for k in b["kollar"]:
        if k["strateji"] not in STRATEJILER:
            raise ValueError(f"bilinmeyen strateji: {k['strateji']}")
        yur = k.get("yurutme", b.get("yurutme", "otomatik"))
        # Grup tanımı kolun kimliğidir (defter tanımı): `depo` (veri kaynağı) ve hesap kol başına
        grup = dict(b["grup"]) | dict(k.get("grup") or {}) | {
            "dugum": DUGUM, "hesap": "Alpaca paper" if yur != "ic" else "iç simülasyon"}
        # `jev: true`: A3 (SEC 8-K) vetolu ikiz; zekâ servisi kör ise yeni giriş yarım boyut (Final Doküman, katman 5)
        ayar = Ayar(hedef_vol=float(bo["hedef_vol"]), kaldirac=kaldirac, vol_pencere_gun=int(bo["vol_pencere_gun"]),
                    frenler=bool(d.get("frenler", True)), bant=float(bo["bant"]), jev_veto=bool(k.get("jev", False)))
        kollar.append(PaperKol(k["ad"], k["strateji"], b.get("grup_adi", "nasdaq100"), grup, "1d", ayar,
                               dict(k["parametre"]), k.get("sinif", "B"), float(b.get("baslangic_ozkaynak", 100_000))))
        if "yurutme" in k:
            kol_yurutme[k["ad"]] = yur
    if len({k.ad for k in kollar}) != len(kollar):
        raise ValueError("kol adları tekil olmalı")
    return NasdaqAyarlari(tuple(kollar), b.get("yurutme", "otomatik"), RiskAyar(kaldirac=kaldirac), model("NASDAQ", SINIF),
                          kol_yurutme)


def sembol(kimlik: str) -> str:
    return kimlik.split(":", 1)[1].replace(".", "-")


def duzenleyici_ucret(adet: float, fiyat: float) -> float:
    """Satışta SEC + FINRA TAF (alışta 0). Komisyon 0 (Alpaca)."""
    if adet >= 0:
        return 0.0
    return abs(adet) * fiyat * SEC_UCRET + min(abs(adet) * TAF_HISSE, TAF_TAVAN)


# ---------------------------------------------------------------------------------------------------- takvim
@dataclass(frozen=True)
class Seans:
    gun_ms: int        # seans günü 00:00 UTC (günlük barın zaman damgası)
    acilis_ms: int
    kapanis_ms: int


def seanslar(bas_ms: int, bit_ms: int) -> list[Seans]:
    from tradebot.veri.takvim import gun_basi, takvim

    return [Seans(gun_basi(o), o, c) for o, c in takvim("XNYS").seanslar(bas_ms, bit_ms)]


# ---------------------------------------------------------------------------------------------------- dış dünya
class Kaynak:
    """Veri ve fiyat: günlük barların güncellenmesi (`guncelle`), son fiyat ve seans açılış fiyatı (Yahoo; Alpaca
    tanımlıysa son fiyat Alpaca IEX'ten)."""

    def __init__(self, guncelle: Callable[[], dict], yahoo_al: Callable[[str, dict], bytes], alpaca=None) -> None:
        self._guncelle, self._al, self.alpaca = guncelle, yahoo_al, alpaca
        self.son: dict[str, tuple[float, int]] = {}   # kimlik → (fiyat, zaman_ms) önbellek

    def guncelle(self) -> dict:
        return self._guncelle()

    def _gun_ici(self, kim: str) -> dict:
        import json

        d = json.loads(self._al(f"https://query1.finance.yahoo.com/v8/finance/chart/{sembol(kim)}",
                                {"interval": "1m", "range": "1d"}))["chart"]["result"][0]
        return d

    def fiyatlar(self, kimlikler: list[str]) -> dict[str, float]:
        """Son fiyatlar; alınamayan için önbellekteki son değer (yoksa yok)."""
        if self.alpaca is not None and kimlikler:
            try:
                p = self.alpaca.son_fiyatlar([sembol(k) for k in kimlikler])
                now = int(time.time() * 1000)
                for k in kimlikler:
                    if sembol(k) in p:
                        self.son[k] = (p[sembol(k)], now)
            except Exception as e:  # noqa: BLE001 — Yahoo'ya düşer
                _log.warning("alpaca_fiyat_alinamadi", hata=f"{type(e).__name__}: {e}"[:160])
        for k in kimlikler:
            if k in self.son and time.time() * 1000 - self.son[k][1] < 10 * DAKIKA_MS:
                continue
            try:
                m = self._gun_ici(k)["meta"]
                self.son[k] = (float(m["regularMarketPrice"]), int(m.get("regularMarketTime", time.time())) * 1000)
            except Exception as e:  # noqa: BLE001
                _log.warning("fiyat_alinamadi", kimlik=k, hata=f"{type(e).__name__}: {e}"[:160])
        return {k: v[0] for k, v in self.son.items() if k in kimlikler}

    def acilis(self, kimlikler: list[str], acilis_ms: int) -> dict[str, float]:
        """Seansın açılış fiyatı (ilk 1 dk barın açılışı; seans başından ≤ 5 dk sonra başlayan bar kabul)."""
        out = {}
        for k in kimlikler:
            try:
                d = self._gun_ici(k)
                ts = [int(x) * 1000 for x in d.get("timestamp") or []]
                op = (d["indicators"]["quote"][0].get("open") or [])
                for t, o in zip(ts, op, strict=False):
                    if o is not None and acilis_ms <= t < acilis_ms + 5 * DAKIKA_MS:
                        out[k] = float(o)
                        break
            except Exception as e:  # noqa: BLE001
                _log.warning("acilis_alinamadi", kimlik=k, hata=f"{type(e).__name__}: {e}"[:160])
        return out


# ---------------------------------------------------------------------------------------------------- düğüm
@dataclass
class Bekleyen:
    emir_id: int
    kol: str
    istemci_id: str            # aracı kurumdaki güncel istemci kimliği (tam adetle yeniden gönderimde değişir)
    kimlik: str
    adet: float
    karar_fiyati: float
    zaman_ms: int
    tur: str
    gonderildi: bool


def _adima(q: float) -> float:
    """Kesirli adet adımına, sıfıra doğru."""
    n = math.floor(abs(q) / ADET_ADIMI + 1e-9)
    return math.copysign(round(n * ADET_ADIMI, 4), q) if n else 0.0


class NasdaqDugumu:
    def __init__(self, defter: PaperDefter, ay: NasdaqAyarlari, kaynak: Kaynak, depo, kayit_al: Callable[[], dict],
                 alpaca=None, saat: Callable[[], float] = time.time, nabiz_dizini=None) -> None:
        self.defter, self.ay, self.kaynak, self.depo, self.kayit_al = defter, ay, kaynak, depo, kayit_al
        self.nabiz_dizini = nabiz_dizini   # zekâ nabzı (Jev'li kolun "habere kör" modu); None: kontrol yok
        self.m: Engine = defter.motor
        self.alpaca = alpaca if ay.yurutme in ("alpaca", "otomatik") else None
        if ay.yurutme == "alpaca" and self.alpaca is None:
            raise RuntimeError("yurutme: alpaca ama Alpaca paper anahtarı yok")
        self.saat = saat
        self.risk = {k.ad: RiskMotoru(ay.risk) for k in ay.kollar}
        self._son_isaret = 0
        self._karar_deneme: dict[int, int] = {}
        self._baslangic = 0

    @property
    def mod(self) -> str:
        return "alpaca" if self.alpaca is not None else "ic"

    def kol_modu(self, kol: str) -> str:
        return "ic" if self.alpaca is None or self.ay.kol_yurutme.get(kol) == "ic" else "alpaca"

    def ac(self) -> None:
        for k in self.ay.kollar:
            if self.defter.kol_ac(k, int(self.saat() * 1000)):
                _log.info("kol_acildi", kol=k.ad, yurutme=self.mod)
        self._baslangic = min(self.defter.kol_baslangic(k.ad) or 0 for k in self.ay.kollar)

    # ------------------------------------------------------------------ durum
    def _durduruldu(self, kol: str) -> tuple[bool, bool]:
        """(yeni risk kapalı mı, düzleşmeli mi): son elle olay `durdur` → ikisi de; düğümün kendi `mutabakat`
        durdurması → yalnız yeni risk kapalı (pozisyon tutulur)."""
        son = None
        for o in self.defter.kol_olaylari(kol):
            if o.tur in ("durdur", "devam"):
                son = o
        if son is None or son.tur == "devam":
            return False, False
        return True, son.ayrinti.get("neden") != "mutabakat"

    def bekleyenler(self) -> list[Bekleyen]:
        """Onaylanmış, final olayı (dolum/ret/iptal) olmayan emirler."""
        with self.m.connect() as b:
            emirler = list(b.execute(select(paper_emir).where(
                paper_emir.c.kol.in_([k.ad for k in self.ay.kollar]), paper_emir.c.onaylanan != 0)))
            if not emirler:
                return []
            olaylar = list(b.execute(select(paper_emir_olay.c.emir_id, paper_emir_olay.c.tur, paper_emir_olay.c.ayrinti)
                                     .where(paper_emir_olay.c.emir_id.in_([e.id for e in emirler]))
                                     .order_by(paper_emir_olay.c.id)))
        final = {i for i, t, _ in olaylar if t in FINAL}
        gonderim = {i: (a or {}).get("istemci") for i, t, a in olaylar if t == "gonderildi"}   # son gönderim
        return [Bekleyen(e.id, e.kol, gonderim.get(e.id) or e.istemci_emir_id, e.enstruman, float(e.onaylanan),
                         float(e.karar_fiyati), int(e.zaman_ms), e.tur, e.id in gonderim)
                for e in emirler if e.id not in final]

    # ------------------------------------------------------------------ tur
    def tur(self) -> dict:
        simdi = int(self.saat() * 1000)
        out: dict = {}
        ss = seanslar(simdi - 8 * GUN_MS, simdi + 8 * GUN_MS)
        bugun = next((s for s in ss if s.gun_ms == simdi // GUN_MS * GUN_MS), None)
        acik = bugun is not None and bugun.acilis_ms <= simdi < bugun.kapanis_ms
        y = self._yurut(simdi, bugun, acik)
        if y:
            out["yurutme"] = y
        if simdi - simdi % SAAT_MS > self._son_isaret:
            out["isaret"] = self._isaretle(simdi, acik)
            self._son_isaret = simdi - simdi % SAAT_MS
        # Son kapanmış seansın kararı: kapanış + gecikmeden sonra, ertesi açılışa kadar (telafi dahil)
        son = [s for s in ss if s.kapanis_ms + KARAR_GECIKME_MS <= simdi]
        if son:
            s = son[-1]
            ertesi = next((x for x in ss if x.acilis_ms > s.kapanis_ms), None)
            if ertesi is not None and simdi < ertesi.acilis_ms:
                k = self._gunluk(s, simdi)
                if k:
                    out["karar"] = k
            elif ertesi is not None and s.gun_ms not in self._karar_deneme and s.kapanis_ms >= self._baslangic \
                    and not all(self.defter.karar_var(kol.ad, s.gun_ms) for kol in self.ay.kollar):
                self._karar_deneme[s.gun_ms] = -1
                _log.error("nasdaq_karar_kacirildi", gun_ms=s.gun_ms)
        return out

    # ------------------------------------------------------------------ karar
    def _gunluk(self, s: Seans, simdi: int) -> dict | None:
        eksik = [k for k in self.ay.kollar if not self.defter.karar_var(k.ad, s.gun_ms)]
        if not eksik:
            return None
        deneme = self._karar_deneme.get(s.gun_ms, 0)
        if deneme and simdi % (10 * DAKIKA_MS) >= DAKIKA_MS:   # başarısızsa ~10 dk'da bir yeniden dene
            return None
        self._karar_deneme[s.gun_ms] = deneme + 1
        try:
            g = self.kaynak.guncelle()
        except Exception as e:  # noqa: BLE001 — eldeki veriyle denenir; o günün barı yoksa karar beklenir
            g = {"hata": f"{type(e).__name__}: {e}"[:200]}
            _log.error("nasdaq_veri_guncellenemedi", hata=g["hata"])
        kayit = self.kayit_al()
        out: dict = {"veri": g}
        for kol in eksik:
            try:
                out[kol.ad] = self._kol_karar(kol, s, kayit)
            except Exception as e:  # noqa: BLE001 — bir kolun hatası diğerini durdurmaz
                _log.error("nasdaq_kol_karar_hatasi", kol=kol.ad, hata=f"{type(e).__name__}: {e}"[:300])
                out[kol.ad] = {"hata": f"{type(e).__name__}: {e}"[:200]}
        return out

    def _kol_karar(self, kol: PaperKol, s: Seans, kayit: dict) -> dict:
        h = kr.hazirla(self.depo, kayit, kol, bit_ms=s.gun_ms + GUN_MS)     # o günün barı dahil, sonrası yok
        if int(h.g.t[-1]) != s.gun_ms:
            raise RuntimeError(f"seans gününün barı yok (son {int(h.g.t[-1])}, beklenen {s.gun_ms})")
        d = self.defter.durum(kol)
        kapali, duzles = self._durduruldu(kol.ad)
        hedef = np.zeros(len(h.g.kimlikler)) if duzles else None
        vetolu, kor = set(), False
        if kol.jev:   # A3 vetoları (yalnız riski azaltır) ve zekâ servisinin nabzı
            from tradebot.zeka import nabiz
            from tradebot.zeka.olay import aktif_vetolar

            simdi = int(self.saat() * 1000)
            vetolu = aktif_vetolar(self.m, simdi)
            if self.nabiz_dizini is not None:
                kor = nabiz.kor_mu(self.nabiz_dizini, simdi, kaynak="sec_8k")[0]
        k = kr.karar_ver(kol, h, d, vetolu, hedef, habere_kor=kor)
        kid = self.defter.karar_yaz(k, h.g.veri_hash)
        fiyat = {kim: float(f) for kim, f in zip(k.kimlikler, k.fiyat, strict=True)}
        planlar = []
        for j, kim in enumerate(k.kimlikler):
            q = k.miktar.get(kim)
            if not q:
                continue
            mevcut = d.adet.get(kim, 0.0)
            tam = -mevcut if (k.yeni[j] == 0 and mevcut) else _adima(q)   # tam kapanış bütün adet
            if tam:
                planlar.append((kim, tam))
        sonuc = self._emirler(kol, d, kid, planlar, fiyat, s.gun_ms, k.durum, kapali, "karar")
        _log.info("nasdaq_karar", kol=kol.ad, gun_ms=s.gun_ms, durum=k.durum, emir=len(planlar), onaylanan=sonuc["onay"],
                  hisse=int((np.abs(k.etkin_hedef) > 0).sum()), brut=round(float(np.abs(k.yeni).sum()), 3))
        return {"karar_id": kid, "durum": k.durum, "emir": len(planlar), **sonuc}

    def _emirler(self, kol: PaperKol, d: KolDurum, karar_id: int | None, planlar: list[tuple[str, float]],
                 fiyat: dict[str, float], bar_ms: int, durum: str, kapali: bool, tur: str) -> dict:
        """Riskten geçen emirler bekleyen olarak deftere (satışlar önce; aynı turdaki sonraki emir tavanı görür)."""
        planlar = sorted(planlar, key=lambda x: x[1] > 0)
        oz = d.isaretle({k: fiyat[k] for k in d.adet}) if d.adet else d.nakit
        kimler = set(d.adet) | {k for k, _ in planlar}
        pf = Portfoy(oz, dict(d.adet), {k: fiyat[k] for k in kimler}, {k: SINIF for k in kimler}, Durum(durum),
                     {kol.ad} if kapali else set())
        simdi = int(self.saat() * 1000)
        out: dict = {"onay": 0, "ret": []}
        for kim, q in planlar:
            f = fiyat[kim]
            istemci = f"NQ{bar_ms // GUN_MS}-{uuid.uuid4().hex[:10]}-{sembol(kim)}"[:48]
            r = self.risk[kol.ad].onayla(EmirIstegi(kim, SINIF, q, f, kol.ad, simdi, istemci),
                                         Piyasa(f, bar_ms, BAYAT_BIRIM_MS, True, ADET_ADIMI), pf)
            onay = (q if (r.risk_azaltan and r.miktar == q) else _adima(r.miktar)) if r.onay else 0.0
            risk = {"onay": r.onay, "gerekceler": list(r.gerekceler), "risk_azaltan": r.risk_azaltan}
            eid = self.defter.emir_yaz(kol.ad, karar_id, istemci, kim, q, onay, f, tur, risk)
            if not onay:
                self.defter.olay_yaz(eid, kol.ad, "ret", kim, 0.0, None, 0.0, simdi,
                                     {"gerekceler": list(r.gerekceler) or ["adet adımının altı"]})
                out["ret"].append({"kimlik": kim, "gerekce": list(r.gerekceler)})
                continue
            pf.pozisyonlar[kim] = pf.pozisyonlar.get(kim, 0.0) + onay
            out["onay"] += 1
        return out

    # ------------------------------------------------------------------ yürütme
    def _yurut(self, simdi: int, bugun: Seans | None, acik: bool) -> dict:
        bek = self.bekleyenler()
        if not bek:
            return {}
        alp = [b for b in bek if self.kol_modu(b.kol) == "alpaca"]
        ic = [b for b in bek if self.kol_modu(b.kol) == "ic"]
        out = {}
        if alp:
            out |= {f"alpaca_{k}": v for k, v in self._alpaca_yurut(alp, simdi, bugun, acik).items()}
        if ic:
            out |= {f"ic_{k}": v for k, v in self._ic_yurut(ic, simdi, bugun, acik).items()}
        return out

    def _ic_yurut(self, bek: list[Bekleyen], simdi: int, bugun: Seans | None, acik: bool) -> dict:
        """Karar emirleri: kararın ertesi seansının açılış fiyatından. Seans içinde verilen kapatma emirleri (elle
        durdurma, acil durdurma; riski azaltan): hemen, son fiyattan. Maliyet modeli aleyhte."""
        if bugun is None or simdi < bugun.acilis_ms + ACILIS_BEKLE_MS:
            return {}
        acilista = [b for b in bek if b.zaman_ms < bugun.acilis_ms]
        hemen = [b for b in bek if b.zaman_ms >= bugun.acilis_ms and b.tur != "karar" and acik]
        if not acilista and not hemen:
            return {}
        px = self.kaynak.acilis(sorted({b.kimlik for b in acilista}), bugun.acilis_ms) if acilista else {}
        if not acik:   # seans bitti, açılış fiyatı hâlâ yoksa günlük barın açılışı (bar deposundan)
            for b in acilista:
                if b.kimlik not in px:
                    df = self.depo.oku(b.kimlik, "1d", bugun.gun_ms, bugun.gun_ms + GUN_MS)
                    if len(df):
                        px[b.kimlik] = float(df["open"][0])
        son = self.kaynak.fiyatlar(sorted({b.kimlik for b in hemen})) if hemen else {}
        mm = self.ay.maliyet
        k = (mm.yari_spread_bps + mm.kayma_bps) / 1e4
        out = {"dolum": 0, "bekleyen": 0}
        for b, p in [(b, px.get(b.kimlik)) for b in acilista] + [(b, son.get(b.kimlik)) for b in hemen]:
            if p is None:
                out["bekleyen"] += 1
                continue
            fiyat = p * (1 + k) if b.adet > 0 else p * (1 - k)
            ucret = abs(b.adet) * fiyat * mm.ucret_bps / 1e4
            self.defter.olay_yaz(b.emir_id, b.kol, "dolum", b.kimlik, b.adet, fiyat, ucret, simdi,
                                 {"yurutme": "ic", "referans": p, "kayma_bps": k * 1e4,
                                  "kaynak": "acilis" if b.zaman_ms < bugun.acilis_ms else "son_fiyat"})
            out["dolum"] += 1
        return {x: v for x, v in out.items() if v}

    def _alpaca_yurut(self, bek: list[Bekleyen], simdi: int, bugun: Seans | None, acik: bool) -> dict:
        out = {"gonderilen": 0, "dolum": 0, "ret": 0}
        for b in bek:
            if not b.gonderildi:
                if acik and bugun.acilis_ms + GONDER_MS <= simdi < bugun.kapanis_ms - 5 * DAKIKA_MS:
                    out["gonderilen"] += self._gonder(b, simdi)
                continue
            dol = self._sorgula(b)
            if dol is None:
                continue
            if dol.durum == "filled" or (dol.durum in ("canceled", "expired", "done_for_day") and dol.adet):
                fiyat = dol.fiyat * (1 + EK_KAYMA) if dol.adet > 0 else dol.fiyat * (1 - EK_KAYMA)
                self.defter.olay_yaz(b.emir_id, b.kol, "dolum", b.kimlik, dol.adet, fiyat,
                                     duzenleyici_ucret(dol.adet, fiyat), simdi,
                                     {"yurutme": "alpaca", "alpaca_id": dol.emir_id, "alpaca_fiyat": dol.fiyat,
                                      "durum": dol.durum, "ek_kayma_bps": EK_KAYMA * 1e4, "istenen": b.adet})
                out["dolum"] += 1
            elif dol.durum in ("canceled", "expired", "rejected", "done_for_day"):
                self.defter.olay_yaz(b.emir_id, b.kol, "ret", b.kimlik, 0.0, None, 0.0, simdi,
                                     {"gerekceler": [f"alpaca: {dol.durum}"]})
                out["ret"] += 1
        return {k: v for k, v in out.items() if v}

    def _gonder(self, b: Bekleyen, simdi: int, tam: bool = False) -> int:
        adet = float(math.trunc(b.adet)) if tam else b.adet
        istemci = (b.istemci_id + "-T")[:48] if tam else b.istemci_id
        try:
            o = self.alpaca.emir_gonder(sembol(b.kimlik), adet, istemci, "day")
        except Exception as e:  # noqa: BLE001
            mevcut = self._sorgu(istemci, b.kimlik)        # zaman aşımı: emir gitmiş olabilir (çift emir yok)
            if mevcut is not None:
                self.defter.olay_yaz(b.emir_id, b.kol, "gonderildi", b.kimlik, 0.0, None, 0.0, simdi,
                                     {"alpaca_id": mevcut.emir_id, "istemci": istemci, "kurtarma": True})
                return 1
            if getattr(e, "durum", 0) in (403, 422):
                kesirli = abs(adet - math.trunc(adet)) > 1e-9
                if kesirli and not tam and abs(b.adet) >= 1:   # kesirli kabul edilmiyor: tam adetle yeniden
                    _log.warning("alpaca_kesirli_ret_tam_adet", kimlik=b.kimlik, hata=str(e)[:160])
                    return self._gonder(b, simdi, tam=True)
                self.defter.olay_yaz(b.emir_id, b.kol, "ret", b.kimlik, 0.0, None, 0.0, simdi,
                                     {"gerekceler": [str(e)[:300]]})
            _log.error("alpaca_emir_hatasi", kimlik=b.kimlik, hata=f"{type(e).__name__}: {e}"[:200])
            return 0
        self.defter.olay_yaz(b.emir_id, b.kol, "gonderildi", b.kimlik, 0.0, None, 0.0, simdi,
                             {"alpaca_id": o.get("id"), "istemci": istemci, "adet": adet})
        return 1

    def _sorgu(self, istemci: str, kimlik: str):
        try:
            return self.alpaca.emir(istemci)
        except Exception as e:  # noqa: BLE001
            _log.warning("alpaca_sorgu_hatasi", kimlik=kimlik, hata=f"{type(e).__name__}: {e}"[:160])
            return None

    def _sorgula(self, b: Bekleyen):
        return self._sorgu(b.istemci_id, b.kimlik)

    # ------------------------------------------------------------------ işaret, koruma, mutabakat
    def _isaretle(self, simdi: int, acik: bool) -> dict:
        saat_bas = simdi - simdi % SAAT_MS
        durumlar = {kol.ad: self.defter.durum(kol) for kol in self.ay.kollar}
        tum = sorted({k for d in durumlar.values() for k in d.adet})
        fiyat = self.kaynak.fiyatlar(tum) if tum else {}
        out = {}
        for kol in self.ay.kollar:
            d = durumlar[kol.ad]
            eksik = [k for k in d.adet if k not in fiyat]
            if eksik:   # fiyatı alınamayan pozisyon: son işaretteki fiyat
                onceki = self._son_fiyatlar(kol.ad)
                fiyat |= {k: onceki[k] for k in eksik if k in onceki}
            if any(k not in fiyat for k in d.adet):
                _log.error("nasdaq_isaret_fiyat_yok", kol=kol.ad, eksik=[k for k in d.adet if k not in fiyat])
                continue
            d.isaretle(fiyat)
            self.defter.ozkaynak_yaz(kol.ad, saat_bas, d, fiyat)
            out[kol.ad] = round(d.ozkaynak, 2)
            self._koruma(kol, saat_bas, fiyat, simdi, acik)
        if self.mod == "alpaca":
            out["mutabakat"] = self._mutabakat()
        return out

    def _son_fiyatlar(self, kol: str) -> dict[str, float]:
        from tradebot.db import paper_ozkaynak

        with self.m.connect() as b:
            f = b.execute(select(paper_ozkaynak.c.fiyat).where(paper_ozkaynak.c.kol == kol)
                          .order_by(paper_ozkaynak.c.zaman_ms.desc()).limit(1)).scalar()
        return dict(f or {})

    def _koruma(self, kol: PaperKol, saat_bas: int, fiyat: dict[str, float], simdi: int, acik: bool) -> None:
        """Elle durdurma ya da acil durdurma: bekleyen kapatması olmayan her pozisyon kapatma emri alır; gönderilmemiş
        alış emirleri iptal edilir (riski azaltan her şey otomatik, kural 7)."""
        d = self.defter.durum(kol)          # izleyici yeni işaretle kurulsun
        _, duzles = self._durduruldu(kol.ad)
        acil = d.izleyici is not None and d.izleyici.durum == Durum.ACIL_DURDURMA
        if not (duzles or acil):
            return
        for b in self.bekleyenler():
            if b.kol == kol.ad and b.adet > 0 and not b.gonderildi:
                self.defter.olay_yaz(b.emir_id, b.kol, "iptal", b.kimlik, 0.0, None, 0.0, simdi,
                                     {"neden": "acil_durdurma" if acil else "durdur"})
        if not d.adet:
            return
        bekleyen = {b.kimlik for b in self.bekleyenler() if b.kol == kol.ad}
        planlar = [(kim, -q) for kim, q in d.adet.items() if kim not in bekleyen]
        if not planlar:
            return
        tur = "acil" if acil else "durdur"
        self._emirler(kol, d, None, planlar, fiyat, saat_bas, Durum.ACIL_DURDURMA.value if acil else "normal", True, tur)
        if acil:
            denetim.kaydet(self.m, DUGUM, "acil_durdurma_kapatma", {"kol": kol.ad, "ozkaynak": d.ozkaynak})
        _log.warning("nasdaq_kapatma", kol=kol.ad, neden=tur, adet=len(planlar), seans_acik=acik)

    def _mutabakat(self) -> dict:
        try:
            alp = self.alpaca.pozisyonlar()
        except Exception as e:  # noqa: BLE001
            return {"hata": f"{type(e).__name__}: {e}"[:120]}
        defter: dict[str, float] = {}
        for kol in self.ay.kollar:
            if self.kol_modu(kol.ad) != "alpaca":   # iç simülasyondaki kolun pozisyonu aracı kurumda yoktur
                continue
            for k, q in self.defter.durum(kol).adet.items():
                defter[sembol(k)] = defter.get(sembol(k), 0.0) + q
        bekleyen = {sembol(b.kimlik) for b in self.bekleyenler() if self.kol_modu(b.kol) == "alpaca"}   # yolda olan emir
        fark = {s: {"defter": round(defter.get(s, 0.0), 6), "alpaca": alp.get(s, 0.0)}
                for s in sorted(set(defter) | set(alp))
                if abs(defter.get(s, 0.0) - alp.get(s, 0.0)) > 1e-6 and s not in bekleyen}
        if fark:
            _log.error("nasdaq_mutabakat_farki", fark=fark)
            for kol in self.ay.kollar:
                if self.kol_modu(kol.ad) == "alpaca" and not self._durduruldu(kol.ad)[0]:
                    self.defter.kol_olay_yaz(kol.ad, "durdur", {"neden": "mutabakat", "fark": fark})
        return {"fark": fark} if fark else {"tamam": True}


def alpaca_istemci(a=None):
    """Ayarlarda paper anahtarı varsa istemci, yoksa None."""
    from tradebot.ayar import ayarlar as sistem
    from tradebot.canli.alpaca import AlpacaPaper

    a = a or sistem()
    if a.alpaca_anahtar is None or a.alpaca_gizli is None:
        return None
    return AlpacaPaper(a.alpaca_anahtar.get_secret_value(), a.alpaca_gizli.get_secret_value())


def calistir(sure_sn: float | None = None, dongu_sn: float = 60.0) -> None:
    """compose `nasdaq` servisi: her `dongu_sn`'de bir tur; hata turu atlar (log), sonraki tur yeniden dener."""
    import os

    from tradebot.ayar import ayarlar as sistem
    from tradebot.db import motor as db_motor
    from tradebot.veri import enstruman as en
    from tradebot.veri import nasdaq as nqv
    from tradebot.veri.depo import BarDepo
    from tradebot.veri.http import NazikIstemci

    ay = ayarlar()
    while ay is None:   # kol henüz tanımlı değil: çökme döngüsü yerine bekle (dağıtımdan sonra yapılandırma gelir)
        _log.warning("nasdaq_kol_tanimsiz", bilgi="config/paper.yaml `nasdaq.kollar` boş; 10 dk sonra yeniden okunur")
        time.sleep(600)
        ay = ayarlar()
    a = sistem()
    m = db_motor(a)
    defter = PaperDefter(m, os.environ.get("TRADEBOT_KOD_SURUMU", "yerel"))
    alp = alpaca_istemci(a) if ay.yurutme != "ic" else None
    if alp is not None:
        h = alp.hesap()
        _log.info("alpaca_hesap", durum=h.get("status"), ozkaynak=h.get("equity"), para=h.get("currency"))
    http = NazikIstemci("yahoo_canli", aralik_sn=0.3, basliklar={"User-Agent": "Mozilla/5.0"}, deneme=3)
    kaynak = Kaynak(lambda: nqv.guncelle(a, m, yalniz_guncel=True), http.al, alp)
    dugum = NasdaqDugumu(defter, ay, kaynak, BarDepo(a.veri_dizini), lambda: {k["kimlik"]: k for k in en.hepsi(m)}, alp,
                         nabiz_dizini=a.veri_dizini)
    dugum.ac()
    _log.info("nasdaq_basladi", kollar={k.ad: dugum.kol_modu(k.ad) for k in ay.kollar}, yurutme=dugum.mod)
    bas = time.monotonic()
    while sure_sn is None or time.monotonic() - bas < sure_sn:
        try:
            r = dugum.tur()
            if r:
                _log.info("nasdaq_tur", **r)
        except Exception as e:  # noqa: BLE001
            _log.error("nasdaq_tur_hatasi", hata=f"{type(e).__name__}: {e}"[:300])
        time.sleep(dongu_sn)
