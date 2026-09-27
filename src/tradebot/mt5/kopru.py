"""MT5 köprüsü (Faz 8, Spike 08): host Windows'ta hesap başına bir süreç; Docker'daki sistem HTTP ile okur.

    uv run --no-project --python 3.12 --with MetaTrader5 src/tradebot/mt5/kopru.py --hesap forex --port 8765

Kendi başına çalışır (yalnız standart kütüphane + MetaTrader5; tradebot paketini içe aktarmaz: Windows'ta yalnız bu
dosya koşar). Yalnız 127.0.0.1'i dinler; Docker Desktop `host.docker.internal`'ı buraya yönlendirir. Sır döndürmez.

Uç noktalar (JSON):
- `/saglik`: terminal bağlı mı, hesap, sunucu saat farkı, en taze tikin yaşı.
- `/semboller?ad=A,B`: sözleşme özellikleri (ad yoksa yalnız adlar ve grupları).
- `/mumlar?sembol=GOLD&tf=M15&bas_ms=..&bit_ms=..`: yalnız KAPANMIŞ barlar (kural 4), açılış zamanı UTC ms (kural 11).
- `/kotasyon?semboller=A,B`: son bid/ask, tik zamanı UTC ms.

Emir yolu yok: paper'da dolum Nautilus sandbox'ta (Spike 05). Gerçek para fazında ayrı kararla eklenir.

Zaman: MT5 zaman damgaları sunucu saatidir. Fark en taze tikten ölçülür (tik − gerçek UTC, 15 dk'ya yuvarlanır, üç
ardışık ölçüm aynıysa kabul). Ölçüm yoksa (hafta sonu) `--fark-sn` (NCM: İstanbul, +3 saat). Yaz saati geçişi olan bir
sunucuda fark değişirse ölçüm yakalar; geçmiş barlar tek farkla çevrildiği için geçiş öncesi barlar `/saglik`'teki
farkla yeniden doğrulanmalı.

Takılma: bütün MT5 çağrıları tek işçi iş parçacığından geçer (paket iş parçacığı güvenli değil) ve süre sınırlıdır.
Spike 08'de büyük bir geçmiş isteği süreci 30 dk takılı bıraktı: bir çağrı `takilma_sn`'yi aşarsa süreç kendini
sonlandırır, gözetmen betiği (`tools/host/mt5kopru.ps1`) terminal dahil yeniden başlatır.
"""
from __future__ import annotations

import argparse
import json
import os
import queue
import sys
import threading
import time
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ZD = {"M1": ("TIMEFRAME_M1", 60), "M5": ("TIMEFRAME_M5", 300), "M15": ("TIMEFRAME_M15", 900),
      "M30": ("TIMEFRAME_M30", 1800), "H1": ("TIMEFRAME_H1", 3600), "H4": ("TIMEFRAME_H4", 14_400),
      "D1": ("TIMEFRAME_D1", 86_400)}
SUTUNLAR = ["acilis_ms", "open", "high", "low", "close", "tick_volume", "spread", "real_volume"]
IZLE = {"forex": "EURUSD,GOLD,USDJPY,GBPUSD", "viop": "XU30_YAKINVADE"}   # Spike 08'deki adlar
EN_COK_BAR = 20_000          # tek istekte; istemci sayfalar (Spike 08: 20 000 sorunsuz, 100 000 M1 takıldı)
ADIM_MS = 900_000            # sunucu saat farkı 15 dk'nın katıdır
OZELLIKLER = ("name", "path", "description", "currency_base", "currency_profit", "currency_margin", "digits", "point",
              "trade_contract_size", "trade_tick_size", "trade_tick_value", "volume_min", "volume_step", "volume_max",
              "trade_mode", "trade_exemode", "filling_mode", "swap_long", "swap_short", "swap_mode", "margin_initial",
              "margin_maintenance", "expiration_time", "trade_stops_level")


def _log(olay: str, **alan) -> None:
    print(json.dumps({"zaman": datetime.now(UTC).isoformat(), "olay": olay, **alan}, ensure_ascii=False,
                     default=str), flush=True)


def fark_adayi(tik_ms: int, simdi_ms: int, tolerans_ms: int = 60_000) -> int | None:
    """Taze bir tikten sunucu − UTC farkı. Fark 15 dk'nın katı değilse ya da ±14 saati aşıyorsa tik bayattır: None."""
    ham = tik_ms - simdi_ms
    aday = round(ham / ADIM_MS) * ADIM_MS
    if abs(ham - aday) > tolerans_ms or abs(aday) > 14 * 3_600_000:
        return None
    return aday


def kapanmis_barlar(satirlar: list[tuple], fark_ms: int, zd_sn: int, simdi_ms: int) -> list[list]:
    """MT5 oranları (sunucu saniyesi, ...) → [UTC açılış ms, ...]; kapanışı gelmemiş bar atılır (kural 4)."""
    out = []
    for r in satirlar:
        acilis = int(r[0]) * 1000 - fark_ms
        if acilis + zd_sn * 1000 <= simdi_ms:
            out.append([acilis, *(float(x) for x in r[1:5]), int(r[5]), int(r[6]), int(r[7])])
    return out


class ZamanAsimi(Exception):
    pass


class Isci:
    """MT5 çağrılarını tek iş parçacığında sırayla koşar. `calistir` sonucu bekler; süre aşılırsa ZamanAsimi."""

    def __init__(self, takilma_sn: float, cik=lambda: os._exit(3)) -> None:
        self.kuyruk: queue.Queue = queue.Queue()
        self.takilma_sn, self._cik = takilma_sn, cik
        self.basladi: float | None = None   # şu anki çağrının başlangıcı
        threading.Thread(target=self._dongu, daemon=True).start()
        threading.Thread(target=self._bekci, daemon=True).start()

    def _dongu(self) -> None:
        while True:
            fn, sonuc, bitti = self.kuyruk.get()
            self.basladi = time.monotonic()
            try:
                sonuc.append((True, fn()))
            except Exception as e:  # noqa: BLE001 — hata çağırana döner
                sonuc.append((False, e))
            finally:
                self.basladi = None
                bitti.set()

    def _bekci(self) -> None:
        while True:
            time.sleep(1)
            b = self.basladi
            if b is not None and time.monotonic() - b > self.takilma_sn:
                _log("mt5_takildi", sn=round(time.monotonic() - b))
                self._cik()
                return

    def calistir(self, fn, zaman_asimi: float = 30.0):
        sonuc: list = []
        bitti = threading.Event()
        self.kuyruk.put((fn, sonuc, bitti))
        if not bitti.wait(zaman_asimi):
            raise ZamanAsimi(f"MT5 çağrısı {zaman_asimi} sn içinde dönmedi")
        ok, deger = sonuc[0]
        if not ok:
            raise deger
        return deger


class Kopru:
    def __init__(self, mt5, isci: Isci, fark_varsayilan_ms: int, saat=lambda: int(time.time() * 1000)) -> None:
        self.mt5, self.isci, self.saat = mt5, isci, saat
        self.fark_varsayilan_ms = fark_varsayilan_ms
        self.fark_olculen_ms: int | None = None
        self._son_adaylar: list[int] = []
        self.izlenen: set[str] = set()      # kotasyonu istenmiş semboller: fark ölçümünde kullanılır
        self.son_taze_tik_ms: int | None = None

    @property
    def fark_ms(self) -> int:
        return self.fark_olculen_ms if self.fark_olculen_ms is not None else self.fark_varsayilan_ms

    def fark_olc(self) -> None:
        """İzlenen sembollerin en taze tikinden fark adayı; üç ardışık aynı aday gelince kabul edilir."""
        m = self.mt5
        tikler = [m.symbol_info_tick(s) for s in sorted(self.izlenen)]
        en_taze = max((t.time_msc for t in tikler if t is not None and t.time_msc), default=None)
        if en_taze is None:
            return
        aday = fark_adayi(en_taze, self.saat())
        if aday is None:
            return
        self.son_taze_tik_ms = en_taze - aday
        self._son_adaylar = (self._son_adaylar + [aday])[-3:]
        if len(self._son_adaylar) == 3 and len(set(self._son_adaylar)) == 1 and aday != self.fark_olculen_ms:
            _log("sunucu_farki", fark_sn=aday // 1000, onceki=self.fark_olculen_ms)
            self.fark_olculen_ms = aday

    # --- uç noktalar (her biri işçide koşar) ---
    def saglik(self) -> dict:
        m = self.mt5
        t, h = m.terminal_info(), m.account_info()
        simdi = self.saat()
        return {"bagli": bool(t and t.connected), "algo": bool(t and t.trade_allowed),
                "hesap": h.login if h else None, "sunucu": h.server if h else None,
                "para": h.currency if h else None, "fark_sn": self.fark_ms // 1000,
                "fark_kaynak": "olculen" if self.fark_olculen_ms is not None else "varsayilan",
                "taze_tik_yas_sn": None if self.son_taze_tik_ms is None else round((simdi - self.son_taze_tik_ms) / 1000),
                "izlenen": len(self.izlenen), "simdi_ms": simdi}

    def semboller(self, adlar: list[str]) -> dict:
        m = self.mt5
        if not adlar:
            return {"semboller": [[s.name, s.path] for s in (m.symbols_get() or ())]}
        out = {}
        for a in adlar:
            m.symbol_select(a, True)
            s = m.symbol_info(a)
            out[a] = None if s is None else {k: getattr(s, k, None) for k in OZELLIKLER}
        return {"semboller": out}

    def mumlar(self, sembol: str, zd: str, bas_ms: int, bit_ms: int) -> dict:
        m = self.mt5
        sabit, zd_sn = ZD[zd]
        bit_ms = min(bit_ms, bas_ms + EN_COK_BAR * zd_sn * 1000)
        m.symbol_select(sembol, True)
        bas = datetime.fromtimestamp((bas_ms + self.fark_ms) / 1000, UTC)
        bit = datetime.fromtimestamp((bit_ms + self.fark_ms) / 1000, UTC)
        r = m.copy_rates_range(sembol, getattr(m, sabit), bas, bit)
        if r is None:
            return {"hata": list(m.last_error()), "sutunlar": SUTUNLAR, "satirlar": []}
        satirlar = kapanmis_barlar([tuple(x) for x in r], self.fark_ms, zd_sn, self.saat())
        return {"sutunlar": SUTUNLAR, "satirlar": satirlar, "fark_sn": self.fark_ms // 1000, "istenen_bit_ms": bit_ms}

    def kotasyon(self, semboller: list[str]) -> dict:
        m = self.mt5
        out = {}
        for s in semboller:
            if s not in self.izlenen:
                m.symbol_select(s, True)
                self.izlenen.add(s)
            t = m.symbol_info_tick(s)
            out[s] = None if t is None or not t.time_msc else {
                "bid": t.bid, "ask": t.ask, "last": t.last, "tik_ms": t.time_msc - self.fark_ms}
        return {"kotasyon": out, "simdi_ms": self.saat(), "fark_sn": self.fark_ms // 1000}


def isleyici(k: Kopru, cagri_sn: float = 60.0):
    class Isleyici(BaseHTTPRequestHandler):
        def log_message(self, *a) -> None:   # erişim logu yok (dakikada bir yoklama)
            return

        def _yaz(self, kod: int, govde: dict) -> None:
            b = json.dumps(govde, ensure_ascii=False, default=str).encode()
            self.send_response(kod)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(b)))
            self.end_headers()
            self.wfile.write(b)

        def do_GET(self) -> None:  # noqa: N802
            u = urlparse(self.path)
            q = {a: v[0] for a, v in parse_qs(u.query).items()}
            liste = lambda ad: [x for x in q.get(ad, "").split(",") if x]  # noqa: E731
            try:
                if u.path == "/saglik":
                    fn = k.saglik
                elif u.path == "/semboller":
                    fn = lambda: k.semboller(liste("ad"))  # noqa: E731
                elif u.path == "/mumlar":
                    if q.get("tf") not in ZD:
                        return self._yaz(400, {"hata": f"tf ∈ {list(ZD)}"})
                    fn = lambda: k.mumlar(q["sembol"], q["tf"], int(q["bas_ms"]), int(q["bit_ms"]))  # noqa: E731
                elif u.path == "/kotasyon":
                    fn = lambda: k.kotasyon(liste("semboller"))  # noqa: E731
                else:
                    return self._yaz(404, {"hata": "yok"})
                self._yaz(200, k.isci.calistir(fn, cagri_sn))
            except ZamanAsimi as e:
                self._yaz(504, {"hata": str(e)})
            except (KeyError, ValueError) as e:
                self._yaz(400, {"hata": f"{type(e).__name__}: {e}"})
            except Exception as e:  # noqa: BLE001
                _log("istek_hatasi", yol=u.path, hata=f"{type(e).__name__}: {e}"[:300])
                self._yaz(500, {"hata": f"{type(e).__name__}: {e}"[:300]})

    return Isleyici


def env_oku(yol: Path) -> dict[str, str]:
    out = {}
    for satir in yol.read_text(encoding="utf-8").splitlines():
        if "=" in satir and not satir.lstrip().startswith("#"):
            a, v = satir.split("=", 1)
            out[a.strip()] = v.strip()
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--hesap", required=True, choices=["forex", "viop"])
    p.add_argument("--port", type=int, required=True)
    p.add_argument("--kok", default=r"C:\TradeBot")
    p.add_argument("--fark-sn", type=int, default=10_800)
    p.add_argument("--takilma-sn", type=float, default=180.0)
    p.add_argument("--izle", default=None, help="saat farkı ölçümü için likit semboller (virgüllü)")
    a = p.parse_args()

    import MetaTrader5 as mt5

    kok = Path(a.kok)
    e = env_oku(kok / "app" / ".env")
    anahtar = a.hesap.upper()
    isci = Isci(a.takilma_sn)

    def baglan() -> bool:
        return mt5.initialize(path=str(kok / "mt5" / a.hesap / "terminal64.exe"),
                              login=int(e[f"TRADEBOT_MT5_{anahtar}_LOGIN"]),
                              password=e[f"TRADEBOT_MT5_{anahtar}_SIFRE"], server=e["TRADEBOT_MT5_SUNUCU"],
                              portable=True, timeout=120_000)

    if not isci.calistir(baglan, 150):
        _log("baglanamadi", hata=mt5.last_error())
        sys.exit(2)
    k = Kopru(mt5, isci, a.fark_sn * 1000)
    izle = (a.izle or IZLE[a.hesap]).split(",")
    isci.calistir(lambda: k.kotasyon(izle))   # izlenenlere ekler (fark ölçümü)
    _log("basladi", hesap=a.hesap, port=a.port, paket=mt5.__version__)

    def arka_plan() -> None:
        """Dakikada bir: fark ölçümü; bağlantı düşerse yeniden bağlanma."""
        while True:
            time.sleep(60)
            try:
                bagli = isci.calistir(lambda: bool((mt5.terminal_info() or None) and mt5.terminal_info().connected))
                if not bagli:
                    _log("baglanti_yok")
                    isci.calistir(baglan, 150)
                isci.calistir(k.fark_olc)
            except Exception as ex:  # noqa: BLE001
                _log("arka_plan_hatasi", hata=f"{type(ex).__name__}: {ex}"[:300])

    threading.Thread(target=arka_plan, daemon=True).start()
    ThreadingHTTPServer(("127.0.0.1", a.port), isleyici(k)).serve_forever()


if __name__ == "__main__":
    main()
