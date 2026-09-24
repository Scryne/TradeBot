"""Spike 03 ikinci tur: DNS etkisinden arındırılmış ölçüm (Docker, --dns 1.1.1.1) + ilk turda düşenler.

- Dukascopy: tek HTTPS oturumu (keep-alive) ile 5 gün × 5 sembol hızı.
- Binance arşivi: aynı dosya DNS'siz süre.
- Yahoo günlük: range=max aylığa düşüyor → period1/period2 ile günlük.
- borsapy günlük: period=10y.
- FRED, GDELT (5 sn kuralına uyarak).
"""
from __future__ import annotations

import http.client
import json
import lzma
import struct
import time
import urllib.request
from datetime import datetime

S = {}


def olc(ad, f):
    t0 = time.perf_counter()
    try:
        S[ad] = {"durum": "OK", **(f() or {})}
    except Exception as e:
        S[ad] = {"durum": "HATA", "hata": f"{type(e).__name__}: {e}"[:200]}
    S[ad]["sure_sn"] = round(time.perf_counter() - t0, 2)
    print(f"{ad:<30} {S[ad]['durum']:<5} {S[ad]['sure_sn']:>7} sn  {json.dumps({k: v for k, v in S[ad].items() if k not in ('durum', 'sure_sn')}, ensure_ascii=False)[:220]}", flush=True)


def al(url, t=30):
    with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=t) as r:
        return r.read()


def duka():
    con = http.client.HTTPSConnection("datafeed.dukascopy.com", timeout=30)
    out, hata = {}, 0
    t0 = time.perf_counter()
    for s in ("EURUSD", "XAUUSD", "USA500IDXUSD", "DEUIDXEUR", "BRENTCMDUSD"):
        dk = 0
        for g in (15, 16, 17, 18, 19):
            try:
                con.request("GET", f"/datafeed/{s}/2026/08/{g:02d}/BID_candles_min_1.bi5", headers={"User-Agent": "Mozilla/5.0"})
                r = con.getresponse(); ham = r.read()
                if r.status == 200 and ham:
                    dk += len(lzma.decompress(ham)) // 24
                else:
                    hata += 1
            except Exception:
                hata += 1
                con.close(); con = http.client.HTTPSConnection("datafeed.dukascopy.com", timeout=30)
        out[s] = dk
    return {"dakika_5gun": out, "hata": hata, "istek_basi_sn": round((time.perf_counter() - t0) / 25, 2)}


def yahoo_gunluk():
    p1, p2 = int(datetime(1993, 1, 1).timestamp()), int(time.time())
    out = {}
    for s in ("SPY", "THYAO.IS", "XU100.IS"):
        r = json.loads(al(f"https://query1.finance.yahoo.com/v8/finance/chart/{s}?period1={p1}&period2={p2}&interval=1d&events=div,splits"))["chart"]["result"][0]
        out[s] = f"{len(r['timestamp'])} gün, {datetime.utcfromtimestamp(r['timestamp'][0]).date()}→"
    return out


def borsapy_gunluk():
    import borsapy as bp
    h = bp.Ticker("THYAO").history(period="10y", interval="1d", actions=True)
    return {"satir": len(h), "ilk": str(h.index[0])[:10] if len(h) else None}


def gdelt():
    time.sleep(6)
    d = json.loads(al("https://api.gdeltproject.org/api/v2/doc/doc?query=%22central%20bank%22%20sourcelang:english&mode=artlist&maxrecords=20&format=json"))
    return {"makale": len(d.get("articles", []))}


if __name__ == "__main__":
    olc("binance_arsiv_dnssiz", lambda: {"kb": len(al("https://data.binance.vision/data/spot/monthly/klines/ETHUSDT/1m/ETHUSDT-1m-2026-08.zip")) // 1024})
    olc("dukascopy_5sembol_5gun", duka)
    olc("yahoo_gunluk_period", yahoo_gunluk)
    olc("borsapy_THYAO_10y", borsapy_gunluk)
    olc("fred_csv", lambda: {"son": al("https://fred.stlouisfed.org/graph/fredgraph.csv?id=DGS10", 60).decode().splitlines()[-1]})
    olc("gdelt_doc", gdelt)
    print(f"\n{sum(v['durum'] == 'OK' for v in S.values())}/{len(S)} başarılı")
