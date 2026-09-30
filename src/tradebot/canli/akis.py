"""FOMC günü dolar kolu — MT5 demo düğümü (dalga 10 B; docs/turnuva/Dalga-10-Akis.md). Ayrı süreç (compose `akis`).

Ön kayıttaki kural: dalga 10'da B çıkan `fomc_dolar(pencere=gun)` NCM forex DEMO hesabında gözlem kolu olarak çalışır.
Planlı FOMC karar gününden önceki gün 21:00 UTC → karar günü 21:00 UTC yedi yabancı paranın eşit sepeti uzun (USD kısa).
Yılda 8 olay; backtest'te yıllık +%0,4 (küçük; gerçek para kapısı değişmez).

Döviz düğümünün (canli/doviz.py) para uzayı defteri, risk onayı (kural 5), emir yolu, mutabakat, MT5 işlemlerini
benimseme, yeniden başlatmada kurtarma ve aracı kurum acil stopu aynen kullanılır (alt sınıf). Farklar:
- **Karar saatlik.** Her saat başı karar gerekiyorsa (sinyal ya da açık pozisyon var): NCM H1 barları → backtest'in AYNI
  fonksiyonları (`fomc_dolar`, `panel_oynaklik_hedefi`, `dengele_adim`; kural 3). Sinyal yalnız takvimden doğar; gerek
  yoksa karar yazılmaz (yılın ~%97'si).
- **Bir bar gecikme.** Pencere 21:00 UTC'de açılıp kapanıyor: aracı kurumun gün devri, spread en geniş. Düğüm kararı
  bir bar geç uygular (22:00 → 22:00). Bu, dalga 10'un ön kayıtlı yürütme stresinin ("dolum bir bar geç") birebir
  aynısıdır: backtest'te +%0,38/yıl (gecikmesiz +%0,40). Ayrıca kararda spread `azami_spread_bps`'i aşarsa en çok
  `spread_bekle_dk` dakika beklenir (yeniden denenir), sonra yine yürütülür (log).
- **Finansman backtest modeliyle** (`NCMFX:fx_sabit`): taşıma geliri yok, tutulan |değer| × yıllık %2 (demo swap 0).
"""
from __future__ import annotations

import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import polars as pl
from sqlalchemy import insert

from tradebot.arastirma.panel import dengele_adim
from tradebot.arastirma.turnuva import STRATEJILER, Ayar, bar_yil, cevir, fomc_gunleri
from tradebot.canli import doviz as dv
from tradebot.canli.defter import PaperDefter
from tradebot.canli.kilit import izleyici
from tradebot.canli.kollar import PaperKol, oku
from tradebot.cekirdek import aileler as al
from tradebot.cekirdek import doviz_akis as da
from tradebot.cekirdek.boyut import panel_oynaklik_hedefi
from tradebot.db import paper_karar
from tradebot.kayit import log
from tradebot.risk.motor import RiskAyar

DUGUM = "akis"
SAAT_MS = dv.SAAT_MS
GUN_MS = dv.GUN_MS
GECMIS_GUN = 200               # H1 geçmişi: 90 işlem günü × 24 bar oynaklık penceresi + ısınma (~3.400 bar)
ASGARI_GECMIS_BAR = 60 * 24    # evren: en az 60 günlük bar (dalga 10 grup tanımı)
TAKVIM_UYARI_GUN = 90         # son planlı FOMC günü bu kadar yakınsa saatte bir hata logu (bekçi bildirir)
KOK = Path(__file__).resolve().parents[3]
_log = log("akis")


@dataclass(frozen=True)
class AkisAyarlari(dv.DovizAyarlari):
    gecikme_bar: int = 1
    azami_spread_bps: float = 4.0
    spread_bekle_dk: int = 30
    karar_gecikme_sn: int = 60


def para_ayir(kimlik: str, sembol: str) -> dv.Para:
    s = kimlik.split(":")[-1]
    taban, kote = s[:3], s[3:]
    if "USD" not in (taban, kote):
        raise ValueError(f"{kimlik}: USD karşılı parite değil")
    return dv.Para(kimlik, sembol, taban if kote == "USD" else kote, taban, kote)


def ayarlar(d: dict | None = None) -> AkisAyarlari | None:
    """`config/paper.yaml` `akis` bloğu. Blok yoksa None (düğüm çalışmaz). FOMC takvimi çekirdeğe burada verilir."""
    d = d or oku()
    b = d.get("akis")
    if not b:
        return None
    da.fomc_ayarla(fomc_gunleri(KOK / b["fomc_takvimi"]))
    risk = RiskAyar(kaldirac=float(b["risk"]["kaldirac"]))
    paralar = tuple(para_ayir(k, s) for k, s in b["semboller"].items())
    bo = b["boyut"]
    ayar = Ayar(hedef_vol=float(bo["hedef_vol"]), kaldirac=risk.kaldirac, vol_pencere_gun=int(bo["vol_pencere_gun"]),
                frenler=bool(d.get("frenler", True)), bant=float(bo["bant"]))
    grup = {"dugum": DUGUM, "yon": "long_short", "para": True, "kimlikler": [p.kimlik for p in paralar],
            "semboller": dict(b["semboller"]), "maliyet": b["maliyet"], "gecikme_bar": int(b["gecikme_bar"]),
            "hesap": "NCM forex demo"}
    kol = PaperKol(b["ad"], b["strateji"], "g10_saatlik", grup, "1h", ayar, dict(b["parametre"]), b.get("sinif", "B"),
                   float(b.get("baslangic_ozkaynak", 10_000)))
    return AkisAyarlari(kol, paralar, b["strateji"], dict(b["parametre"]), ayar.hedef_vol, ayar.vol_pencere_gun,
                        ayar.bant, risk, float(b["maliyet"]["kayma_bps"]), float(b["maliyet"]["finansman_yillik"]),
                        0, int(b["magic"]), gecikme_bar=int(b["gecikme_bar"]),
                        azami_spread_bps=float(b["azami_spread_bps"]), spread_bekle_dk=int(b["spread_bekle_dk"]))


# ---------------------------------------------------------------------------------------------------- saf karar
def izgara(barlar: dict[str, pl.DataFrame], paralar: tuple[dv.Para, ...], son_bar_ms: int) \
        -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """H1 barları → ortak ızgara (t, close [n,k] ileri doldurulmuş, evrende [n,k]). Backtest ızgarasıyla aynı kural
    (bar açılışlarının birleşimi, bar yoksa getiri 0). Son kapanmış bar (`son_bar_ms`) hiçbir sembolde yoksa ileri
    doldurulmuş bir satır eklenir: karar her zaman o barın kapanışına aittir."""
    t = np.unique(np.concatenate([barlar[p.sembol]["acilis_ms"].to_numpy() for p in paralar]))
    t = t[t <= son_bar_ms]
    if len(t) == 0 or t[-1] < son_bar_ms:
        t = np.r_[t, son_bar_ms]
    k = len(paralar)
    close, var = np.full((len(t), k), np.nan), np.zeros((len(t), k), dtype=bool)
    for j, p in enumerate(paralar):
        df = barlar[p.sembol].filter(pl.col("acilis_ms") <= son_bar_ms).sort("acilis_ms")
        i = np.searchsorted(t, df["acilis_ms"].to_numpy())
        close[i, j], var[i, j] = df["close"].to_numpy(), True
    for j in range(k):
        son = np.nan
        for i in range(len(t)):
            if np.isnan(close[i, j]):
                close[i, j] = son
            else:
                son = close[i, j]
    evrende = (np.cumsum(var, axis=0) >= ASGARI_GECMIS_BAR) & np.isfinite(close)
    return t, close, evrende


def hedefler(ay: AkisAyarlari, t: np.ndarray, close: np.ndarray, evrende: np.ndarray) -> np.ndarray:
    """Her barın kapanışındaki hedef çift ağırlıkları [n, k]. `turnuva.hedef_uret`'in panel yolu."""
    _, fonk, _ = STRATEJILER[ay.strateji]
    yon = np.array([p.yon for p in ay.paralar])
    pn = al.Panel(t, close, evrende, None, yon, tuple(p.para for p in ay.paralar))
    s = np.clip(fonk(pn, **cevir(ay.parametre, 24.0)), -1.0, 1.0)
    s = np.where(evrende, s, 0.0)
    return panel_oynaklik_hedefi(s, close, evrende, ay.hedef_vol, bar_yil("1h", "fx_24x5"),
                                 pencere=ay.vol_pencere_gun * 24, azami=ay.risk.kaldirac, varlik_olcekle=False,
                                 varlik_tavani=ay.risk.enstruman_tavani)


def sinyal_var(ay: AkisAyarlari, saat_bas: int) -> bool:
    """`saat_bas`'ta başlayan bar için (gecikme dahil) takvim sinyali var mı: çekirdeğin kendisi, fiyatsız ızgarada
    (strateji fiyata bakmaz; boyut ayrıca hesaplanır)."""
    g = ay.gecikme_bar
    t = saat_bas - np.arange(g + 2, 0, -1, dtype=np.int64) * SAAT_MS
    k = len(ay.paralar)
    _, fonk, _ = STRATEJILER[ay.strateji]
    pn = al.Panel(t, np.ones((len(t), k)), np.ones((len(t), k), dtype=bool), None,
                  np.array([p.yon for p in ay.paralar]), tuple(p.para for p in ay.paralar))
    return bool(np.abs(fonk(pn, **cevir(ay.parametre, 24.0))[-1 - g]).sum() > 0)


# ---------------------------------------------------------------------------------------------------- dış dünya
class Kaynak:
    """MT5 köprüsü: H1 barları, kotasyon (emir, pozisyon ve işlem geçmişi `ist` üzerinden, döviz düğümüyle aynı)."""

    def __init__(self, ist) -> None:
        self.ist = ist

    def saatlik(self, paralar: tuple[dv.Para, ...], simdi_ms: int) -> dict[str, pl.DataFrame]:
        from tradebot.veri.mt5 import katalog_barlari

        fark = int(self.ist.saglik()["fark_sn"]) * 1000
        ozellik = self.ist.semboller([p.sembol for p in paralar])
        out = {}
        for p in paralar:
            df = self.ist.mumlar(p.sembol, "H1", simdi_ms - GECMIS_GUN * GUN_MS, simdi_ms)
            out[p.sembol] = katalog_barlari(df, "1h", fark, False, float(ozellik[p.sembol]["point"]))
        return out

    def kotasyon(self, paralar: tuple[dv.Para, ...]) -> dict[str, dict]:
        return self.ist.kotasyon([p.sembol for p in paralar])["kotasyon"]


# ---------------------------------------------------------------------------------------------------- düğüm
class AkisDugumu(dv.DovizDugumu):
    EMIR_ONEK = "AK"

    def __init__(self, defter: PaperDefter, ay: AkisAyarlari, kaynak: Kaynak, saat: Callable[[], float] = time.time):
        super().__init__(defter, ay, kaynak, saat)
        self.ay: AkisAyarlari = ay

    def tur(self) -> dict:
        simdi = int(self.saat() * 1000)
        d = self._d()
        out: dict = {}
        saat_bas = simdi // SAAT_MS * SAAT_MS
        if not d.gecmis or d.gecmis[-1][0] < saat_bas:
            out["isaret"] = self._saatlik(d, saat_bas)
            d = self._d()
            if not len(da._FOMC) or int(da._FOMC[-1]) - simdi < TAKVIM_UYARI_GUN * GUN_MS:
                _log.error("fomc_takvimi_bitiyor", son=int(da._FOMC[-1]) if len(da._FOMC) else None,
                           neden="config/fomc_planli.yaml'a Fed'in yeni yıl takvimini ekle")
        if saat_bas in d.kararlar:
            devam = self._devam(d.kararlar[saat_bas])
            if devam:
                out["devam"] = devam
        elif simdi - saat_bas >= self.ay.karar_gecikme_sn * 1000 and saat_bas >= self._ilk_saat():
            if d.adet or any(abs(v) > 0 for v in d.etkin.values()) or sinyal_var(self.ay, saat_bas):
                r = self._saatlik_karar(d, saat_bas, simdi)
                if r:
                    out["karar"] = r
        return out

    def _ilk_saat(self) -> int:
        b = self.defter.kol_baslangic(self.kol.ad) or 0
        return b // SAAT_MS * SAAT_MS

    def _fonlama(self, d: dv.DovizDurum, fiyat: dict[str, float], bit: int) -> float:
        """Backtest modeli (NCMFX:fx_sabit): tutulan |değer| × yıllık finansman; taşıma geliri yok."""
        if not d.adet or not d.gecmis:
            return 0.0
        bas = max(d.son_fonlama, d.gecmis[-1][0])
        if bit <= bas:
            return 0.0
        dt = (bit - bas) / dv.YIL_MS
        toplam = 0.0
        for p in self.ay.paralar:
            kim = dv.ONEK + p.para
            a = d.adet.get(kim, 0.0)
            if abs(a) < 1e-9:
                continue
            v = a * fiyat.get(kim, d.son_fiyat.get(kim, 0.0))
            etki = -abs(v) * self.ay.kurum_payi_yillik * dt
            self.defter.olay_yaz(0, self.kol.ad, "fonlama", kim, 0.0, fiyat.get(kim), -etki, bit,
                                 {"bas_ms": bas, "bit_ms": bit, "deger_usd": v,
                                  "finansman_yillik": self.ay.kurum_payi_yillik})
            toplam += etki
        return toplam

    def _saatlik_karar(self, d: dv.DovizDurum, saat_bas: int, simdi: int) -> dict | None:
        if self._benimse().get("benimsenen"):
            d = self._d()
        fiyat, ham = self._fiyatlar()
        genis = {s: round((a - b) / ((a + b) / 2) * 1e4, 2) for s, (b, a, _) in ham.items()
                 if (a - b) / ((a + b) / 2) * 1e4 > self.ay.azami_spread_bps}
        if genis and simdi - saat_bas < self.ay.spread_bekle_dk * 60_000:
            return None                                   # devir saati spread'i: bir sonraki turda yeniden dene
        barlar = self.kaynak.saatlik(self.ay.paralar, simdi)
        son_bar = saat_bas - SAAT_MS
        t, close, evrende = izgara(barlar, self.ay.paralar, son_bar)
        h = hedefler(self.ay, t, close, evrende)
        g = self.ay.gecikme_bar
        hedef = h[-1 - g] if len(h) > g else np.zeros(len(self.ay.paralar))
        oz = d.ozkaynak(fiyat)
        kaymis = np.array([d.adet.get(dv.ONEK + p.para, 0.0) * fiyat.get(dv.ONEK + p.para, 0.0) * p.yon / oz
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
               "islem": [bool(x) for x in islem], "son_bar_ms": int(t[-1]), "gecikme_bar": g,
               "ozkaynak": oz, "genis_spread": genis, "fomc_sayisi": int(len(da._FOMC))}
        with self.m.begin() as b:
            kid = int(b.execute(insert(paper_karar).values(
                kol=self.kol.ad, bar_ms=saat_bas, karar_ms=int(self.saat() * 1000), kod_surumu=self.defter.kod,
                veri_hash=f"{int(t[-1])}:{len(t)}"[:64], durum=durum, ayrinti=ayr)).inserted_primary_key[0])
        hedef_para = {p.para: float(yeni[j] * p.yon) for j, p in enumerate(self.ay.paralar) if islem[j]}
        sonuc = self._yurut(d, kid, saat_bas, hedef_para, fiyat, ham, "S")
        hedef_l = [round(float(x), 3) for x in hedef]
        _log.info("akis_karar", saat=saat_bas, durum=durum, hedef=hedef_l, islem=int(islem.sum()), genis_spread=genis)
        return {"karar_id": kid, "hedef": hedef_l, **sonuc}


def calistir(sure_sn: float | None = None, dongu_sn: float = 60.0) -> None:
    """compose `akis` servisi: her `dongu_sn`'de bir tur. Hata turu atlar (log), bir sonraki tur yeniden dener."""
    import os

    from tradebot.ayar import ayarlar as sistem
    from tradebot.db import motor as db_motor
    from tradebot.mt5.istemci import Mt5Istemci

    ay = ayarlar()
    if ay is None:
        raise SystemExit("config/paper.yaml içinde `akis` bloğu yok")
    a = sistem()
    if not a.mt5_kopru_forex:
        raise SystemExit("TRADEBOT_MT5_KOPRU_FOREX tanımlı değil")
    defter = PaperDefter(db_motor(a), os.environ.get("TRADEBOT_KOD_SURUMU", "yerel"))
    dugum = AkisDugumu(defter, ay, Kaynak(Mt5Istemci(a.mt5_kopru_forex)))
    dugum.ac()
    bas = time.monotonic()
    while sure_sn is None or time.monotonic() - bas < sure_sn:
        try:
            r = dugum.tur()
            if r:
                _log.info("akis_tur", **{k: v for k, v in r.items() if k != "isaret"}, isaret=r.get("isaret"))
        except Exception as e:  # noqa: BLE001
            _log.error("akis_tur_hatasi", hata=f"{type(e).__name__}: {e}"[:300])
        time.sleep(dongu_sn)
