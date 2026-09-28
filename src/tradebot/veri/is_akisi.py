"""Veri iş akışları: kaynak başına güncelleme, kalite, evren ve gece işi (sırayla, zaman bütçeli).

Gece işi her koşuda sonucunu denetim izine yazar (hangi kaynak kaç dosya, kalite durum dağılımı, süre).
"""
from __future__ import annotations

import time
from collections import Counter
from datetime import UTC, datetime, timedelta

from sqlalchemy.engine import Engine

from tradebot import denetim
from tradebot.ayar import Ayarlar
from tradebot.kayit import log
from tradebot.veri import enstruman as en
from tradebot.veri import evren as ev
from tradebot.veri import kalite
from tradebot.veri.binance import Binance
from tradebot.veri.depo import BarDepo
from tradebot.veri.dukascopy import Dukascopy
from tradebot.veri.yahoo import Yahoo

_log = log("veri.is_akisi")


def binance(a: Ayarlar, m: Engine, sinir: int | None = None) -> dict:
    b = Binance(a.veri_dizini, m)
    k = b.evren["kripto"]
    evren = b.evren_guncelle(k["temel_zaman_dilimi"], sinir=sinir)
    dakika = [b.klines(s, "1m") for s in k["dakikalik"]]
    funding = [b.funding(s) for s in k["funding"]]
    return {"sembol": len(evren), "saatlik_dosya": sum(r["yeni_dosya"] for r in evren),
            "dakikalik_dosya": sum(r["yeni_dosya"] for r in dakika), "funding_dosya": sum(r["yeni_dosya"] for r in funding)}


def yahoo(a: Ayarlar, m: Engine, tam: bool = False) -> dict:
    r = Yahoo(a.veri_dizini, m).evren_guncelle(tam=tam)
    return {"enstruman": len(r), "tam_yenileme": sum(x["tam"] for x in r), "olay": sum(x["olay"] for x in r)}


def dukascopy(a: Ayarlar, m: Engine, butce_dk: float) -> dict:
    r = Dukascopy(a.veri_dizini, m).evren_guncelle(butce_dk=butce_dk)
    return {"enstruman": len(r), "dosya": sum(x.get("yeni_dosya", 0) for x in r)}


def mt5(a: Ayarlar, m: Engine, butce_dk: float = 60.0) -> dict:
    """MT5 köprüleri (Faz 8). Köprü tanımsızsa ya da ulaşılamıyorsa atlanır (yalnız log; bekçi ayrıca alarm verir)."""
    from tradebot.mt5.istemci import Mt5Istemci
    from tradebot.veri.mt5 import Mt5Veri

    istemciler = {h: Mt5Istemci(u) for h, u in (("forex", a.mt5_kopru_forex), ("viop", a.mt5_kopru_viop)) if u}
    if not istemciler:
        return {"atlandi": "köprü tanımsız"}
    from tradebot.veri.viop import xu030_surekli

    r = Mt5Veri(a.veri_dizini, m, istemciler).guncelle(butce_dk)
    return {"enstruman": len({x["kimlik"] for x in r}), "yeni_bar": sum(x.get("yeni", 0) for x in r),
            "hata": [x for x in r if "hata" in x and x["hata"]][:5],
            "xu030_surekli": xu030_surekli(BarDepo(a.veri_dizini), m)}


def _zaman_dilimleri(kayit: dict) -> list[str]:
    if kayit["kaynak"] == "mt5":
        return ["1h", "1d"]
    return ["1d"] if kayit["kaynak"] == "yahoo" else ["1h"]


def kalite_hepsi(a: Ayarlar, m: Engine) -> dict:
    depo = BarDepo(a.veri_dizini)
    simdi = int(time.time() * 1000)
    say: Counter = Counter()
    for k in en.hepsi(m):
        if k["durum"] == "veri_yok":
            continue
        for zd in _zaman_dilimleri(k) + (["1m"] if depo.yol(k["kimlik"], "1m").exists() else []):
            df = depo.oku(k["kimlik"], zd)
            if df.is_empty():
                continue
            durum, ozet = kalite.rapor(df, zd, k["takvim"], simdi, sicrama_uyari=k["kaynak"] != "binance")
            if k["meta"].get("evren_uyarisi"):
                ozet["evren_uyarisi"] = k["meta"]["evren_uyarisi"]
            kalite.kaydet(m, k["kimlik"], zd, durum, ozet)
            say[durum] += 1
    return dict(say)


def evren_kur(a: Ayarlar, m: Engine) -> dict:
    depo = BarDepo(a.veri_dizini)
    simdi = int(time.time() * 1000)
    kayit = en.hepsi(m)
    gruplar = {
        "kripto": ([k["kimlik"] for k in kayit if k["sinif"] == "kripto"], "1h", "2017-08-01"),
        "bist": ([k["kimlik"] for k in kayit if k["piyasa"] == "BIST" and k["sinif"] == "hisse"], "1d", "2000-01-01"),
        "abd_etf": ([k["kimlik"] for k in kayit if k["piyasa"] == "ARCA"], "1d", "1993-01-01"),
        "dukascopy": ([k["kimlik"] for k in kayit if k["piyasa"] == "DUKASCOPY"], "1h", "2010-01-01"),
    }
    out = {}
    for grup, (kimlikler, zd, bas) in gruplar.items():
        bas_ms = int(datetime.fromisoformat(bas).replace(tzinfo=UTC).timestamp() * 1000)
        tb = ev.tablo_kur(depo, kimlikler, zd, bas_ms, simdi, pencere=30 if grup == "kripto" else 20)
        if not tb.is_empty():
            ev.yaz(tb, a.veri_dizini, grup)
        out[grup] = {"enstruman": tb["kimlik"].n_unique() if not tb.is_empty() else 0, "satir": len(tb)}
    return out


def _adimlar(adimlar: list, sonuc: dict) -> None:
    for ad, f in adimlar:
        t = time.monotonic()
        try:
            sonuc[ad] = f() | {"sure_dk": round((time.monotonic() - t) / 60, 1)}
        except Exception as e:
            sonuc[ad] = {"hata": f"{type(e).__name__}: {e}"[:300]}
            _log.error("gece_adim_hatasi", adim=ad, hata=sonuc[ad]["hata"])
        _log.info("gece_adim", adim=ad, sonuc=sonuc[ad])


def gece(a: Ayarlar, m: Engine, dukascopy_butce_dk: float = 240.0) -> dict:
    """Sırayla: Binance → Yahoo → MT5 → kalite → evren → denetim kaydı (`gece_isi`) → Dukascopy (bütçeli, saatlerce sürebilir)
    → denetim kaydı (`gece_isi_dukascopy`). Bir adımın hatası diğerlerini durdurmaz.

    Dukascopy en sondadır: hız sınırı yüzünden bütçesi 15 saate kadar çıkar ve servis yeniden başlatılırsa (her dağıtımda)
    kesilir. Önceden sondan bir önceki adımdı; iş hiç kalite/evren adımına ulaşamadı (2026-09-27 denetimi: kalite
    raporu ve gece_isi denetim kaydı hiç yazılmamıştı). Dukascopy verisinin kalitesi bir sonraki gece raporlanır."""
    t0 = time.monotonic()
    sonuc: dict = {"basla": datetime.now(UTC).isoformat()}
    _adimlar([("binance", lambda: binance(a, m)), ("yahoo", lambda: yahoo(a, m)), ("mt5", lambda: mt5(a, m)),
              ("kalite", lambda: kalite_hepsi(a, m)), ("evren", lambda: evren_kur(a, m))], sonuc)
    sonuc["sure_dk"] = round((time.monotonic() - t0) / 60, 1)
    denetim.kaydet(m, "veri", "gece_isi", sonuc)
    d: dict = {"basla": datetime.now(UTC).isoformat()}
    _adimlar([("dukascopy", lambda: dukascopy(a, m, dukascopy_butce_dk))], d)
    denetim.kaydet(m, "veri", "gece_isi_dukascopy", d)
    return sonuc | {"dukascopy": d["dukascopy"]}


def sonraki_calisma(simdi: datetime, saat_utc: int, dakika: int) -> datetime:
    hedef = simdi.replace(hour=saat_utc, minute=dakika, second=0, microsecond=0)
    return hedef if hedef > simdi else hedef + timedelta(days=1)
