"""Kilit açılımı kolu — paper düğümü (Dalga 6b, karar A). Nautilus dışı ayrı süreç (compose `kilit`).

Akış (her tur ~60 sn; `tur()` kaldığı yerden devam eder, yeniden başlatmada çift işlem olmaz):
- Saat başı: funding tahakkuku (Binance `fundingRate` geçmişi, gerçekleşen oranlar) → işaret fiyatıyla özkaynak işareti
  (`paper_ozkaynak`, kalp atışı). Kol durdurulduysa, acil durdurma eşiği aşıldıysa ya da tutulan perp artık işlem
  görmüyorsa pozisyonlar hemen kapanır (riski azaltan her şey otomatik, kural 7).
- Günde bir (00:05 UTC'den sonra, gün başına bir karar): DefiLlama takviminin o anki hali ham depoya yazılır (hash =
  kimlik, point-in-time) → `cekirdek.kilit.gun_karari` (backtest ile aynı fonksiyon, kural 3) → karar emirden ÖNCE
  deftere → her bacak risk motorundan geçer (kural 5) → dolum.

Yürütme (paper, aleyhte): alış ask'tan, satış bid'den, üstüne kayma (token %0,1, BTC %0,01) ve taker ücreti %0,05
(Dalga 6 maliyet modeli). `karar_fiyati` günün 00:00 açılışıdır (backtest'in dolum fiyatı); gönderim anındaki orta fiyat
ayrıca yazılır, fark gecikme maliyeti olarak ölçülür.

Bacak tutarlılığı: önce token kısa, sonra aynı nominalde BTC uzun. BTC bacağı reddedilir ya da kırpılırsa token bacağı
BTC'ye eşitlenene kadar geri alınır (riski azaltır; açıkta tek bacak kalmaz).

Takvim alınamazsa gün yalnız kapanışlarla kararlanır (yeni olay yok): belirsizlikte riski azalt (kural 8'in ilkesi).
Jev bu kolda yok (v1): kural takvimden, yön kararı Jev'e verdirilmez; veto entegrasyonu sonraki iş.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import insert, select
from sqlalchemy.engine import Engine

from tradebot import denetim
from tradebot.arastirma import kilit as kl
from tradebot.arastirma.turnuva import Ayar
from tradebot.canli.defter import PaperDefter
from tradebot.canli.karar import KolDurum
from tradebot.canli.kollar import PaperKol, oku
from tradebot.cekirdek import kilit as ck
from tradebot.db import paper_emir, paper_emir_olay, paper_karar, paper_ozkaynak
from tradebot.kayit import log
from tradebot.risk.motor import Durum, EmirIstegi, Piyasa, Portfoy, PortfoyIzleyici, RiskAyar, RiskMotoru
from tradebot.veri import binance_vadeli as bv
from tradebot.veri import kilit as vk

KILIT = "kilit_kisa"
DUGUM = "kilit"
ONEK = "BINANCEF:"
BTC = "BTC"
SINIF = "kripto_perp"
GUN_MS = ck.GUN_MS
SAAT_MS = 3_600_000
KARAR_GECIKME_MS = 5 * 60_000          # 00:05 UTC: günlük mum kesinleşmiş, takvim güncel
TAKVIM_SABIR_MS = 30 * 60_000          # takvim bu süre içinde alınamazsa gün yalnız kapanışlarla kararlanır
GECIKMELI_MS = 30 * 60_000             # 00:30'dan sonra verilen karar "gecikmeli" (maliyet ölçümünde ayrılır)
FAPI = bv.FAPI
_log = log("kilit")


@dataclass(frozen=True)
class Maliyet:
    ucret: float = 0.0005
    kayma_token: float = 0.001
    kayma_btc: float = 0.0001


@dataclass(frozen=True)
class KilitAyarlari:
    kol: PaperKol
    kural: ck.KilitKural
    maliyet: Maliyet
    kategoriler: tuple[str, ...]
    asgari_oran: float
    risk: RiskAyar


def ayarlar(d: dict | None = None) -> KilitAyarlari | None:
    """`config/paper.yaml` `kilit` bloğu → kol + kural. Blok yoksa None (düğüm çalışmaz)."""
    d = d or oku()
    b = d.get("kilit")
    if not b:
        return None
    risk = RiskAyar(kaldirac=float(b["risk"]["kaldirac"]))
    kr = b["kural"]
    kural = ck.KilitKural(int(kr["giris"]), int(kr["cikis"]), float(kr["notional"]),
                          azami_brut=risk.kaldirac, azami_btc=risk.enstruman_tavani)
    ayar = Ayar(hedef_vol=0.0, kaldirac=risk.kaldirac, vol_pencere_gun=0, frenler=bool(d.get("frenler", True)), bant=0.0)
    kol = PaperKol(b["ad"], KILIT, "kilit_perp", {"dugum": DUGUM, "yon": "kisa_notr", "kimlikler": [f"{ONEK}*USDT"],
                                                 "olay": b["olay"], "maliyet": b["maliyet"]},
                   "1d", ayar, {"giris": kural.giris, "cikis": kural.cikis, "notional": kural.notional,
                                "azami_brut": kural.azami_brut, "azami_btc": kural.azami_btc},
                   b.get("sinif", "A"), float(d.get("baslangic_ozkaynak", 100_000)))
    return KilitAyarlari(kol, kural, Maliyet(**b["maliyet"]), tuple(b["olay"]["kategoriler"]),
                         float(b["olay"]["asgari_oran"]), risk)


# ---------------------------------------------------------------------------------------------------- borsa (okuma)
class Borsa:
    """Binance USDT-M herkese açık uçları (anahtarsız, yalnız okuma). `http_al(url) -> bytes`."""

    def __init__(self, http_al: Callable[[str], bytes], ham=None) -> None:
        self.al, self.ham = http_al, ham

    def perpler(self, kaydet: bool = False) -> dict[str, dict]:
        return bv.usdt_perpler(self.al, self.ham if kaydet else None)

    def kotasyon(self) -> dict[str, tuple[float, float]]:
        return {x["symbol"]: (float(x["bidPrice"]), float(x["askPrice"]))
                for x in json.loads(self.al(f"{FAPI}/ticker/bookTicker"))}

    def isaret(self) -> dict[str, float]:
        return {x["symbol"]: float(x["markPrice"]) for x in json.loads(self.al(f"{FAPI}/premiumIndex"))}

    def gun_acilisi(self, sembol: str, gun_ms: int) -> float | None:
        r = json.loads(self.al(f"{FAPI}/klines?symbol={sembol}&interval=1d&startTime={gun_ms}&limit=1"))
        return float(r[0][1]) if r and int(r[0][0]) == gun_ms else None

    def funding(self, sembol: str, bas_ms: int) -> list[tuple[int, float, float]]:
        r = json.loads(self.al(f"{FAPI}/fundingRate?symbol={sembol}&startTime={bas_ms}&limit=1000"))
        return [(int(x["fundingTime"]), float(x["fundingRate"]), float(x.get("markPrice") or 0)) for x in r]

    def takvim(self, gun_ms: int) -> tuple[bytes, str]:
        icerik = self.al(vk.URL)
        sha = self.ham.kaydet("defillama", f"unlocks/gunluk/{gun_ms}", icerik, "html")[1] if self.ham else ""
        return icerik, sha


# ---------------------------------------------------------------------------------------------------- durum
@dataclass
class Durum_:
    nakit: float
    adet: dict[str, float]                          # enstrüman → adet (net)
    acik: list[ck.Pozisyon]
    bacak: dict[tuple[str, int], dict[str, float]]  # (sembol, olay_ms) → {"token": adet, "btc": adet, "perp": kimlik}
    son_fonlama: dict[str, int]                     # enstrüman → son tahakkuk edilen funding zamanı
    gecmis: list[tuple[int, float]]                 # özkaynak işaretleri
    durdurulmus: bool
    kararlar: dict[int, int] = field(default_factory=dict)   # gün → karar id
    son_fiyat: dict[str, float] = field(default_factory=dict)  # son işaretteki fiyatlar (kotasyon yoksa yedek)

    def ozkaynak(self, fiyat: dict[str, float]) -> float:
        return self.nakit + sum(a * fiyat[k] for k, a in self.adet.items() if abs(a) > 1e-12)


def durum_kur(defter: PaperDefter, kol: str, baslangic: float) -> Durum_:
    """Kol durumu defterden (dolum + fonlama + işaret + kol olayları). Pozisyonlar dolumların etiketinden kurulur;
    enstrümanın net adedi sıfırsa (gözetmen kapattı) o olay kapalı sayılır."""
    m = defter.motor
    with m.connect() as b:
        olay = list(b.execute(select(paper_emir_olay.c.tur, paper_emir_olay.c.enstruman, paper_emir_olay.c.miktar,
                                     paper_emir_olay.c.fiyat, paper_emir_olay.c.ucret, paper_emir_olay.c.ayrinti)
                              .where(paper_emir_olay.c.kol == kol, paper_emir_olay.c.tur.in_(("dolum", "fonlama")))
                              .order_by(paper_emir_olay.c.id)))
        isaretler = list(b.execute(select(paper_ozkaynak.c.zaman_ms, paper_ozkaynak.c.ozkaynak, paper_ozkaynak.c.fiyat)
                                   .where(paper_ozkaynak.c.kol == kol).order_by(paper_ozkaynak.c.zaman_ms)))
        kararlar = {int(g): int(i) for g, i in b.execute(select(paper_karar.c.bar_ms, paper_karar.c.id)
                                                            .where(paper_karar.c.kol == kol))}
    gecmis = [(int(t), float(o)) for t, o, _ in isaretler]
    nakit, adet = baslangic, defaultdict(float)
    bacak: dict[tuple[str, int], dict] = {}
    meta: dict[tuple[str, int], dict] = {}
    son_fon: dict[str, int] = {}
    for tur, kim, q, p, u, ay in olay:
        ay = ay or {}
        if tur == "fonlama":
            nakit -= u
            son_fon[kim] = max(son_fon.get(kim, 0), int(ay.get("funding_ms", 0)))
            continue
        adet[kim] += q
        nakit -= q * p + u
        if "olay_ms" in ay:
            a = (ay["sembol"], int(ay["olay_ms"]))
            b_ = bacak.setdefault(a, {"token": 0.0, "btc": 0.0, "perp": ay.get("perp")})
            b_[ay["bacak"]] += q
            if ay.get("islem") == "ac":
                meta.setdefault(a, {"giris_ms": int(ay["gun_ms"]), "cikis_ms": int(ay["cikis_ms"]),
                                    "notional": float(ay["notional"])})
    acik = []
    for a, b_ in bacak.items():
        if abs(b_["token"]) > 1e-12 and a in meta and abs(adet.get(b_["perp"], 0.0)) > 1e-12:
            acik.append(ck.Pozisyon(a[0], a[1], meta[a]["giris_ms"], meta[a]["cikis_ms"], meta[a]["notional"]))
    son_elle = None
    for o in defter.kol_olaylari(kol):
        if o.tur == "devam" or (o.tur == "durdur" and o.ayrinti.get("neden") != "mutabakat"):
            son_elle = o.tur
    return Durum_(nakit, {k: v for k, v in adet.items() if abs(v) > 1e-12}, acik, bacak, son_fon, gecmis,
                  son_elle == "durdur", kararlar, dict(isaretler[-1][2] or {}) if isaretler else {})


def izleyici(gecmis: list[tuple[int, float]], baslangic: float, risk: RiskAyar) -> tuple[PortfoyIzleyici, Durum]:
    """Fren durumu özkaynak geçmişinden (kol düzeyi, gözlem kolları gibi acil kalıcı değil). Döndürür: (izleyici, son
    işaretteki geçiş: ACIL_DURDURMA ise pozisyonlar o işarette kapatılmalıdır)."""
    iz = PortfoyIzleyici(risk, baslangic_ms=gecmis[0][0] if gecmis else 0, acil_kalici=False)
    son = Durum.NORMAL
    for t, oz in gecmis:
        son = iz.guncelle(oz / baslangic, t)
    return iz, son


# ---------------------------------------------------------------------------------------------------- düğüm
class KilitDugumu:
    def __init__(self, defter: PaperDefter, ay: KilitAyarlari, borsa: Borsa, saat: Callable[[], float] = time.time):
        self.defter, self.ay, self.borsa, self.saat = defter, ay, borsa, saat
        self.m: Engine = defter.motor
        self.kol = ay.kol
        self.risk = RiskMotoru(ay.risk)
        self._takvim_hatasi: dict[int, int] = {}

    def ac(self) -> None:
        if self.defter.kol_ac(self.kol, int(self.saat() * 1000)):
            _log.info("kol_acildi", kol=self.kol.ad)

    # ------------------------------------------------------------------ tur
    def tur(self) -> dict:
        simdi = int(self.saat() * 1000)
        d = durum_kur(self.defter, self.kol.ad, self.kol.baslangic_ozkaynak)
        out: dict = {}
        saat_bas = simdi // SAAT_MS * SAAT_MS
        if not d.gecmis or d.gecmis[-1][0] < saat_bas:
            out["isaret"] = self._saatlik(d, saat_bas)
            d = durum_kur(self.defter, self.kol.ad, self.kol.baslangic_ozkaynak)
        gun = simdi // GUN_MS * GUN_MS
        if gun in d.kararlar:
            devam = self._devam(d, gun, d.kararlar[gun])
            if devam:
                out["devam"] = devam
        elif simdi - gun >= KARAR_GECIKME_MS and gun >= self._ilk_gun():
            out["karar"] = self._gunluk(d, gun, simdi)
        return out

    def _ilk_gun(self) -> int:
        """İlk karar günü: kol gün içinde geç açıldıysa ertesi gün (giriş günün açılışında varsayılır, backtest gibi)."""
        b = self.defter.kol_baslangic(self.kol.ad) or 0
        return b // GUN_MS * GUN_MS + (GUN_MS if b % GUN_MS > GECIKMELI_MS else 0)

    def _devam(self, d: Durum_, gun: int, karar_id: int) -> dict | None:
        """Karar yazılıp emirleri tamamlanmadan süreç durduysa (yeniden başlatma) eksik kalan emirler: planlanan
        kapanışlardan hâlâ açık olanlar, planlanan açılışlardan hiç emri olmayanlar. Emir kimliği tekildir."""
        with self.m.connect() as b:
            ayr = b.execute(select(paper_karar.c.ayrinti).where(paper_karar.c.id == karar_id)).scalar() or {}
            ids = set(b.execute(select(paper_emir.c.istemci_emir_id).where(paper_emir.c.karar_id == karar_id)).scalars())
        acik = {p.anahtar: p for p in d.acik}
        kapat = [(acik[(x["sembol"], int(x["olay_ms"]))], x.get("neden", "cikis")) for x in ayr.get("kapat", [])
                 if (x["sembol"], int(x["olay_ms"])) in acik]
        ac = [ck.Pozisyon(x["sembol"], int(x["olay_ms"]), int(x["giris_ms"]), int(x["cikis_ms"]), float(x["notional"]))
              for x in ayr.get("ac", []) if _istemci(gun, x["sembol"], int(x["olay_ms"]), "ac", "token") not in ids]
        if not kapat and not ac:
            return None
        _log.warning("kilit_karar_devam", gun=gun, kapat=len(kapat), ac=len(ac))
        return self._yurut(d, karar_id, gun, kapat, ac, self.borsa.perpler())

    # ------------------------------------------------------------------ saatlik
    def _saatlik(self, d: Durum_, saat_bas: int) -> dict:
        perp = self.borsa.perpler()
        isaret = self.borsa.isaret()
        fon = self._fonlama(d, perp)
        d = durum_kur(self.defter, self.kol.ad, self.kol.baslangic_ozkaynak) if fon else d
        fiyat = {k: isaret.get(k[len(ONEK):], d.son_fiyat.get(k, 0.0)) for k in d.adet}
        oz = d.ozkaynak(fiyat)
        self.defter.ozkaynak_yaz(self.kol.ad, saat_bas, KolDurum(oz, d.nakit, dict(d.adet)), fiyat)
        _, gecis = izleyici(d.gecmis + [(saat_bas, oz)], self.kol.baslangic_ozkaynak, self.ay.risk)
        neden = "durdur" if d.durdurulmus else ("acil_durdurma" if gecis == Durum.ACIL_DURDURMA else None)
        kapat = [(p, neden) for p in d.acik] if neden else \
            [(p, "islem_gormuyor") for p in d.acik if perp.get(p.sembol, {}).get("durum") != "TRADING"]
        if kapat:
            self._yurut(d, None, saat_bas // GUN_MS * GUN_MS, kapat, [], perp)
            if neden == "acil_durdurma":
                denetim.kaydet(self.m, "kilit", "acil_durdurma_kapatma", {"kol": self.kol.ad, "ozkaynak": oz})
        return {"ozkaynak": round(oz, 2), "fonlama": fon, "kapatilan": [(p.sembol, n) for p, n in kapat]}

    def _fonlama(self, d: Durum_, perp: dict[str, dict]) -> int:
        """Tutulan her enstrümanın gerçekleşen funding'i (8 saatte bir). Nakit etkisi = −adet × işaret × oran
        (uzun pozitif oranda öder, kısa alır). Adet, funding anındaki net adettir (dolum zamanlarından)."""
        n = 0
        if not d.adet:
            return 0
        with self.m.connect() as b:
            dolum = [(kim, int(t), float(q)) for kim, t, q in b.execute(
                select(paper_emir_olay.c.enstruman, paper_emir_olay.c.zaman_ms, paper_emir_olay.c.miktar)
                .where(paper_emir_olay.c.kol == self.kol.ad, paper_emir_olay.c.tur == "dolum"))]
        for kim in sorted(d.adet):
            ilk = min(t for k, t, _ in dolum if k == kim)
            bas = max(d.son_fonlama.get(kim, 0) + 1, ilk)
            for t, oran, px in self.borsa.funding(kim[len(ONEK):], bas):
                if t <= d.son_fonlama.get(kim, 0) or t < ilk:
                    continue
                a = sum(q for k, tt, q in dolum if k == kim and tt <= t)
                if abs(a) < 1e-12 or px <= 0:
                    continue
                nakit_etkisi = -a * px * oran
                self.defter.olay_yaz(0, self.kol.ad, "fonlama", kim, 0.0, px, -nakit_etkisi, t,
                                     {"funding_ms": t, "oran": oran, "adet": a})
                n += 1
        return n

    # ------------------------------------------------------------------ günlük
    def _gunluk(self, d: Durum_, gun: int, simdi: int) -> dict:
        perp = self.borsa.perpler(kaydet=True)
        if perp.get(BTC, {}).get("durum") != "TRADING":
            _log.error("btc_perp_islem_gormuyor", gun=gun)
            return {"hata": "BTC perp işlem görmüyor"}
        olaylar, sha, takvim_hatasi = [], "", None
        try:
            icerik, sha = self.borsa.takvim(gun)
            ev = kl.olaylar(vk.coz(icerik), list(self.ay.kategoriler), self.ay.asgari_oran)
            olaylar = [ck.Olay(s, int(t), float(o)) for s, t, o in ev.select("sembol", "gun_ms", "oran").iter_rows()
                       if int(t) >= gun]
        except Exception as e:  # noqa: BLE001 — takvim yoksa yalnız kapanış
            ilk = self._takvim_hatasi.setdefault(gun, simdi)
            takvim_hatasi = f"{type(e).__name__}: {e}"[:200]
            if simdi - ilk < TAKVIM_SABIR_MS:
                _log.warning("takvim_alinamadi", hata=takvim_hatasi)
                return {"bekliyor": takvim_hatasi}
            _log.error("takvim_yok_yalniz_kapanis", hata=takvim_hatasi)
        iz, _ = izleyici(d.gecmis, self.kol.baslangic_ozkaynak, self.ay.risk)
        islem = {s for s, v in perp.items() if v.get("durum") == "TRADING"}
        k = ck.gun_karari(gun, olaylar, d.acik, islem, self.ay.kural, yeni_risk=iz.durum == Durum.NORMAL
                          and takvim_hatasi is None, hepsini_kapat=d.durdurulmus)
        ayr = {"tur": KILIT, "takvim_sha": sha, "takvim_hatasi": takvim_hatasi, "gecikmeli": simdi - gun > GECIKMELI_MS,
               "olay_sayisi": len(olaylar), "veto": [],
               "kapat": [_poz(p) | {"neden": n} for p, n in k.kapat], "ac": [_poz(p) for p in k.ac],
               "red": [{"sembol": o.sembol, "olay_ms": o.gun_ms, "oran": o.oran, "neden": n} for o, n in k.red],
               "acik_once": [_poz(p) for p in d.acik]}
        with self.m.begin() as b:
            kid = int(b.execute(insert(paper_karar).values(
                kol=self.kol.ad, bar_ms=gun, karar_ms=int(self.saat() * 1000), kod_surumu=self.defter.kod,
                veri_hash=(sha or "takvim_yok")[:64], durum=iz.durum.value, ayrinti=ayr)).inserted_primary_key[0])
        sonuc = self._yurut(d, kid, gun, list(k.kapat), list(k.ac), perp)
        _log.info("kilit_karar", gun=gun, kapat=len(k.kapat), ac=len(k.ac), red=len(k.red), durum=iz.durum.value)
        return {"karar_id": kid, "kapat": len(k.kapat), "ac": len(k.ac), "red": len(k.red), **sonuc}

    # ------------------------------------------------------------------ yürütme
    def _yurut(self, d: Durum_, karar_id: int | None, gun: int, kapat: list[tuple[ck.Pozisyon, str]],
               ac: list[ck.Pozisyon], perp: dict[str, dict]) -> dict:
        kot = self.borsa.kotasyon()
        isaret = self.borsa.isaret()
        adet = dict(d.adet)
        fiyat = {f"{ONEK}{v['sembol']}": isaret[v["sembol"]] for v in perp.values() if v["sembol"] in isaret}
        fiyat |= {k: d.son_fiyat.get(k, 0.0) for k in adet if k not in fiyat}
        iz, _ = izleyici(d.gecmis, self.kol.baslangic_ozkaynak, self.ay.risk)
        pf = Portfoy(d.ozkaynak(fiyat), adet, fiyat, {k: SINIF for k in fiyat}, iz.durum,
                     {self.kol.ad} if d.durdurulmus else set())
        btc = f"{ONEK}{perp[BTC]['sembol']}"
        acilis: dict[str, float | None] = {}

        def ref(kim: str) -> float:
            if kim not in acilis:
                try:
                    acilis[kim] = self.borsa.gun_acilisi(kim[len(ONEK):], gun)
                except Exception:  # noqa: BLE001 — referans yalnız ölçüm içindir
                    acilis[kim] = None
            return acilis[kim] or sum(kot[kim[len(ONEK):]]) / 2

        out = {"dolum": 0, "ret": []}
        for p, neden in kapat:
            b_ = d.bacak.get(p.anahtar, {})
            for bacak, kim in (("token", b_.get("perp")), ("btc", btc)):
                q = -b_.get(bacak, 0.0)
                if kim and abs(q) > 1e-12:
                    self._emir(karar_id, pf, kim, q, p, bacak, "kapat", gun, kot, ref(kim), perp, out, neden)
        for p in ac:
            v = perp[p.sembol]
            kim = f"{ONEK}{v['sembol']}"
            bid = kot[v["sembol"]][0]
            q_t = -_yuvarla(p.notional * pf.ozkaynak / bid, v.get("adim", 0.0))
            if q_t == 0 or abs(q_t) * bid < v.get("asgari_notional", 0.0):
                out["ret"].append({"sembol": p.sembol, "neden": "lot/asgari notional"})
                continue
            t = self._emir(karar_id, pf, kim, q_t, p, "token", "ac", gun, kot, ref(kim), perp, out)
            if not t:
                continue
            ask_b = kot[perp[BTC]["sembol"]][1]
            q_b = _yuvarla(abs(t[0]) * t[1] / ask_b, perp[BTC].get("adim", 0.0))
            b = self._emir(karar_id, pf, btc, q_b, p, "btc", "ac", gun, kot, ref(btc), perp, out) if q_b > 0 else None
            fark = abs(t[0]) * t[1] - (abs(b[0]) * b[1] if b else 0.0)
            if fark > 0.01 * abs(t[0]) * t[1]:   # BTC bacağı eksik: token bacağını eşitle (riski azaltır)
                geri = _yuvarla(fark / kot[v["sembol"]][1], v.get("adim", 0.0))
                if b is None:
                    geri = abs(t[0])
                if geri > 0:
                    self._emir(karar_id, pf, kim, min(geri, abs(t[0])), p, "token", "geri", gun, kot, ref(kim), perp,
                               out)
        return out

    def _emir(self, karar_id, pf: Portfoy, kim: str, q: float, p: ck.Pozisyon, bacak: str, islem: str, gun: int,
              kot, karar_fiyati: float, perp, out: dict, neden: str | None = None) -> tuple[float, float] | None:
        s = kim[len(ONEK):]
        bid, ask = kot[s]
        on = ask if q > 0 else bid
        eid_ist = _istemci(gun, p.sembol, p.olay_ms, islem, bacak)
        ist = EmirIstegi(kim, SINIF, q, on, self.kol.ad, int(self.saat() * 1000), eid_ist)
        taban = next((t for t, v in perp.items() if v["sembol"] == s), None)
        piy = Piyasa(pf.fiyatlar.get(kim, (bid + ask) / 2), int(self.saat() * 1000), 60_000, True,
                     float(perp.get(taban, {}).get("adim", 0.0) or 0.0))
        r = self.risk.onayla(ist, piy, pf)
        risk = {"onay": r.onay, "gerekceler": list(r.gerekceler), "risk_azaltan": r.risk_azaltan}
        eid = self.defter.emir_yaz(self.kol.ad, karar_id, eid_ist, kim, q, r.miktar if r.onay else 0.0, karar_fiyati,
                                   "karar", risk, gonderim_fiyati=(bid + ask) / 2)
        if not r.onay or abs(r.miktar) < 1e-12:
            self.defter.olay_yaz(eid, self.kol.ad, "ret", kim, q, None, 0.0, int(self.saat() * 1000),
                                 {"gerekceler": list(r.gerekceler)})
            out["ret"].append({"sembol": p.sembol, "bacak": bacak, "gerekce": list(r.gerekceler)})
            return None
        m = r.miktar
        kayma = self.ay.maliyet.kayma_btc if bacak == "btc" else self.ay.maliyet.kayma_token
        px = ask * (1 + kayma) if m > 0 else bid * (1 - kayma)
        ucret = abs(m) * px * self.ay.maliyet.ucret
        self.defter.olay_yaz(eid, self.kol.ad, "dolum", kim, m, px, ucret, int(self.saat() * 1000),
                             {"sembol": p.sembol, "olay_ms": p.olay_ms, "gun_ms": gun, "cikis_ms": p.cikis_ms,
                              "notional": p.notional, "bacak": bacak, "islem": islem, "perp": f"{ONEK}{s}"
                              if bacak == "token" else None, "neden": neden, "bid": bid, "ask": ask,
                              "gecikmeli": False})
        pf.pozisyonlar[kim] = pf.pozisyonlar.get(kim, 0.0) + m
        out["dolum"] += 1
        return m, px


def _istemci(gun: int, sembol: str, olay_ms: int, islem: str, bacak: str) -> str:
    """Tekil emir kimliği: gün + olay + işlem (Aç/Kapat/Geri) + bacak (Token/Btc)."""
    return f"KL{gun // GUN_MS}-{sembol}-{olay_ms // GUN_MS}-{islem[0].upper()}{bacak[0].upper()}"[:64]


def _poz(p: ck.Pozisyon) -> dict:
    return {"sembol": p.sembol, "olay_ms": p.olay_ms, "giris_ms": p.giris_ms, "cikis_ms": p.cikis_ms,
            "notional": p.notional}


def _yuvarla(x: float, adim: float) -> float:
    if adim <= 0:
        return x
    import math
    return round(math.floor(x / adim + 1e-9) * adim, 12)


def calistir(sure_sn: float | None = None, dongu_sn: float = 60.0) -> None:
    """compose `kilit` servisi: her `dongu_sn`'de bir tur. Hata turu atlar (log), bir sonraki tur yeniden dener."""
    import os

    from tradebot.ayar import ayarlar as sistem
    from tradebot.db import motor as db_motor
    from tradebot.veri.depo import HamDepo
    from tradebot.veri.http import NazikIstemci

    ay = ayarlar()
    if ay is None:
        raise SystemExit("config/paper.yaml içinde `kilit` bloğu yok")
    a = sistem()
    m = db_motor(a)
    defter = PaperDefter(m, os.environ.get("TRADEBOT_KOD_SURUMU", "yerel"))
    dugum = KilitDugumu(defter, ay, Borsa(NazikIstemci("kilit", deneme=3, zaman_asimi=60).al, HamDepo(a.veri_dizini, m)))
    dugum.ac()
    bas = time.monotonic()
    while sure_sn is None or time.monotonic() - bas < sure_sn:
        try:
            r = dugum.tur()
            if r:
                _log.info("kilit_tur", **{k: v for k, v in r.items() if k != "isaret"}, isaret=r.get("isaret"))
        except Exception as e:  # noqa: BLE001
            _log.error("kilit_tur_hatasi", hata=f"{type(e).__name__}: {e}"[:300])
        time.sleep(dongu_sn)

