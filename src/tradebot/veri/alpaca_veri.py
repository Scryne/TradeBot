"""Alpaca Market Data v2 indiricisi (Nasdaq-100 tarihî üyeleri + QQQ gün içi). Anahtar: Alpaca PAPER hesabı (ücretsiz
plan: SIP tarihsel, son 15 dk hariç, 2016'dan; 200 istek/dk).

Neden: Yahoo yalnız bugün işlem gören sembolleri tutar (271 tarihî üyenin 74'ü yok). Alpaca kapanan ve satın alınan
şirketlerin geçmişini de verir (ATVI, CELG, XLNX, SPLK ölçüldü, 2026-10-18) ve `asof` ile o gün işlem gören sembolden
sorgulanabilir (FB, 2020 → Meta'nın geçmişi; bugünkü FB bir ETF). Böylece 2016+ dönemde evren hayatta kalma yanlılığından
büyük ölçüde arınır.

Kurallar:
- Her sayfa ham olarak saklanır (ham değişmez, hash kimlik; kural 9). Barlar ayrı depoda: `veri/alpaca/bar/` (Yahoo
  deposuna karışmaz; grup tanımında `depo: alpaca`).
- Günlük bar `t`'si New York gece yarısıdır (04:00/05:00 UTC): seans günü 00:00 UTC'ye etiketlenir (Yahoo ile aynı).
- `adjustment=all`: OHLC bölünme + temettü düzeltmeli (toplam getiri); `adj_close` = close.
- Gün içi (30 dk): Alpaca uzatılmış seans barlarını da verir (04:00–20:00 ET). Saklanır: 16:00 barının açılışı
  gün içi çıkışın dolum fiyatıdır (yalnız normal seans tutulsaydı çıkış ertesi sabaha kayardı).
"""
from __future__ import annotations

import json
import time
from datetime import UTC, datetime

import httpx
import polars as pl

from tradebot.kayit import log
from tradebot.veri import nasdaq100 as nq
from tradebot.veri.depo import BarDepo, HamDepo
from tradebot.veri.takvim import gun_basi

URL = "https://data.alpaca.markets/v2/stocks/bars"
KAYNAK = "alpaca"
BASLANGIC = "2016-01-01"
TF = {"1d": "1Day", "30m": "30Min", "1h": "1Hour"}
_log = log("veri.alpaca")


def _ms(s: str) -> int:
    return int(datetime.fromisoformat(s.replace("Z", "+00:00")).timestamp() * 1000)


def _iso(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def sayfa_coz(icerik: bytes, sembol: str, zd: str) -> pl.DataFrame:
    d = json.loads(icerik)
    b = (d.get("bars") or {}).get(sembol) or []
    if not b:
        return pl.DataFrame()
    t = [_ms(x["t"]) for x in b]
    acilis = [gun_basi(x) for x in t] if zd == "1d" else t
    df = pl.DataFrame({"acilis_ms": acilis, "open": [float(x["o"]) for x in b], "high": [float(x["h"]) for x in b],
                       "low": [float(x["l"]) for x in b], "close": [float(x["c"]) for x in b],
                       "volume": [float(x["v"]) for x in b]})
    return df.with_columns(pl.col("close").alias("adj_close")).unique("acilis_ms", keep="last").sort("acilis_ms")


class AlpacaVeri:
    def __init__(self, anahtar: str, gizli: str, ham: HamDepo, depo: BarDepo, aralik_sn: float = 0.32,
                 istemci: httpx.Client | None = None) -> None:
        self.ham, self.depo, self.aralik = ham, depo, aralik_sn
        self._c = istemci or httpx.Client(timeout=60, headers={"APCA-API-KEY-ID": anahtar, "APCA-API-SECRET-KEY": gizli})
        self._son = 0.0

    def _al(self, params: dict) -> bytes:
        for i in range(6):
            bekle = self.aralik - (time.monotonic() - self._son)
            if bekle > 0:
                time.sleep(bekle)
            self._son = time.monotonic()
            try:
                r = self._c.get(URL, params=params)
            except httpx.HTTPError as e:
                _log.warning("alpaca_veri_yeniden", hata=str(e)[:120], deneme=i + 1)
                time.sleep(2 ** i)
                continue
            if r.status_code == 429 or r.status_code >= 500:
                time.sleep(max(2 ** i, float(r.headers.get("Retry-After", 0) or 0)))
                continue
            r.raise_for_status()
            return r.content
        raise RuntimeError(f"alpaca veri: {params.get('symbols')} alınamadı")

    def bars(self, sembol: str, zd: str, bas_ms: int, bit_ms: int, asof: str | None = None) -> pl.DataFrame:
        """[bas, bit) aralığının barları (sayfalı). Her sayfa ham depoya."""
        params = {"symbols": sembol, "timeframe": TF[zd], "start": _iso(bas_ms), "end": _iso(bit_ms),
                  "adjustment": "all", "feed": "sip", "limit": 10000, "sort": "asc"}
        if asof:
            params["asof"] = asof
        parcalar, sayfa = [], 0
        while True:
            icerik = self._al(params)
            anahtar = f"bars/{zd}/{sembol}/{asof or '-'}/{_iso(bas_ms)[:10]}_{_iso(bit_ms)[:10]}/{sayfa}"
            self.ham.kaydet(KAYNAK, anahtar, icerik, "json")
            df = sayfa_coz(icerik, sembol, zd)
            if len(df):
                parcalar.append(df)
            tok = json.loads(icerik).get("next_page_token")
            if not tok:
                break
            params["page_token"], sayfa = tok, sayfa + 1
        return pl.concat(parcalar).unique("acilis_ms", keep="last").sort("acilis_ms") if parcalar else pl.DataFrame()


def sorgular(ayar: dict, yillar: dict[int, bytes], simdi_ms: int, piyasa: str = "NASDAQ") -> list[tuple[str, str, str, int]]:
    """Her üyelik dönemi için (kimlik, o gün işlem gören sembol, asof tarihi, bitiş ms): kimlik eşlemesi
    `nasdaq100.kimlik_donemleri` ile aynı. Yalnız 2016'dan sonraya uzanan dönemler (Alpaca geçmişi 2016'dan)."""
    esle, disla = ayar.get("sembol_esleme") or {}, set((ayar.get("dislanan") or {}).keys())
    bas2016 = int(datetime(2016, 1, 1, tzinfo=UTC).timestamp() * 1000)
    out = []
    for d in nq.donemler(yillar):
        if d.sembol in disla or (d.bit_ms is not None and d.bit_ms < bas2016):
            continue
        son = min(d.bit_ms - 86_400_000 if d.bit_ms is not None else simdi_ms, simdi_ms)
        asof = datetime.fromtimestamp(son / 1000, UTC).strftime("%Y-%m-%d")
        out.append((f"{piyasa}:{esle.get(d.sembol, d.sembol)}", d.sembol, asof,
                    simdi_ms if d.bit_ms is None else min(d.bit_ms + 5 * 86_400_000, simdi_ms)))
    return out


def guncelle(a, m, yalniz_guncel: bool = False, gun_ici: bool = True) -> dict:
    """Bütün (ya da bugünkü) Nasdaq-100 üyelik dönemlerinin günlük barları + QQQ 30 dk. Aynı kimliğin dönemleri
    birleştirilir (FB + META → NASDAQ:META)."""
    from tradebot.veri import nasdaq as nqv

    if a.alpaca_anahtar is None or a.alpaca_gizli is None:
        raise RuntimeError("Alpaca anahtarı yok (TRADEBOT_ALPACA_ANAHTAR/GIZLI)")
    ham = HamDepo(a.veri_dizini, m)
    depo = BarDepo(a.veri_dizini / "alpaca")
    av = AlpacaVeri(a.alpaca_anahtar.get_secret_value(), a.alpaca_gizli.get_secret_value(), ham, depo)
    ayar = nq.ayar_oku()
    yillar = nq.yerel(ham, ayar) or nq.indir(ham, ayar)
    uy = nqv.uyelik_yukle(ham, ayar)
    nqv.uyelik_yaz(a.veri_dizini / "alpaca", uy, ayar["uyelik"]["commit"])   # Alpaca deposunun yanında da
    simdi = int(time.time() * 1000) - 20 * 60_000                                # ücretsiz plan: son 15 dk SIP yok
    bas = int(datetime.fromisoformat(BASLANGIC).replace(tzinfo=UTC).timestamp() * 1000)
    hepsi = sorgular(ayar, yillar, simdi)
    if yalniz_guncel:
        guncel = set(uy.uyeler(simdi))
        hepsi = [q for q in hepsi if q[0] in guncel and q[3] >= simdi - 86_400_000]
    birlesik: dict[str, list[pl.DataFrame]] = {}
    bos, hata = [], []
    for kimlik, sembol, asof, bit in hepsi:
        try:
            df = av.bars(sembol, "1d", bas, bit, asof)
        except Exception as e:  # noqa: BLE001 — bir sembol diğerlerini durdurmaz
            hata.append(sembol)
            _log.error("alpaca_sembol_hatasi", sembol=sembol, hata=f"{type(e).__name__}: {e}"[:200])
            continue
        if df.is_empty():
            bos.append(sembol)
            continue
        birlesik.setdefault(kimlik, []).append(df)
    for kimlik, dfs in birlesik.items():
        depo.yaz(kimlik, "1d", pl.concat(dfs).unique("acilis_ms", keep="last").sort("acilis_ms"), birlestir=False)
    out = {"donem": len(hepsi), "kimlik": len(birlesik), "bos": bos[:30], "bos_sayi": len(bos), "hata": hata[:20]}
    if gun_ici:
        df = av.bars("QQQ", "30m", bas, simdi)
        if len(df):
            depo.yaz("ARCA:QQQ", "30m", df, birlestir=False)
        out["qqq_30m"] = len(df)
    return out
