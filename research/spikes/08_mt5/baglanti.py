"""Spike 08: NCM MT5 demo hesaplarına Python'dan bağlantı (Faz 8'in ilk riskli adımı). HOST WINDOWS'TA çalışır.

    uv run --no-project --python 3.12 --with MetaTrader5 research/spikes/08_mt5/baglanti.py <forex|viop>
        [--gecmis] [--ornekle <dk> <sembol,sembol>] [--emir <sembol>]

MT5 terminali grafik arayüzlüdür: SSH oturumundan değil, kullanıcı oturumundaki zamanlanmış görevden çalıştırılır
(`calistir.ps1`). Şifre `C:\\TradeBot\\app\\.env`'den okunur; çıktıya sır girmez. Sonuç: C:\\TradeBot\\log\\mt5_<hesap>.json

Beklentiler (sonuca bakmadan yazıldı, 2026-09-27):
  B1 İki hesap da portable terminal kopyasıyla giriş yapar (`trade_allowed`, demo).
  B2 Forex hesabında XAUUSD, EURUSD, USDTRY ve en az bir ABD/Almanya endeks CFD'si var.
  B3 VİOP hesabında BIST30 endeks vadelisi ve USDTRY vadelisi var (sembol adları bilinmiyor; listeden bulunur).
  B4 XAUUSD M15 geçmişi terminalden en az 1 yıl çekilebilir (Dukascopy ile karşılaştırma için).
  B5 --emir: piyasa açıkken en küçük hacimle al-kapat demo emri dolar (retcode 10009); kapalıyken ret kodu okunur.
"""
from __future__ import annotations

import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

import MetaTrader5 as mt5

KOK = Path(r"C:\TradeBot")
ADAY = {  # sembol adı içinde aranan parçalar (büyük/küçük harf duyarsız)
    "forex": ["GOLD", "SILVER", "XAU", "EURUSD", "USDTRY", "GBPUSD", "USDJPY", "DXY", "ES", "NQ", "YM", "GER40", "CL",
              "NG"],
    "viop": ["XU030", "XU30", "USDTRY", "TRYUSD", "EURTRY", "XAUTRY", "XAUUSD", "XAGUSD", "EURUSD"],
}
# geçmiş derinliği ölçülen semboller (ilk turdaki listeden; 2026-09-27)
GECMIS = {"forex": ["GOLD", "SILVER", "EURUSD", "USDJPY", "ES!", "ES6Z", "NQ6Z", "GER40!", "GER40Z26", "CL!", "CL6X"],
          "viop": ["XU30_YAKINVADE", "F_XU0301026", "F_XU0301226", "TRYUSD_YAKINVADE", "F_USDTRY1026",
                   "F_XAUUSD1026", "F_XAUTRYM1026"]}


def iz(*x) -> None:
    """İlerleme (calistir.log'a): ikinci turda süreç sessizce takıldı, hangi çağrıda olduğunu görmek için."""
    print(datetime.now(UTC).strftime("%H:%M:%S"), *x, flush=True)


def mumlar(sembol: str, tf: int, adet: int = 20_000, deneme: int = 4):
    """İlk istekte terminal geçmişi sunucudan indirirken None döner (ilk tur: hepsi None): bekleyip yeniden dener."""
    hata = None
    for i in range(deneme):
        iz("mum", sembol, tf, "deneme", i)
        r = mt5.copy_rates_from_pos(sembol, tf, 0, adet)
        if r is not None and len(r):
            return r, None
        hata = mt5.last_error()
        time.sleep(5)
    return None, hata


def env() -> dict[str, str]:
    out = {}
    for satir in (KOK / "app" / ".env").read_text(encoding="utf-8").splitlines():
        if "=" in satir and not satir.lstrip().startswith("#"):
            k, v = satir.split("=", 1)
            out[k.strip()] = v.strip()
    return out


def ad(x) -> dict:
    return x._asdict() if x is not None else None


def ozellik(s) -> dict:
    alanlar = ("name", "path", "description", "currency_base", "currency_profit", "currency_margin", "digits", "point",
               "spread", "spread_float", "trade_contract_size", "trade_tick_size", "trade_tick_value", "volume_min",
               "volume_step", "volume_max", "trade_mode", "trade_exemode", "filling_mode", "order_mode",
               "trade_stops_level", "swap_long", "swap_short", "swap_mode", "margin_initial", "margin_maintenance",
               "expiration_time", "start_time", "session_deals", "bid", "ask", "last", "time")
    d = s._asdict()
    return {k: d.get(k) for k in alanlar}


def emir_testi(sembol: str) -> dict:
    """En küçük hacimle piyasa alışı, ardından kapatma. Demo hesap; bağlantı testi, sinyal değil."""
    mt5.symbol_select(sembol, True)
    info = mt5.symbol_info(sembol)
    tick = mt5.symbol_info_tick(sembol)
    doldurma = mt5.ORDER_FILLING_FOK if info.filling_mode & 1 else (
        mt5.ORDER_FILLING_IOC if info.filling_mode & 2 else mt5.ORDER_FILLING_RETURN)
    istek = {"action": mt5.TRADE_ACTION_DEAL, "symbol": sembol, "volume": info.volume_min,
             "type": mt5.ORDER_TYPE_BUY, "price": tick.ask if tick else 0.0, "deviation": 20,
             "magic": 808, "comment": "spike08", "type_filling": doldurma, "type_time": mt5.ORDER_TIME_GTC}
    t0 = time.perf_counter()
    kontrol = mt5.order_check(istek)
    r = mt5.order_send(istek)
    sonuc = {"sembol": sembol, "istek_fiyat": istek["price"], "doldurma": doldurma,
             "order_check": ad(kontrol), "ac": ad(r), "ac_sn": round(time.perf_counter() - t0, 3),
             "son_hata": mt5.last_error()}
    if r is not None and r.retcode == mt5.TRADE_RETCODE_DONE:
        time.sleep(2)
        poz = [p for p in (mt5.positions_get(symbol=sembol) or []) if p.magic == 808]
        for p in poz:
            t = mt5.symbol_info_tick(sembol)
            kapat = {**istek, "type": mt5.ORDER_TYPE_SELL, "price": t.bid, "position": p.ticket}
            t0 = time.perf_counter()
            sonuc.setdefault("kapat", []).append({**ad(mt5.order_send(kapat)), "sn": round(time.perf_counter() - t0, 3)})
    if isinstance(sonuc.get("ac"), dict) and sonuc["ac"].get("request"):
        sonuc["ac"]["request"] = sonuc["ac"]["request"]._asdict()
    for k in sonuc.get("kapat", []):
        if k.get("request"):
            k["request"] = k["request"]._asdict()
    if isinstance(sonuc.get("order_check"), dict) and sonuc["order_check"].get("request"):
        sonuc["order_check"]["request"] = sonuc["order_check"]["request"]._asdict()
    return sonuc


def main() -> None:
    hesap = sys.argv[1]
    e = env()
    anahtar = hesap.upper()
    terminal = KOK / "mt5" / hesap / "terminal64.exe"
    out: dict = {"hesap": hesap, "zaman": datetime.now(UTC).isoformat(), "paket": mt5.__version__}
    t0 = time.perf_counter()
    iz("initialize", hesap)
    ok = mt5.initialize(path=str(terminal), login=int(e[f"TRADEBOT_MT5_{anahtar}_LOGIN"]),
                        password=e[f"TRADEBOT_MT5_{anahtar}_SIFRE"], server=e["TRADEBOT_MT5_SUNUCU"],
                        portable=True, timeout=120_000)
    out["baglanti_sn"] = round(time.perf_counter() - t0, 1)
    iz("initialize bitti", ok, out["baglanti_sn"])
    if not ok:
        out["hata"] = mt5.last_error()
        yaz(hesap, out)
        return
    try:
        out["terminal"] = {k: v for k, v in ad(mt5.terminal_info()).items()
                           if k in ("build", "connected", "trade_allowed", "tradeapi_disabled", "ping_last",
                                    "company", "name", "path", "community_account")}
        out["hesap_bilgi"] = {k: v for k, v in ad(mt5.account_info()).items()
                              if k in ("login", "trade_mode", "leverage", "limit_orders", "margin_so_mode",
                                       "trade_allowed", "trade_expert", "margin_mode", "currency_digits",
                                       "fifo_close", "balance", "equity", "currency", "server", "company")}
        iz("semboller")
        semboller = mt5.symbols_get() or ()
        out["sembol_sayisi"] = len(semboller)
        out["gruplar"] = sorted({s.path.rsplit("\\", 1)[0] for s in semboller})
        out["tum_semboller"] = sorted(s.name for s in semboller)
        adaylar = [s for s in semboller if any(p.upper() in s.name.upper() for p in ADAY[hesap])]
        out["adaylar"] = []
        for s in adaylar[:80]:
            mt5.symbol_select(s.name, True)
            out["adaylar"].append(ozellik(mt5.symbol_info(s.name) or s))
        iz("adaylar", len(adaylar))
        time.sleep(3)  # seçilen semboller için tik gelsin
        out["tikler"] = {s.name: ad(mt5.symbol_info_tick(s.name)) for s in adaylar[:80]}
        if "--gecmis" in sys.argv:
            out["gecmis"] = gecmis(hesap)
        if "--ornekle" in sys.argv:
            i = sys.argv.index("--ornekle")
            out["ornek"] = ornekle(float(sys.argv[i + 1]), sys.argv[i + 2].split(","))
        if "--emir" in sys.argv:
            hedef = sys.argv[sys.argv.index("--emir") + 1] if len(sys.argv) > sys.argv.index("--emir") + 1 else None
            out["emir"] = emir_testi(hedef) if hedef else {"hata": "sembol verilmedi"}
    finally:
        mt5.shutdown()
    yaz(hesap, out)


def ornekle(dk: float, semboller: list[str], aralik: float = 5.0) -> dict:
    """`dk` dakika boyunca her `aralik` sn'de bid/ask. Spread (fiyat, nokta, baz puan) ve sunucu saatinin UTC'den farkı
    (tik zamanı − gerçek UTC; barlar sunucu saatiyle damgalı, kural 11 için köprü dönüştürecek)."""
    import statistics as st
    for x in semboller:
        mt5.symbol_select(x, True)
    time.sleep(3)
    ham: dict[str, list] = {x: [] for x in semboller}
    fark: list[float] = []
    bitis = time.time() + dk * 60
    while time.time() < bitis:
        for x in semboller:
            t = mt5.symbol_info_tick(x)
            if t is None or t.bid <= 0 or t.ask <= 0:
                continue
            simdi = time.time()
            ham[x].append((t.time_msc, t.bid, t.ask))
            if simdi - t.time_msc / 1000 > -86_400:
                fark.append(t.time_msc / 1000 - simdi)
        time.sleep(aralik)
    out = {"sunucu_utc_fark_sn": {"medyan": st.median(fark) if fark else None,
                                  "saat": round(st.median(fark) / 3600) if fark else None, "n": len(fark)}}
    for x, r in ham.items():
        info = mt5.symbol_info(x)
        tekil = sorted({(m, b, a) for m, b, a in r})
        if not tekil:
            out[x] = {"n": 0}
            continue
        sp = [a - b for _, b, a in tekil]
        bp = [(a - b) / ((a + b) / 2) * 1e4 for _, b, a in tekil]
        out[x] = {"n": len(r), "tekil_tik": len(tekil), "spread_medyan": st.median(sp), "spread_max": max(sp),
                  "spread_nokta_medyan": st.median(sp) / info.point, "spread_bp_medyan": round(st.median(bp), 3),
                  "spread_bp_p90": round(sorted(bp)[int(0.9 * (len(bp) - 1))], 3), "son_bid": tekil[-1][1],
                  "son_ask": tekil[-1][2], "son_tik_msc": tekil[-1][0]}
    return out


def gecmis(hesap: str) -> dict:
    """Her sembol için M1/M15/H1/D1 derinliği."""
    out = {}
    for ad_ in GECMIS[hesap]:
        mt5.symbol_select(ad_, True)
        g = {}
        for adi, tf in (("M1", mt5.TIMEFRAME_M1), ("M15", mt5.TIMEFRAME_M15), ("H1", mt5.TIMEFRAME_H1),
                        ("D1", mt5.TIMEFRAME_D1)):
            r, hata = mumlar(ad_, tf)
            g[adi] = {"hata": hata} if r is None else {
                "adet": int(len(r)), "ilk": datetime.fromtimestamp(int(r[0]["time"]), UTC).isoformat(),
                "son": datetime.fromtimestamp(int(r[-1]["time"]), UTC).isoformat(),
                "son_bar": {k: float(r[-1][k]) for k in ("open", "high", "low", "close", "tick_volume", "spread",
                                                          "real_volume")}}
        out[ad_] = g
    return out


def yaz(hesap: str, out: dict) -> None:
    ek = "_emir" if "emir" in out else ("_ornek" if "ornek" in out else "")
    yol = KOK / "log" / f"mt5_{hesap}{ek}.json"
    yol.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
    print(yol)


if __name__ == "__main__":
    main()
