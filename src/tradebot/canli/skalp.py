"""Mikro ivme skalp düğümü — NCM forex DEMO hesabı, XAUUSD, saniyeler (GÖZLEM deneyi; compose `skalp`).

Scryne (2026-10-05): TikTok videosundaki "5 $ → 731 $" Strategy Tester botu (~10 sn'de bir 0,01 lot) gerçek spread'le
denensin; "evet çalıştır". Karar çekirdeği `cekirdek.skalp.karar` (saf). Yürütme altın düğümünün yolu (`AltinDugumu`:
karar deftere → risk motoru (kural 5) → MT5 demo piyasa emri → gerçek dolum deftere; saatlik finansman, mutabakat,
durdurma ve acil durdurmada kapatma, yeniden başlatmada kurtarma). Sabit 0,01 lot; martingale ve lot büyütme yok
(kural 6). Frenler (günlük −%3, haftalık −%8) yeni işlem açtırmaz, açık işlem yine kapanır.

Döngü `dongu_sn` (3 sn): kotasyon → açık pozisyon varsa hedef/stop/süre denetimi, düzse `bekleme` saniyelik orta fiyat
yönünde giriş. Her pozisyona aracı kurumda acil stop (stop mesafesinin 2 katı; donma ve sıçrama için). Dakikada bir
özkaynak işareti (pano ve gözetmen canlı görsün), 30 dakikada bir Telegram özeti.

Maliyet: dolum MT5 demo hesabının gerçek dolumudur (gerçek spread ve kayma), deftere ek kayma eklenmez (`kayma_bps` 0):
deneyin sorusu tam olarak gerçek spread'in ne yaptığıdır; defter MT5 ile birebir kalır. Finansman CFD metal modeli.
"""
from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
from sqlalchemy import insert, select

from tradebot.arastirma.panel import riski_artirma
from tradebot.canli import altin
from tradebot.canli.altin import AltinAyarlari, AltinDugumu
from tradebot.canli.defter import PaperDefter
from tradebot.canli.karar import KolDurum
from tradebot.canli.kilit import izleyici
from tradebot.canli.kollar import oku
from tradebot.cekirdek import skalp as cs
from tradebot.db import paper_emir_olay, paper_karar
from tradebot.kayit import log

DUGUM = "skalp"
BLOK = "skalp"
DAKIKA_MS = 60_000
SAAT_MS = 3_600_000
OZET_MS = 30 * DAKIKA_MS
ACIL_STOP_KAT = 2.0
_log = log("skalp")


@dataclass(frozen=True)
class SkalpParam:
    bekleme_ms: int
    tp_usd: float
    sl_oran: float
    azami_ms: int


def ayarlar(d: dict | None = None) -> tuple[AltinAyarlari, SkalpParam] | None:
    d = d or oku()
    ay = altin.ayarlar(d, blok=BLOK, dugum=DUGUM, grup_adi="xau_tik", zd="10s")
    if ay is None:
        return None
    p = d[BLOK]["parametre"]
    return ay, SkalpParam(int(float(p["bekleme_sn"]) * 1000), float(p["tp_usd"]), float(p["sl_oran"]),
                          int(float(p["azami_sn"]) * 1000))


class SkalpDugumu(AltinDugumu):
    EID_ONEK, EID_BOLEN = "SK", 1000

    def __init__(self, defter: PaperDefter, ay: AltinAyarlari, p: SkalpParam, ist, saat: Callable[[], float] = time.time,
                 bildir: Callable[[str], None] | None = None) -> None:
        super().__init__(defter, ay, ist, saat)
        self.p, self.bildir = p, bildir
        self.ortalar: deque[tuple[int, float]] = deque(maxlen=200)
        self.giris: tuple[float, int] | None = None        # (MT5 giriş fiyatı, açılış ms)
        self.son_kapanis_ms = 0
        self.son_saat = 0
        self.son_dakika = 0
        self.son_ozet = int(saat() * 1000)
        self.spreadler: deque[float] = deque(maxlen=2000)

    # ------------------------------------------------------------------ tur
    def tur(self) -> dict:
        simdi = int(self.saat() * 1000)
        out: dict = {}
        d = self._d()
        if not self.son_saat:
            self.son_saat = max((t for t, _ in d.gecmis if t % SAAT_MS == 0), default=0)
        saat_bas = simdi // SAAT_MS * SAAT_MS
        if saat_bas > self.son_saat:
            out["isaret"] = self._saatlik(d, saat_bas)
            self.son_saat = self.son_dakika = saat_bas
            d = self._d()
        if not self._kurtarildi:
            k = self._kurtar()
            self._kurtarildi = True
            if k:
                out["kurtarma"] = k
                d = self._d()
        kot = self._kotasyon()
        if kot is None:
            return out
        bid, ask, _ = kot
        orta = (bid + ask) / 2
        self.ortalar.append((simdi, orta))
        self.spreadler.append(ask - bid)
        dakika = simdi // DAKIKA_MS * DAKIKA_MS
        if dakika > self.son_dakika:
            adet = {self.ay.kimlik: d.adet} if d.adet else {}
            self.defter.ozkaynak_yaz(self.kol.ad, dakika, KolDurum(d.ozkaynak(orta), d.nakit, adet), {self.ay.kimlik: orta})
            self.son_dakika = dakika
            d = self._d()
        k = self._karar(d, kot, simdi)
        if k:
            out["karar"] = k
        if simdi - self.son_ozet >= OZET_MS:
            self._ozet(simdi, orta)
        return out

    def _orta_once(self, simdi: int) -> float | None:
        hedef = simdi - self.p.bekleme_ms
        once = [o for t, o in self.ortalar if t <= hedef]
        return once[-1] if once else None

    def _giris_fiyati(self, d) -> tuple[float, int] | None:
        if self.giris is None and d.lot:
            ps = [x for x in self.ist.pozisyonlar(self.ay.magic) if x["sembol"] == self.ay.sembol]
            if ps:
                lot = sum(float(x["hacim"]) for x in ps)
                px = sum(float(x["hacim"]) * float(x["fiyat"]) for x in ps) / lot
                self.giris = (px, min(int(x["zaman_ms"]) for x in ps))
        return self.giris

    def _karar(self, d, kot: tuple[float, float, int], simdi: int) -> dict | None:
        bid, ask, _ = kot
        iz, _ = izleyici(d.gecmis, self.kol.baslangic_ozkaynak, self.ay.risk)
        durum = iz.durum.value
        poz = int(np.sign(d.lot))
        if not poz:
            self.giris = None
        g = self._giris_fiyati(d) if poz else None
        if poz and g is None:
            return None                                  # MT5'te pozisyon görünmüyor: saatlik mutabakat/benimseme çözer
        hedef, neden = cs.karar(poz, g[0] if g else 0.0, bid, ask, self._orta_once(simdi),
                                simdi - g[1] if g else 0, simdi - self.son_kapanis_ms, self.p.tp_usd,
                                self.p.sl_oran * (bid + ask) / 2, self.p.azami_ms, self.p.bekleme_ms)
        if d.durdurulmus or durum == "acil_durdurma":
            hedef, neden = 0, "durdur" if d.durdurulmus else "acil_durdurma"
        elif durum != "normal":
            hedef = int(riski_artirma(np.array([float(hedef)]), np.array([float(poz)]))[0])
        if hedef == poz:
            return None
        hedef_lot = hedef * self.ay.lot
        ayr = {"tur": self.ay.strateji, "neden": neden, "poz": poz, "hedef_lot": hedef_lot, "lot_once": d.lot,
               "bid": bid, "ask": ask, "giris": g[0] if g else None, "orta_once": self._orta_once(simdi)}
        with self.m.begin() as c:
            kid = int(c.execute(insert(paper_karar).values(
                kol=self.kol.ad, bar_ms=simdi, karar_ms=simdi, kod_surumu=self.defter.kod,
                veri_hash=f"{simdi}:{bid}:{ask}"[:64], durum=durum, ayrinti=ayr)).inserted_primary_key[0])
        sl = self.p.sl_oran * (bid + ask) / 2
        sonuc = self._yurut(d, kid, simdi, hedef_lot, kot, "K" if hedef == 0 else "A",
                            neden=neden, sl_mesafe=ACIL_STOP_KAT * sl if hedef else None)
        if hedef == 0 and sonuc["dolum"]:
            self.son_kapanis_ms = int(self.saat() * 1000)
            self.giris = None
        _log.info("skalp_karar", neden=neden, poz=poz, hedef=hedef, **sonuc)
        return {"karar_id": kid, "neden": neden, "hedef": hedef, **sonuc}

    # ------------------------------------------------------------------ özet
    def istatistik(self, bas_ms: int) -> dict:
        """[bas_ms, şimdi] kapanan işlemler (dolum çiftleri): sayı, kazanan, net (ons × fiyat farkı)."""
        with self.m.connect() as b:
            ds = list(b.execute(select(paper_emir_olay.c.miktar, paper_emir_olay.c.fiyat, paper_emir_olay.c.zaman_ms)
                                .where(paper_emir_olay.c.kol == self.kol.ad, paper_emir_olay.c.tur == "dolum")
                                .order_by(paper_emir_olay.c.id)))
        islem, kazanan, net, acik = 0, 0, 0.0, None
        for q, px, t in ds:
            if acik is None:
                acik = (float(q), float(px))
                continue
            k = acik[0] * (float(px) - acik[1])
            acik = None
            if int(t) >= bas_ms:
                islem += 1
                kazanan += k > 0
                net += k
        return {"islem": islem, "kazanan": kazanan, "net": net}

    def _ozet(self, simdi: int, orta: float) -> None:
        self.son_ozet = simdi
        d = self._d()
        son = self.istatistik(simdi - OZET_MS)
        tum = self.istatistik(0)
        sp = float(np.median(self.spreadler)) if self.spreadler else float("nan")
        oz = d.ozkaynak(orta)
        metin = (f"Skalp botu (demo, altın, 0,01 lot)\n"
                 f"Son 30 dk: {son['islem']} işlem, {son['kazanan']} kazanç / {son['islem'] - son['kazanan']} kayıp, "
                 f"net {son['net']:+.2f} $\n"
                 f"Başlangıçtan beri: {tum['islem']} işlem, net {oz - self.kol.baslangic_ozkaynak:+.2f} $ "
                 f"(özkaynak {oz:,.2f} $)\nOrtanca spread {sp:.2f} $ (her işlemin peşin maliyeti)")
        _log.info("skalp_ozet", **son, toplam=tum["islem"], ozkaynak=round(oz, 2), spread=round(sp, 3))
        if self.bildir is not None:
            self.bildir(metin)


def calistir(sure_sn: float | None = None, dongu_sn: float = 3.0) -> None:
    """compose `skalp` servisi."""
    import os

    from tradebot.ayar import ayarlar as sistem
    from tradebot.bildirim import Bildirici
    from tradebot.db import motor as db_motor
    from tradebot.mt5.istemci import Mt5Istemci

    r = ayarlar()
    if r is None:
        raise SystemExit("config/paper.yaml içinde `skalp` bloğu yok")
    ay, p = r
    a = sistem()
    if not a.mt5_kopru_forex:
        raise SystemExit("TRADEBOT_MT5_KOPRU_FOREX tanımlı değil")
    bildirici = Bildirici(a)
    dugum = SkalpDugumu(PaperDefter(db_motor(a), os.environ.get("TRADEBOT_KOD_SURUMU", "yerel")), ay, p,
                        Mt5Istemci(a.mt5_kopru_forex, zaman_asimi=30), bildir=lambda m: bildirici.gonder("BILGI", m))
    dugum.ac()
    bildirici.gonder("BILGI", f"Skalp botu başladı (NCM demo, altın 0,01 lot, ~{p.bekleme_ms // 1000} sn'de bir işlem "
                              f"denemesi). Her 30 dakikada özet gelir.")
    bas = time.monotonic()
    while sure_sn is None or time.monotonic() - bas < sure_sn:
        try:
            r = dugum.tur()
            if r.get("isaret") or r.get("kurtarma"):
                _log.info("skalp_tur", **r)
        except Exception as e:  # noqa: BLE001
            _log.error("skalp_tur_hatasi", hata=f"{type(e).__name__}: {e}"[:300])
        time.sleep(dongu_sn)

