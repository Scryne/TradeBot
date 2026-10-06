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

Planlı kapanış (delist) koruması: Binance perp'in kaldırılacağını duyurunca `deliveryDate`'i kapanış anına çeker. Böyle
bir perp "işlem görmüyor" sayılır: yeni olay açılmaz, açık pozisyon ilk saat başında kapanır (`teslim_planli`; riski
azaltan, kural 7). Bu bir kural, yargı değil: kodda durur.
Jev bu kolda yok (2026-10-01 ölçümü): 596 geçmiş olayın giriş penceresinde tokenı anan 23 Binance duyurusunun hiçbiri
USDT perp tutanı etkilemiyordu (USDT dışı çiftler, marjin). Jev'li ikiz kol Jev'sizin kopyası olurdu, katkı ölçülemezdi.
"""
from __future__ import annotations

import json
import time
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import func, insert, select
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
YENIDEN_ARALIK_MS = 10 * 60_000        # gerçek kolda borsa hatasıyla düşen emir en erken bu kadar sonra yeniden denenir
YENIDEN_SON_MS = 6 * SAAT_MS           # açılış yalnız günün 06:00 UTC'sine kadar (backtest girişi açılışta)
YENIDEN_AZAMI = 3                      # açılış başına en çok yeniden deneme
NAKIT_GELIRI = {"FUNDING_FEE", "SPECIAL_FUNDING_FEE", "COMMISSION", "COMMISSION_REBATE", "INSURANCE_CLEAR"}   # gerçek kol nakdi
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
    gercek: dict | None = None     # gerçek kol: {"ortam": demo|ana, "sermaye": USDT, "onay": "..."}


GERCEK_SERMAYE_TAVANI = 2_000.0    # USDT; kodda sabit. Yükseltmek riski artırır: Scryne'ın açık onayı (kural 7)
GERCEK_BLOK = "kilit_gercek"


def ayarlar(d: dict | None = None, blok: str = "kilit") -> KilitAyarlari | None:
    """`config/paper.yaml` `kilit` bloğu → kol + kural. Blok yoksa None (düğüm çalışmaz).
    `blok="kilit_gercek"`: aynı kural, ayrı kol ve düğüm; gerçek emir. Ana ağ `onay` ister, sermaye tavanı kodda."""
    d = d or oku()
    b = d.get("kilit")
    if not b or (blok != "kilit" and not d.get(blok)):
        return None
    gercek = None
    if blok != "kilit":
        g = d[blok]
        b = b | {k: v for k, v in g.items() if k in ("ad", "sinif")}
        gercek = {"ortam": str(g["ortam"]), "sermaye": float(g["sermaye"]), "onay": str(g.get("onay") or "").strip()}
        if gercek["ortam"] not in ("demo", "ana"):
            raise ValueError(f"{blok}.ortam demo|ana olmalı")
        if not 0 < gercek["sermaye"] <= GERCEK_SERMAYE_TAVANI:
            raise ValueError(f"{blok}.sermaye (0, {GERCEK_SERMAYE_TAVANI}] USDT olmalı (kodda sabit tavan, kural 7)")
        if gercek["ortam"] == "ana" and not gercek["onay"]:
            raise ValueError(f"{blok}: gerçek paraya geçiş Scryne'ın açık onayını ister (`onay` boş; kural 7)")
    risk = RiskAyar(kaldirac=float(b["risk"]["kaldirac"]))
    kr = b["kural"]
    kural = ck.KilitKural(int(kr["giris"]), int(kr["cikis"]), float(kr["notional"]),
                          azami_brut=risk.kaldirac, azami_btc=risk.enstruman_tavani)
    ayar = Ayar(hedef_vol=0.0, kaldirac=risk.kaldirac, vol_pencere_gun=0, frenler=bool(d.get("frenler", True)), bant=0.0)
    grup = {"dugum": DUGUM if gercek is None else blok, "yon": "kisa_notr", "kimlikler": [f"{ONEK}*USDT"],
            "olay": b["olay"], "maliyet": b["maliyet"]} | ({"ortam": gercek["ortam"]} if gercek else {})
    kol = PaperKol(b["ad"], KILIT, "kilit_perp", grup,
                   "1d", ayar, {"giris": kural.giris, "cikis": kural.cikis, "notional": kural.notional,
                                "azami_brut": kural.azami_brut, "azami_btc": kural.azami_btc},
                   b.get("sinif", "A"), gercek["sermaye"] if gercek else float(d.get("baslangic_ozkaynak", 100_000)))
    return KilitAyarlari(kol, kural, Maliyet(**b["maliyet"]), tuple(b["olay"]["kategoriler"]),
                         float(b["olay"]["asgari_oran"]), risk, gercek)


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


# ---------------------------------------------------------------------------------------------------- yürütücüler
@dataclass(frozen=True)
class Dolum:
    adet: float          # işaretli gerçekleşen adet
    fiyat: float
    ucret: float         # paper: modelden; gerçek: 0 (komisyon borsanın gelir kaydından ayrıca yazılır)
    ek: dict


class PaperYurutucu:
    """Paper dolum (aleyhte): alış ask'tan, satış bid'den, üstüne kayma ve taker ücreti. Olay başına BTC bacağı."""
    gercek = False
    net_btc = False
    onek = "KL"          # istemci emir kimliği öneki (kimlik tablo genelinde tekil: kollar çakışmasın)

    def __init__(self, maliyet: Maliyet) -> None:
        self.maliyet = maliyet

    def doldur(self, sembol: str, m: float, bid: float, ask: float, bacak: str, istemci_id: str,
               azaltan: bool) -> Dolum | str:
        kayma = self.maliyet.kayma_btc if bacak.startswith("btc") else self.maliyet.kayma_token
        px = ask * (1 + kayma) if m > 0 else bid * (1 - kayma)
        return Dolum(m, px, abs(m) * px * self.maliyet.ucret, {})


class GercekYurutucu:
    """Binance USDT-M piyasa emri (`canli/binance_emir.VadeliIstemci`). Küçük sermayede BTC bacağı olay başına
    yuvarlanamadığı için BTC korumasını netler (`net_btc`). Funding ve komisyon borsanın gelir kaydından okunur."""
    gercek = True
    net_btc = True
    onek = "KG"

    def __init__(self, istemci) -> None:
        self.ist = istemci

    def doldur(self, sembol: str, m: float, bid: float, ask: float, bacak: str, istemci_id: str,
               azaltan: bool) -> Dolum | str:
        r = self.ist.emir(sembol, m, istemci_id, azaltan)
        if abs(r["adet"]) < 1e-12:
            return f"borsa: {r.get('durum', 'dolmadı')}"
        return Dolum(r["adet"], r["fiyat"], 0.0, {"borsa_emir": r.get("emir_id"), "durum": r.get("durum")})

    def islemde(self) -> set[str] | None:
        """Emrin gideceği ortamda işlem gören semboller; okunamazsa None (o gün yeni olay açılmaz)."""
        try:
            return self.ist.islemde()
        except Exception as e:  # noqa: BLE001
            _log.warning("ortam_sembolleri_okunamadi", hata=f"{type(e).__name__}: {e}"[:200])
            return None


# ---------------------------------------------------------------------------------------------------- düğüm
class KilitDugumu:
    def __init__(self, defter: PaperDefter, ay: KilitAyarlari, borsa: Borsa, saat: Callable[[], float] = time.time,
                 yurutucu: PaperYurutucu | GercekYurutucu | None = None):
        self.defter, self.ay, self.borsa, self.saat = defter, ay, borsa, saat
        self.m: Engine = defter.motor
        self.kol = ay.kol
        self.risk = RiskMotoru(ay.risk)
        self.yurutucu = yurutucu or PaperYurutucu(ay.maliyet)
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
        """Günün kararından eksik kalan emirler. (1) Yeniden başlatma: karar yazılıp emirleri tamamlanmadan süreç
        durduysa planlanan kapanışlardan hâlâ açık olanlar, açılışlardan hiç emri olmayanlar. (2) Gerçek kolda borsa
        hatası: daha önce denenmiş kalem yalnız bütün denemeleri borsa düzeyinde düştüyse (`hata:` / `borsa:`, risk
        reddi değil), `YENIDEN_ARALIK_MS` arayla yeniden denenir. Açılış en çok `YENIDEN_AZAMI` kez ve günün
        `YENIDEN_SON_MS`'ine kadar, yalnız borsada o perp'te pozisyon yokken (belirsiz hata emri gerçekleştirmiş
        olabilir; o durumda mutabakat yakalar). Kapanış riski azaltır: sınırsız, borsada pozisyon durdukça."""
        simdi = int(self.saat() * 1000)
        with self.m.connect() as b:
            ayr = b.execute(select(paper_karar.c.ayrinti).where(paper_karar.c.id == karar_id)).scalar() or {}
            emirler = list(b.execute(select(paper_emir.c.id, paper_emir.c.istemci_emir_id)
                                     .where(paper_emir.c.karar_id == karar_id)))
            olaylar: dict[int, list] = defaultdict(list)     # emir → [(tür, ayrıntı, zaman)]; zaman düğüm saatiyle
            for eid, tur, a, z in b.execute(select(paper_emir_olay.c.emir_id, paper_emir_olay.c.tur,
                                                   paper_emir_olay.c.ayrinti, paper_emir_olay.c.zaman_ms)
                                            .where(paper_emir_olay.c.emir_id.in_([e.id for e in emirler] or [-1]))):
                olaylar[int(eid)].append((tur, a or {}, int(z)))
        acik = {p.anahtar: p for p in d.acik}
        perp: dict[str, dict] = {}
        borsa: dict[str, float] | None = None

        def denemeler(x: dict, islem: str) -> list:
            t = _istemci(gun, x["sembol"], int(x["olay_ms"]), islem, "token", self.yurutucu.onek)
            return [e for e in emirler if e.istemci_emir_id == t or e.istemci_emir_id.startswith(f"{t[:33]}R")]

        def borsa_hatasi(e) -> bool:
            o = olaylar.get(int(e.id), [])
            return bool(o) and all(t == "ret" and any(str(g).startswith(("hata:", "borsa:")) for g in a.get("gerekceler", []))
                                   for t, a, _ in o)

        def borsada(sembol: str) -> bool:
            nonlocal perp, borsa
            perp = perp or self.borsa.perpler()
            borsa = self.yurutucu.ist.pozisyonlar() if borsa is None else borsa
            return abs(borsa.get(perp.get(sembol, {}).get("sembol", ""), 0.0)) > 1e-12

        def tekrar(dn: list, son: bool) -> bool:
            son_ret = max(z for e in dn for _, _, z in olaylar.get(int(e.id), [(None, None, simdi)]))
            return (self.yurutucu.gercek and all(borsa_hatasi(e) for e in dn)
                    and simdi - son_ret >= YENIDEN_ARALIK_MS and son)

        kapat, ac = [], []
        for x in ayr.get("kapat", []):
            a = (x["sembol"], int(x["olay_ms"]))
            dn = denemeler(x, "kapat") if a in acik else []
            if a in acik and (not dn or (tekrar(dn, True) and borsada(x["sembol"]))):
                kapat.append((acik[a], x.get("neden", "cikis")))
        for x in ayr.get("ac", []):
            a = (x["sembol"], int(x["olay_ms"]))
            dn = denemeler(x, "ac")
            if a in acik or (dn and not tekrar(dn, not d.durdurulmus and len(dn) <= YENIDEN_AZAMI
                                               and simdi - gun < YENIDEN_SON_MS)):
                continue
            if dn and borsada(x["sembol"]):
                _log.error("kilit_yeniden_deneme_borsada_pozisyon_var", sembol=x["sembol"], deneme=len(dn))
                continue
            ac.append(ck.Pozisyon(x["sembol"], a[1], int(x["giris_ms"]), int(x["cikis_ms"]), float(x["notional"])))
        if not kapat and not ac:
            return None
        _log.warning("kilit_karar_devam", gun=gun, kapat=[p.sembol for p, _ in kapat], ac=[p.sembol for p in ac])
        return self._yurut(d, karar_id, gun, kapat, ac, perp or self.borsa.perpler())

    def _kimlik(self, taban: str) -> str:
        """Emir kimliği tablo genelinde ve Binance'te tekildir. Aynı karar kalemi yeniden denenirse R1, R2… eki alır
        (Binance ≤ 36 karakter)."""
        with self.m.connect() as b:
            n = b.execute(select(func.count()).select_from(paper_emir).where(
                (paper_emir.c.istemci_emir_id == taban) | paper_emir.c.istemci_emir_id.like(f"{taban[:33]}R%"))).scalar()
        return taban if not n else f"{taban[:33]}R{n}"

    # ------------------------------------------------------------------ saatlik
    def _saatlik(self, d: Durum_, saat_bas: int) -> dict:
        perp = self.borsa.perpler()
        isaret = self.borsa.isaret()
        fon = self._gelir() if self.yurutucu.gercek else self._fonlama(d, perp)
        mutabakat = self._mutabakat(d) if self.yurutucu.gercek else None
        d = durum_kur(self.defter, self.kol.ad, self.kol.baslangic_ozkaynak) if fon or mutabakat else d
        fiyat = {k: isaret.get(k[len(ONEK):], d.son_fiyat.get(k, 0.0)) for k in d.adet}
        oz = d.ozkaynak(fiyat)
        self.defter.ozkaynak_yaz(self.kol.ad, saat_bas, KolDurum(oz, d.nakit, dict(d.adet)), fiyat)
        _, gecis = izleyici(d.gecmis + [(saat_bas, oz)], self.kol.baslangic_ozkaynak, self.ay.risk)
        neden = "durdur" if d.durdurulmus else ("acil_durdurma" if gecis == Durum.ACIL_DURDURMA else None)
        kapat = [(p, neden) for p in d.acik] if neden else \
            [(p, _kapanis_nedeni(perp.get(p.sembol, {}))) for p in d.acik if not _islemde(perp.get(p.sembol, {}))]
        if kapat:
            self._yurut(d, None, saat_bas // GUN_MS * GUN_MS, kapat, [], perp)
            if neden == "acil_durdurma":
                denetim.kaydet(self.m, "kilit", "acil_durdurma_kapatma", {"kol": self.kol.ad, "ozkaynak": oz})
        out = {"ozkaynak": round(oz, 2), "fonlama": fon, "kapatilan": [(p.sembol, n) for p, n in kapat]}
        return out | ({"mutabakat": mutabakat} if mutabakat else {})

    def _gelir(self) -> int:
        """Gerçek kol: borsanın gelir kaydındaki funding ve komisyon satırları (`tranId` tekil) → `fonlama` olayı.
        `ucret` = −gelir (maliyet pozitif). Komisyon dolumda 0 yazıldığı için tek kaynak burasıdır."""
        with self.m.connect() as b:
            rows = list(b.execute(select(paper_emir_olay.c.zaman_ms, paper_emir_olay.c.ayrinti).where(
                paper_emir_olay.c.kol == self.kol.ad, paper_emir_olay.c.tur == "fonlama")))
        gorulen = {str((a or {}).get("tranId")) for _, a in rows}
        bas = max([int(t) for t, _ in rows] + [self.defter.kol_baslangic(self.kol.ad) or 0])
        n = 0
        for g in self.yurutucu.ist.gelir(bas - 3_600_000):     # bir saat geriden: geç yazılan satırlar kaçmasın
            if g["tur"] not in NAKIT_GELIRI or str(g["tranId"]) in gorulen:
                if g["tur"] not in NAKIT_GELIRI and g["tur"] not in ("REALIZED_PNL", "TRANSFER"):
                    _log.warning("tanimsiz_gelir_turu", tur=g["tur"], gelir=g["gelir"])
                continue
            kim = f"{ONEK}{g['sembol']}"
            self.defter.olay_yaz(0, self.kol.ad, "fonlama", kim, 0.0, None, -float(g["gelir"]), int(g["zaman_ms"]),
                                 {"gelir": g["tur"], "tranId": str(g["tranId"]), "funding_ms": int(g["zaman_ms"])})
            gorulen.add(str(g["tranId"]))
            n += 1
        return n

    def _mutabakat(self, d: Durum_) -> dict | None:
        """Gerçek kol: borsadaki pozisyonlar ↔ defter. Fark varsa kol durdurulur (yeni risk yok, defterdekiler ilk
        saat başında kapanır; kural 7) ve KRİTİK hata loglanır. Defterin bilmediği borsa pozisyonuna dokunulmaz."""
        borsa = {f"{ONEK}{s}": q for s, q in self.yurutucu.ist.pozisyonlar().items() if abs(q) > 1e-12}
        fark = {k: {"borsa": borsa.get(k, 0.0), "defter": d.adet.get(k, 0.0)} for k in set(borsa) | set(d.adet)
                if abs(borsa.get(k, 0.0) - d.adet.get(k, 0.0)) > 1e-9 * max(1.0, abs(borsa.get(k, 0.0)))}
        if not fark:
            return None
        if not d.durdurulmus:
            self.defter.kol_olay_yaz(self.kol.ad, "durdur", {"neden": "mutabakat_gercek", "fark": fark},
                                     int(self.saat() * 1000))
            denetim.kaydet(self.m, "kilit", "gercek_mutabakat_farki", {"kol": self.kol.ad, "fark": fark})
        _log.error("gercek_mutabakat_farki", kol=self.kol.ad, fark=fark)
        return fark

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
        islem = {s for s, v in perp.items() if _islemde(v)}
        if self.yurutucu.gercek:   # yeni olay yalnız emrin gideceği ortamda da işlem görüyorsa; açıkların kapanışı değişmez
            ortam = self.yurutucu.islemde() or set()
            tut = {p.sembol for p in d.acik}
            islem = {s for s in islem if s in tut or perp[s]["sembol"] in ortam}
        k = ck.gun_karari(gun, olaylar, d.acik, islem, self.ay.kural, yeni_risk=iz.durum == Durum.NORMAL
                          and takvim_hatasi is None, hepsini_kapat=d.durdurulmus)
        ayr = {"tur": KILIT, "takvim_sha": sha, "takvim_hatasi": takvim_hatasi, "gecikmeli": simdi - gun > GECIKMELI_MS,
               "olay_sayisi": len(olaylar), "veto": [],
               "teslim_planli": sorted(s for s, v in perp.items() if v.get("durum") == "TRADING" and v.get("teslim_ms")),
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
        oz = d.ozkaynak(fiyat)
        if self.yurutucu.gercek:   # boyut hiçbir zaman borsadaki gerçek marjin bakiyesini aşmaz
            oz = min(oz, self.yurutucu.ist.ozkaynak())
        pf = Portfoy(oz, adet, fiyat, {k: SINIF for k in fiyat}, iz.durum,
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
        net = self.yurutucu.net_btc
        for p, neden in kapat:
            b_ = d.bacak.get(p.anahtar, {})
            for bacak, kim in (("token", b_.get("perp")),) + ((("btc", btc),) if not net else ()):
                q = -b_.get(bacak, 0.0)
                if kim and abs(q) > 1e-12:
                    self._emir(karar_id, pf, kim, q, p, bacak, "kapat", gun, kot, ref(kim), perp, out, neden)
        if net:
            acilan = []
            for p in ac:
                v = perp[p.sembol]
                kim = f"{ONEK}{v['sembol']}"
                bid = kot[v["sembol"]][0]
                q_t = -_yuvarla(p.notional * pf.ozkaynak / bid, v.get("adim", 0.0))
                if q_t == 0 or abs(q_t) * bid < v.get("asgari_notional", 0.0):
                    out["ret"].append({"sembol": p.sembol, "neden": "lot/asgari notional"})
                    continue
                t = self._emir(karar_id, pf, kim, q_t, p, "token", "ac", gun, kot, ref(kim), perp, out)
                if t:
                    acilan.append((p, kim, t))
            self._btc_dengele(karar_id, pf, btc, gun, kot, perp, out, acilan, ref)
            return out
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

    def _btc_dengele(self, karar_id, pf: Portfoy, btc: str, gun: int, kot, perp, out: dict,
                     acilan: list, ref) -> None:
        """Net BTC koruması (gerçek kol): BTC uzun = token kısalarının toplam nominali, BTC adımına en yakın.
        Artış dolmazsa bu turda açılan tokenlar geri kapatılır (açıkta kısa kalmaz; riski azaltır)."""
        s = btc[len(ONEK):]
        ask = kot[s][1]
        adim = float(perp[BTC].get("adim", 0.0) or 0.0)
        kisa = sum(-q * pf.fiyatlar.get(k, 0.0) for k, q in pf.pozisyonlar.items() if k != btc and q < 0)
        hedef = round(round(kisa / ask / adim) * adim, 12) if adim > 0 else kisa / ask
        fark = round(hedef - pf.pozisyonlar.get(btc, 0.0), 12)
        if abs(fark) < max(adim / 2, 1e-12):
            return
        on = f"{self.yurutucu.onek}H{gun // GUN_MS}-"
        with self.m.connect() as b:   # gün içindeki sıra: yeniden başlatmada da tekil ve belirlenimci
            n = b.execute(select(func.count()).select_from(paper_emir).where(
                paper_emir.c.istemci_emir_id.like(f"{on}%"))).scalar()
        eid = f"{on}{n}"
        b = self._emir(karar_id, pf, btc, fark, None, "btc_net", "denge", gun, kot, ref(btc), perp, out, istemci=eid)
        if fark > 0 and (b is None or b[0] < fark - adim - 1e-12) and acilan:   # risk motoru tavana kırparsa bir adım tolerans
            _log.error("btc_korumasi_eksik_tokenlar_geri", hedef=hedef, fark=fark)
            for p, kim, t in acilan:
                self._emir(karar_id, pf, kim, -t[0], p, "token", "geri", gun, kot, ref(kim), perp, out)
            self._btc_dengele(karar_id, pf, btc, gun, kot, perp, out, [], ref)

    def _emir(self, karar_id, pf: Portfoy, kim: str, q: float, p: ck.Pozisyon | None, bacak: str, islem: str, gun: int,
              kot, karar_fiyati: float, perp, out: dict, neden: str | None = None,
              istemci: str | None = None) -> tuple[float, float] | None:
        s = kim[len(ONEK):]
        bid, ask = kot[s]
        on = ask if q > 0 else bid
        eid_ist = istemci or self._kimlik(_istemci(gun, p.sembol, p.olay_ms, islem, bacak, self.yurutucu.onek))
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
            out["ret"].append({"sembol": p.sembol if p else s, "bacak": bacak, "gerekce": list(r.gerekceler)})
            return None
        onceki = pf.pozisyonlar.get(kim, 0.0)
        azaltan = abs(onceki + r.miktar) < abs(onceki) and onceki * r.miktar < 0
        try:
            dol = self.yurutucu.doldur(s, r.miktar, bid, ask, bacak, eid_ist, azaltan)
        except Exception as e:  # noqa: BLE001 — emir gitti mi bilinmiyor: mutabakat yakalar
            dol = f"hata: {type(e).__name__}: {e}"[:200]
            _log.error("emir_hatasi", kol=self.kol.ad, enstruman=kim, hata=dol)
        if isinstance(dol, str):
            self.defter.olay_yaz(eid, self.kol.ad, "ret", kim, q, None, 0.0, int(self.saat() * 1000), {"gerekceler": [dol]})
            out["ret"].append({"sembol": p.sembol if p else s, "bacak": bacak, "gerekce": [dol]})
            return None
        m, px = dol.adet, dol.fiyat
        ayr = {"bacak": bacak, "islem": islem, "neden": neden, "bid": bid, "ask": ask, "gecikmeli": False} | dol.ek
        if p is not None:
            ayr |= {"sembol": p.sembol, "olay_ms": p.olay_ms, "gun_ms": gun, "cikis_ms": p.cikis_ms,
                    "notional": p.notional, "perp": f"{ONEK}{s}" if bacak == "token" else None}
        self.defter.olay_yaz(eid, self.kol.ad, "dolum", kim, m, px, dol.ucret, int(self.saat() * 1000), ayr)
        pf.pozisyonlar[kim] = onceki + m
        out["dolum"] += 1
        return m, px


def _islemde(v: dict) -> bool:
    """Perp işlemde ve kaldırılması planlanmamış (`teslim_ms` yok)."""
    return v.get("durum") == "TRADING" and not v.get("teslim_ms")


def _kapanis_nedeni(v: dict) -> str:
    return "teslim_planli" if v.get("durum") == "TRADING" and v.get("teslim_ms") else "islem_gormuyor"


def _istemci(gun: int, sembol: str, olay_ms: int, islem: str, bacak: str, onek: str = "KL") -> str:
    """Tekil emir kimliği: önek + gün + olay + işlem (Aç/Kapat/Geri) + bacak (Token/Btc)."""
    return f"{onek}{gun // GUN_MS}-{sembol}-{olay_ms // GUN_MS}-{islem[0].upper()}{bacak[0].upper()}"[:36]   # Binance ≤ 36


def _poz(p: ck.Pozisyon) -> dict:
    return {"sembol": p.sembol, "olay_ms": p.olay_ms, "giris_ms": p.giris_ms, "cikis_ms": p.cikis_ms,
            "notional": p.notional}


def _yuvarla(x: float, adim: float) -> float:
    if adim <= 0:
        return x
    import math
    return round(math.floor(x / adim + 1e-9) * adim, 12)


def gercek_istemci(ay: KilitAyarlari, a=None):
    """Gerçek kolun Binance istemcisi (sırlar yalnız host `.env`'inde; kural 12). Anahtar yoksa None."""
    from tradebot.ayar import ayarlar as sistem
    from tradebot.canli.binance_emir import VadeliIstemci

    a = a or sistem()
    if ay.gercek is None or a.binance_anahtar is None or a.binance_gizli is None:
        return None
    return VadeliIstemci(ay.gercek["ortam"], a.binance_anahtar.get_secret_value(), a.binance_gizli.get_secret_value())


def calistir(sure_sn: float | None = None, dongu_sn: float = 60.0, blok: str = "kilit") -> None:
    """compose `kilit` (paper) ya da `kilit-gercek` servisi: her `dongu_sn`'de bir tur. Hata turu atlar (log), bir
    sonraki tur yeniden dener. Gerçek kol açılışta hesabı doğrular (tek yön modu; ana ağda çekim kapalı + IP kısıtı)."""
    import os

    from tradebot.ayar import ayarlar as sistem
    from tradebot.db import motor as db_motor
    from tradebot.veri.depo import HamDepo
    from tradebot.veri.http import NazikIstemci

    ay = ayarlar(blok=blok)
    if ay is None:
        raise SystemExit(f"config/paper.yaml içinde `{blok}` bloğu yok")
    a = sistem()
    m = db_motor(a)
    defter = PaperDefter(m, os.environ.get("TRADEBOT_KOD_SURUMU", "yerel"))
    yurutucu = None
    if ay.gercek is not None:
        ist = gercek_istemci(ay, a)
        if ist is None:
            raise SystemExit("TRADEBOT_BINANCE_ANAHTAR / TRADEBOT_BINANCE_GIZLI tanımlı değil (yalnız host .env)")
        _log.info("gercek_hesap", **ist.dogrula())
        yurutucu = GercekYurutucu(ist)
    dugum = KilitDugumu(defter, ay, Borsa(NazikIstemci("kilit", deneme=3, zaman_asimi=60).al, HamDepo(a.veri_dizini, m)),
                        yurutucu=yurutucu)
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

