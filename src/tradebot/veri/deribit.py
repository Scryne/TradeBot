"""Deribit opsiyon verisi (Dalga 4, oynaklık primi): haftalık oynaklık yüzeyi ve uzlaşma fiyatları.

Kaynak: herkese açık tarihsel sunucu (`history.deribit.com`, anahtarsız). Her işlem kaydı örtük oynaklığı (`iv`),
dayanak endeksi (`index_price`) ve enstrüman adını (vade, kullanım fiyatı, tür) taşır. Ham sayfalar ham depoya yazılır
(hash kimliktir, kural 9); yüzey hamdan yeniden üretilir.

Haftalık yüzey (sonuca bakmadan, 2026-09-28): Deribit haftalık opsiyonları Cuma 08:00 UTC'de vadelenir. Giriş anı Cuma
08:05; o andan sonraki `PENCERE_DK` dakikada bir sonraki Cuma vadesine yapılan işlemlerden, Black-Scholes deltasıyla
kovalanarak medyan oynaklık: ATM (|K/S − 1| ≤ %2), %25 delta put/call (|Δ| 0,18–0,32), %10 delta put/call (|Δ| 0,06–0,14).
Kovada `ASGARI_ISLEM`'den az işlem varsa değer boş (o hafta o yapı kurulmaz).
"""
from __future__ import annotations

import json
import math
from datetime import UTC, datetime, timedelta

import numpy as np

TARIH = "https://history.deribit.com/api/v2/public/get_last_trades_by_currency_and_time"
TESLIM = "https://www.deribit.com/api/v2/public/get_delivery_prices"
PENCERE_DK = 60
ASGARI_ISLEM = 3
GUN_MS = 86_400_000
YIL_SN = 365.0 * 86_400
AYLAR = {a: i + 1 for i, a in enumerate(["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"])}
KOVALAR = {"p25": ("P", 0.18, 0.32), "p10": ("P", 0.06, 0.14), "c25": ("C", 0.18, 0.32), "c10": ("C", 0.06, 0.14)}


def cumalar(bas: datetime, bit: datetime) -> list[datetime]:
    """[bas, bit) arasındaki Cuma 08:00 UTC anları."""
    g = datetime(bas.year, bas.month, bas.day, 8, tzinfo=UTC)
    g += timedelta(days=(4 - g.weekday()) % 7)
    out = []
    while g < bit:
        out.append(g)
        g += timedelta(days=7)
    return out


def enstruman_coz(ad: str) -> tuple[datetime, float, str] | None:
    """`BTC-11MAR22-42000-P` → (vade 08:00 UTC, kullanım fiyatı, "P"|"C")."""
    try:
        _, v, k, t = ad.split("-")
        gun, ay, yil = int(v[:-5]), AYLAR[v[-5:-2]], 2000 + int(v[-2:])
        return datetime(yil, ay, gun, 8, tzinfo=UTC), float(k.replace("d", ".")), t
    except (ValueError, KeyError):
        return None


def _N(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def delta(S: float, K: float, T: float, iv: float, tur: str) -> float:
    """Black-Scholes deltası (faiz 0; `iv` ondalık, `T` yıl)."""
    if T <= 0 or iv <= 0:
        return float("nan")
    d1 = (math.log(S / K) + 0.5 * iv * iv * T) / (iv * math.sqrt(T))
    return _N(d1) if tur == "C" else _N(d1) - 1


def yuzey(islemler: list[dict], vade: datetime) -> dict:
    """Bir giriş penceresinin işlemlerinden hedef vadenin oynaklık kovaları (yüzde oynaklık, ör. 62,4)."""
    kova: dict[str, list[float]] = {"atm": [], **{k: [] for k in KOVALAR}}
    endeks = []
    for x in islemler:
        c = enstruman_coz(x["instrument_name"])
        if c is None or c[0] != vade or not x.get("iv"):
            continue
        _, K, tur = c
        S = float(x["index_price"])
        T = (vade.timestamp() * 1000 - x["timestamp"]) / 1000 / YIL_SN
        iv = float(x["iv"]) / 100
        endeks.append(S)
        if abs(K / S - 1) <= 0.02:
            kova["atm"].append(iv * 100)
        d = abs(delta(S, K, T, iv, tur))
        for ad, (t, alt, ust) in KOVALAR.items():
            if tur == t and alt <= d <= ust:
                kova[ad].append(iv * 100)
    out = {ad: (float(np.median(v)) if len(v) >= ASGARI_ISLEM else None) for ad, v in kova.items()}
    out |= {f"n_{ad}": len(v) for ad, v in kova.items()}
    out["endeks"] = float(np.median(endeks)) if endeks else None
    return out


class DeribitGecmis:
    def __init__(self, ham, http_al) -> None:
        self.ham, self.al = ham, http_al

    def pencere(self, para: str, bas_ms: int, bit_ms: int) -> list[dict]:
        """[bas, bit) opsiyon işlemleri (sayfalı). Her sayfa ham depoya."""
        out, t = [], bas_ms
        while t < bit_ms:
            anahtar = f"{para}/option/{bas_ms}/{t}"
            icerik = self._onbellek(anahtar)
            if icerik is None:   # geçmiş pencere değişmez: indirilen sayfa bir daha istenmez
                u = (f"{TARIH}?currency={para}&kind=option&start_timestamp={t}&end_timestamp={bit_ms}&count=1000"
                     "&sorting=asc&include_old=true")
                icerik = self.al(u)
                self.ham.kaydet("deribit", anahtar, icerik, "json")
            r = json.loads(icerik)["result"]
            islem = r["trades"]
            out += islem
            if not r.get("has_more") or not islem:
                break
            t = int(islem[-1]["timestamp"]) + 1
        return out

    def _onbellek(self, anahtar: str) -> bytes | None:
        from pathlib import Path

        from sqlalchemy import select

        from tradebot.db import ham_dosya

        with self.ham.motor.connect() as b:
            yol = b.execute(select(ham_dosya.c.yol).where(ham_dosya.c.kaynak == "deribit", ham_dosya.c.anahtar == anahtar)
                            .order_by(ham_dosya.c.id.desc()).limit(1)).scalar()
        return Path(yol).read_bytes() if yol and Path(yol).exists() else None

    def haftalik(self, para: str, cuma: datetime) -> dict:
        bas = int((cuma + timedelta(minutes=5)).timestamp() * 1000)
        islem = self.pencere(para, bas, bas + PENCERE_DK * 60_000)
        vade = cuma + timedelta(days=7)
        return {"para": para, "giris_ms": bas, "vade_ms": int(vade.timestamp() * 1000), **yuzey(islem, vade)}

    def teslim_fiyatlari(self, para: str) -> dict[str, float]:
        """{"2026-09-28": fiyat} — Deribit'in 08:00 UTC uzlaşma (teslim) fiyatı."""
        out, ofset = {}, 0
        while True:
            icerik = self.al(f"{TESLIM}?index_name={para.lower()}_usd&offset={ofset}&count=1000")
            r = json.loads(icerik)["result"]
            for x in r["data"]:
                out[x["date"]] = float(x["delivery_price"])
            ofset += len(r["data"])
            if not r["data"] or ofset >= r["records_total"]:
                break
        self.ham.kaydet("deribit", f"{para}/teslim/{datetime.now(UTC).date().isoformat()}", json.dumps(out).encode(), "json")
        return out
