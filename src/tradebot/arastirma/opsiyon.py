"""Dalga 4 — opsiyon oynaklık primi: tanımlı riskli haftalık opsiyon satışı backtest'i (saf; I/O yok).

Her Cuma 08:05 UTC'de bir sonraki Cuma vadeli yapı açılır, vadede (Deribit teslim fiyatıyla) kapanır. Oynaklıklar o
haftanın gerçek işlemlerinden (`veri/deribit.py` haftalık yüzey); kullanım fiyatı hedef deltadan çözülür.

Maliyet (aleyhte, kural 4): satılan bacak `iv − yarım spread`, alınan bacak `iv + yarım spread` ile fiyatlanır; Deribit
işlem ücreti bacak başına min(%0,03 × dayanak, %12,5 × prim), teslim ücreti vadede içsel değeri olan bacakta
min(%0,015 × dayanak, %12,5 × içsel değer). Faiz 0 (haftalık vadede ihmal; aleyhte değil, nötr).

Boyut: haftalık azami kayıp (en geniş kanat − net prim) özkaynağın `risk` kadarı. Dolayısıyla haftalık getiri =
risk × (birim sonuç / birim azami kayıp); en kötü hafta −risk ile sınırlıdır (tanımlı risk). Açığa satılan kontratların
nominali özkaynağın `KALDIRAC_TAVANI` katını aşarsa boyut tavana kırpılır (kural 6).
"""
from __future__ import annotations

import math
from dataclasses import dataclass
from statistics import NormalDist

import numpy as np

from tradebot.cekirdek.boyut import KALDIRAC_TAVANI

_N = NormalDist()
YIL_SN = 365.0 * 86_400
HEDEF_DELTA = {"p25": 0.25, "p10": 0.10, "c25": 0.25, "c10": 0.10}
# (tür, kova, yön: −1 satılır, +1 alınır)
YAPILAR = {
    "iron_condor": (("P", "p25", -1), ("P", "p10", +1), ("C", "c25", -1), ("C", "c10", +1)),
    "put_spread": (("P", "p25", -1), ("P", "p10", +1)),
    "call_spread": (("C", "c25", -1), ("C", "c10", +1)),
}


@dataclass(frozen=True)
class Maliyet:
    yarim_spread_25: float = 1.5      # oynaklık puanı
    yarim_spread_10: float = 2.0
    islem_ucreti: float = 0.0003      # × dayanak
    teslim_ucreti: float = 0.00015
    ucret_tavani: float = 0.125       # × prim / içsel değer

    def kat(self, k: float) -> Maliyet:
        return Maliyet(self.yarim_spread_25 * k, self.yarim_spread_10 * k, self.islem_ucreti * k, self.teslim_ucreti * k,
                       self.ucret_tavani)


def bs(S: float, K: float, T: float, iv: float, tur: str) -> float:
    """Black-Scholes fiyatı (faiz 0; iv ondalık)."""
    if T <= 0 or iv <= 0:
        return max(0.0, (S - K) if tur == "C" else (K - S))
    s = iv * math.sqrt(T)
    d1 = (math.log(S / K) + 0.5 * s * s) / s
    d2 = d1 - s
    if tur == "C":
        return S * _N.cdf(d1) - K * _N.cdf(d2)
    return K * _N.cdf(-d2) - S * _N.cdf(-d1)


def deltadan_kullanim(S: float, T: float, iv: float, tur: str, hedef: float) -> float:
    """|Δ| = hedef olan kullanım fiyatı (call: N(d1) = Δ; put: N(d1) − 1 = −Δ)."""
    d1 = _N.inv_cdf(hedef) if tur == "C" else _N.inv_cdf(1 - hedef)
    s = iv * math.sqrt(T)
    return S * math.exp(-(d1 * s - 0.5 * s * s))


@dataclass(frozen=True)
class HaftaSonucu:
    giris_ms: int
    getiri: float          # özkaynağa oran
    prim: float            # net prim / dayanak
    azami_kayip: float     # birim azami kayıp / dayanak
    nominal: float         # açığa satılan nominal / özkaynak
    kurulmadi: str | None = None


def hafta(yuzey: dict, S_T: float | None, yapi: str, risk: float, m: Maliyet) -> HaftaSonucu:
    """Bir haftalık döngü. `yuzey`: giris_ms, vade_ms, endeks, kovalar (yüzde oynaklık)."""
    g = int(yuzey["giris_ms"])
    S = yuzey.get("endeks")
    bacaklar = YAPILAR[yapi]
    if S is None or S_T is None or any(yuzey.get(k) is None for _, k, _ in bacaklar):
        return HaftaSonucu(g, 0.0, 0.0, 0.0, 0.0, "eksik veri")
    T = (int(yuzey["vade_ms"]) - g) / 1000 / YIL_SN
    net_prim, sonuc_vade, giris_ucret, teslim_ucret = 0.0, 0.0, 0.0, 0.0
    kullanim: dict[str, float] = {}
    for tur, kova, yon in bacaklar:
        iv = yuzey[kova] / 100
        K = deltadan_kullanim(S, T, iv, tur, HEDEF_DELTA[kova])
        kullanim[kova] = K
        yarim = (m.yarim_spread_25 if kova.endswith("25") else m.yarim_spread_10) / 100
        fiyat = bs(S, K, T, max(iv + yarim * yon, 0.01), tur)   # satışta düşük, alışta yüksek oynaklık (aleyhte)
        net_prim += -yon * fiyat
        giris_ucret += min(m.islem_ucreti * S, m.ucret_tavani * fiyat)
        icsel = max(0.0, (S_T - K) if tur == "C" else (K - S_T))
        sonuc_vade += yon * icsel
        if icsel > 0:
            teslim_ucret += min(m.teslim_ucreti * S_T, m.ucret_tavani * icsel)
    genislik = max(kullanim.get("p25", 0) - kullanim.get("p10", 0), kullanim.get("c10", 0) - kullanim.get("c25", 0))
    # Boyut yalnız girişte bilinenle (kural 3): en kötü durumda iki bacak içsel değerli, teslim ücreti dayanağa göre
    azami = genislik - net_prim + giris_ucret + 2 * m.teslim_ucreti * S
    ucret = giris_ucret + teslim_ucret
    if azami <= 0 or net_prim <= 0:
        return HaftaSonucu(g, 0.0, net_prim / S, azami / S, 0.0, "prim yok")
    birim = net_prim + sonuc_vade - ucret        # bir kontratın sonucu ($)
    adet = risk / azami                          # özkaynak 1 için kontrat (dayanak birimi)
    satilan = sum(1 for _, _, yon in bacaklar if yon < 0)
    nominal = adet * S * satilan
    if nominal > KALDIRAC_TAVANI:
        adet *= KALDIRAC_TAVANI / nominal
        nominal = KALDIRAC_TAVANI
    return HaftaSonucu(g, adet * birim, net_prim / S, azami / S, nominal)


def kos(yuzeyler: list[dict], teslim: dict[str, float], yapi: str, risk: float, m: Maliyet) -> list[HaftaSonucu]:
    """Haftalık döngüler (sıralı). `teslim`: {"YYYY-MM-DD": 08:00 UTC teslim fiyatı}."""
    from datetime import UTC, datetime

    out = []
    for y in sorted(yuzeyler, key=lambda x: x["giris_ms"]):
        gun = datetime.fromtimestamp(int(y["vade_ms"]) / 1000, UTC).date().isoformat()
        out.append(hafta(y, teslim.get(gun), yapi, risk, m))
    return out


def ozet(sonuclar: list[HaftaSonucu]) -> dict:
    """Haftalık getirilerden metrikler (hafta = gözlem; kurulmayan hafta 0 getiri, nakitte)."""
    from datetime import UTC, datetime

    r = np.array([s.getiri for s in sonuclar])
    if len(r) < 10:
        return {"hafta": int(len(r))}
    oz = np.cumprod(1 + r)
    tepe = np.maximum.accumulate(np.r_[1.0, oz])[1:]
    yil = len(r) / 52.1775
    yillar: dict[int, list[float]] = {}
    for s in sonuclar:
        yillar.setdefault(datetime.fromtimestamp(s.giris_ms / 1000, UTC).year, []).append(s.getiri)
    yillik = {y: float(np.prod(1 + np.array(v)) - 1) for y, v in sorted(yillar.items())}
    kurulan = [s for s in sonuclar if s.kurulmadi is None]
    return {
        "hafta": int(len(r)), "kurulan": len(kurulan),
        "yillik_bilesik": float(oz[-1] ** (1 / yil) - 1), "sharpe": float(r.mean() / r.std(ddof=1) * math.sqrt(52.1775))
        if r.std(ddof=1) > 0 else 0.0,
        "sr_haftalik": float(r.mean() / r.std(ddof=1)) if r.std(ddof=1) > 0 else 0.0,
        "en_kotu_hafta": float(r.min()), "en_iyi_hafta": float(r.max()), "kazanan_hafta": float((r > 0).mean()),
        "en_kotu_dusus": float((oz / tepe - 1).min()), "yillik": yillik,
        "yil_pozitif_orani": float(np.mean([v > 0 for v in yillik.values()])),
        "ort_prim": float(np.mean([s.prim for s in kurulan])) if kurulan else 0.0,
        "ort_nominal": float(np.mean([s.nominal for s in kurulan])) if kurulan else 0.0,
    }
