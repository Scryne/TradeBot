"""Spike 03: ilk dalga veri kaynaklarının ölçümü (erişim, hız, kapsam, kalite). Çıktı: data/olcum.json + ekran.

Her ölçüm bağımsız; biri düşerse diğerleri sürer. Anahtar gerektiren kaynaklar yalnız "anahtar gerekir" olarak
işaretlenir (bu spike anahtar açmaz).
"""
from __future__ import annotations

import io
import json
import lzma
import struct
import time
import traceback
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import polars as pl

DATA = Path(__file__).parent / "data"
DATA.mkdir(exist_ok=True)
UA = {"User-Agent": "TradeBot-arastirma 218348029+Scryne@users.noreply.github.com"}  # SEC EDGAR kimlikli User-Agent ister
SONUC: dict[str, dict] = {}


def al(url: str, zaman_asimi: int = 30, basliklar: dict | None = None) -> bytes:
    req = urllib.request.Request(url, headers=basliklar or {"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=zaman_asimi) as r:
        return r.read()


def olc(ad: str):
    def sar(f):
        t0 = time.perf_counter()
        try:
            SONUC[ad] = {"durum": "OK", **(f() or {})}
        except Exception as e:
            SONUC[ad] = {"durum": "HATA", "hata": f"{type(e).__name__}: {e}"[:300]}
            traceback.print_exc(limit=1)
        SONUC[ad]["sure_sn"] = round(time.perf_counter() - t0, 2)
        print(f"{ad:<34} {SONUC[ad]['durum']:<5} {SONUC[ad]['sure_sn']:>6} sn  "
              + json.dumps({k: v for k, v in SONUC[ad].items() if k not in ('durum', 'sure_sn')}, ensure_ascii=False)[:230])
        return f
    return sar


def ts(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d")


# ============================================================================ KRİPTO
@olc("binance_arsiv_1dk_ay")
def _():
    ham = al("https://data.binance.vision/data/spot/monthly/klines/ETHUSDT/1m/ETHUSDT-1m-2026-08.zip")
    with zipfile.ZipFile(io.BytesIO(ham)) as z:
        df = pl.read_csv(io.BytesIO(z.read(z.namelist()[0])), has_header=False)
    acilis = df[:, 0]
    birim = "mikrosaniye" if acilis[0] > 10**14 else "milisaniye"
    adim = acilis.diff().drop_nulls()
    return {"zip_kb": len(ham) // 1024, "satir": len(df), "zaman_birimi": birim,
            "eksik_dakika": int((adim != adim.mode()[0]).sum())}


@olc("binance_arsiv_eski_birim")
def _():
    ham = al("https://data.binance.vision/data/spot/monthly/klines/ETHUSDT/1m/ETHUSDT-1m-2024-08.zip")
    with zipfile.ZipFile(io.BytesIO(ham)) as z:
        ilk = z.read(z.namelist()[0]).split(b",")[0]
    return {"ilk_zaman": ilk.decode(), "birim": "mikrosaniye" if int(ilk) > 10**14 else "milisaniye"}


@olc("binance_funding_arsiv")
def _():
    ham = al("https://data.binance.vision/data/futures/um/monthly/fundingRate/BTCUSDT/BTCUSDT-fundingRate-2026-08.zip")
    with zipfile.ZipFile(io.BytesIO(ham)) as z:
        df = pl.read_csv(io.BytesIO(z.read(z.namelist()[0])))
    return {"satir": len(df), "kolonlar": df.columns}


@olc("binance_exchangeInfo_evren")
def _():
    d = json.loads(al("https://api.binance.com/api/v3/exchangeInfo"))
    s = d["symbols"]
    usdt = [x for x in s if x["quoteAsset"] == "USDT"]
    return {"sembol": len(s), "usdt_cifti": len(usdt), "islemde_usdt": sum(x["status"] == "TRADING" for x in usdt),
            "not": "listeleme tarihi yok; PIT evren için ilk kline tarihi kullanılmalı"}


@olc("binance_duyuru_delist")
def _():
    url = ("https://www.binance.com/bapi/composite/v1/public/cms/article/list/query"
           "?type=1&catalogId=161&pageNo=1&pageSize=20")
    d = json.loads(al(url))
    arts = d["data"]["catalogs"][0]["articles"]
    (DATA / "binance_delist.json").write_text(json.dumps(arts, ensure_ascii=False, indent=1), encoding="utf-8")
    return {"makale": len(arts), "ilk": arts[0]["title"][:90], "zaman_alani": "releaseDate" in arts[0]}


@olc("kripto_rss_coindesk")
def _():
    ham = al("https://www.coindesk.com/arc/outboundfeeds/rss/")
    return {"kb": len(ham) // 1024, "item": ham.count(b"<item>")}


# ============================================================================ DUKASCOPY
def duka_gun_1dk(sembol: str, gun: datetime) -> list[tuple]:
    """Dukascopy günlük 1 dk BID mum dosyası (.bi5 = LZMA). Ay 0 tabanlı."""
    url = (f"https://datafeed.dukascopy.com/datafeed/{sembol}/{gun.year}/{gun.month - 1:02d}/{gun.day:02d}/"
           "BID_candles_min_1.bi5")
    ham = al(url)
    if not ham:
        return []
    veri = lzma.decompress(ham)
    kayit = []
    for i in range(0, len(veri), 24):
        sn, o, c, l, h, v = struct.unpack(">5if", veri[i:i + 24])
        kayit.append((sn, o, h, l, c, v))
    return kayit


@olc("dukascopy_EURUSD_1dk_gun")
def _():
    k = duka_gun_1dk("EURUSD", datetime(2026, 9, 22))
    return {"dakika": len(k), "ilk_fiyat_ham": k[0][1], "not": "fiyat = tamsayı × 1e-5 (EURUSD point)"}


@olc("dukascopy_semboller")
def _():
    ok = {}
    for s in ("XAUUSD", "USA500IDXUSD", "BRENTCMDUSD", "DEUIDXEUR", "USDTRY"):
        try:
            ok[s] = len(duka_gun_1dk(s, datetime(2026, 9, 22)))
        except Exception as e:
            ok[s] = f"HATA {type(e).__name__}"
    return {"dakika_sayisi": ok}


@olc("dukascopy_1ay_hiz")
def _():
    t0, top = time.perf_counter(), 0
    for g in range(1, 31):
        try:
            top += len(duka_gun_1dk("EURUSD", datetime(2026, 6, g)))
        except Exception:
            pass
    return {"dakika": top, "gun_basi_sn": round((time.perf_counter() - t0) / 30, 2)}


# ============================================================================ YAHOO (ABD ETF + BIST)
def yahoo(sembol: str, aralik: str = "max", interval: str = "1d") -> dict:
    return json.loads(al(f"https://query1.finance.yahoo.com/v8/finance/chart/{sembol}?range={aralik}"
                         f"&interval={interval}&events=div,splits"))["chart"]["result"][0]


@olc("yahoo_SPY_max_gunluk")
def _():
    r = yahoo("SPY")
    t = r["timestamp"]
    ev = r.get("events", {})
    return {"bar": len(t), "ilk": ts(t[0] * 1000), "temettu": len(ev.get("dividends", {})), "bolunme": len(ev.get("splits", {}))}


@olc("yahoo_SPY_1dk")
def _():
    r = yahoo("SPY", "8d", "1m")
    return {"bar": len(r["timestamp"]), "ilk": ts(r["timestamp"][0] * 1000), "not": "1 dk yalnız son ~8-30 gün"}


@olc("yahoo_ETF_sepeti")
def _():
    out = {}
    for s in ("QQQ", "IWM", "TLT", "GLD", "XLF", "XLK", "XLE", "EEM"):
        r = yahoo(s)
        out[s] = f"{len(r['timestamp'])} bar, {ts(r['timestamp'][0] * 1000)}→"
    return out


@olc("yahoo_BIST_THYAO")
def _():
    r = yahoo("THYAO.IS")
    ev = r.get("events", {})
    q = r["indicators"]["quote"][0]
    bos = sum(c is None for c in q["close"])
    return {"bar": len(r["timestamp"]), "ilk": ts(r["timestamp"][0] * 1000), "bos_kapanis": bos,
            "temettu": len(ev.get("dividends", {})), "bolunme": len(ev.get("splits", {})),
            "bolunmeler": [f"{ts(int(k) * 1000)} {v['numerator']}:{v['denominator']}" for k, v in list(ev.get("splits", {}).items())[:6]]}


@olc("yahoo_BIST_1saat")
def _():
    r = yahoo("THYAO.IS", "2y", "1h")
    return {"bar": len(r["timestamp"]), "ilk": ts(r["timestamp"][0] * 1000)}


# ============================================================================ BORSAPY (BIST, KAP, VİOP, TCMB)
@olc("borsapy_THYAO_gunluk")
def _():
    import borsapy as bp
    h = bp.Ticker("THYAO").history(period="max", interval="1d", actions=True)
    return {"satir": len(h), "ilk": str(h.index[0])[:10], "kolon": list(h.columns),
            "bolunme_sayisi": int((h.get("Stock Splits", 0) != 0).sum()) if "Stock Splits" in h else None}


@olc("borsapy_THYAO_1dk")
def _():
    import borsapy as bp
    h = bp.Ticker("THYAO").history(period="5d", interval="1m")
    return {"satir": len(h), "ilk": str(h.index[0])[:16] if len(h) else None}


@olc("borsapy_THYAO_haber_KAP")
def _():
    import borsapy as bp
    n = bp.Ticker("THYAO").news
    ornek = n.head(3).to_dict("records") if hasattr(n, "head") else (n[:3] if n else [])
    (DATA / "borsapy_news.json").write_text(json.dumps(ornek, ensure_ascii=False, default=str, indent=1), encoding="utf-8")
    return {"kayit": len(n), "kolonlar": list(n.columns) if hasattr(n, "columns") else None}


@olc("borsapy_VIOP_endeks")
def _():
    import borsapy as bp
    f = bp.VIOP().index_futures
    return {"satir": len(f), "kolonlar": list(f.columns)[:8] if hasattr(f, "columns") else None}


@olc("borsapy_ekonomik_takvim")
def _():
    import borsapy as bp
    c = bp.EconomicCalendar()
    ev = c.events() if callable(getattr(c, "events", None)) else None
    return {"tur": type(ev).__name__, "satir": len(ev) if ev is not None else None}


# ============================================================================ SEC, FRED, GDELT, MERKEZ BANKASI
@olc("sec_edgar_8K")
def _():
    d = json.loads(al("https://data.sec.gov/submissions/CIK0000320193.json", basliklar=UA))
    f = d["filings"]["recent"]
    idx = [i for i, t in enumerate(f["form"]) if t == "8-K"]
    return {"sirket": d["name"], "son_8K": f["filingDate"][idx[0]] if idx else None, "8K_sayisi": len(idx),
            "kabul_zamani_var": "acceptanceDateTime" in f}


@olc("fred_csv_anahtarsiz")
def _():
    ham = al("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10")
    satir = ham.decode().splitlines()
    return {"satir": len(satir), "son": satir[-1]}


@olc("gdelt_doc_api")
def _():
    d = json.loads(al("https://api.gdeltproject.org/api/v2/doc/doc?query=%22central%20bank%22%20sourcelang:english"
                      "&mode=artlist&maxrecords=20&format=json"))
    return {"makale": len(d.get("articles", []))}


@olc("fed_basin_rss")
def _():
    ham = al("https://www.federalreserve.gov/feeds/press_monetary.xml")
    return {"item": ham.count(b"<item>")}


@olc("tcmb_duyuru")
def _():
    ham = al("https://www.tcmb.gov.tr/wps/wcm/connect/tr/tcmb+tr/main+menu/duyurular/basin")
    return {"kb": len(ham) // 1024, "not": "RSS yok; HTML ya da borsapy.TCMB/EVDS (anahtar)"}


if __name__ == "__main__":
    (DATA / "olcum.json").write_text(json.dumps(SONUC, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    ok = sum(v["durum"] == "OK" for v in SONUC.values())
    print(f"\n{ok}/{len(SONUC)} ölçüm başarılı")
