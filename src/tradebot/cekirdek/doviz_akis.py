"""Döviz akış ve olay primleri (dalga 10; docs/turnuva/Dalga-10-Akis.md). Panel fonksiyonları, saf ve nedensel.

Her enstrüman USD karşılı bir paradır (`Panel.paralar[j]` yabancı para, `Panel.para_yon[j]` +1 XXXUSD / −1 USDXXX).
Ağırlıklar para uzayında kurulur, enstrümana `para_yon` ile çevrilir (USDJPY'de JPY uzun = USDJPY kısa).

Zaman kuralı: out[t] bar t'nin KAPANIŞINDA verilir, bar t+1 boyunca tutulur. Bir pencerede [E, X) tutulacak barlar,
açılışı (t + bar) bu aralıkta olanlardır: giriş E'deki barın açılışında, çıkış X'teki barın açılışında dolar.

- `fomc_dolar` (Mueller, Tahbaz-Salehi, Vedolin 2017, JF): planlı FOMC karar günlerinde USD sepete karşı değer kaybeder.
  Yabancı para sepeti uzun, önceki gün 21:00 UTC'den (NY kapanışı) pencere sonuna.
- `ay_sonu_hedge` (Melvin, Prins 2015, JIMF): ABD hisseleri ay içinde yabancı hisselerden iyi gittiyse yabancı yatırımcı
  kur riskini dengelemek için ay sonu 16:00 Londra fixing'inde USD satar (ve tersi). Ayın son iş günleri, fixing'e kadar.
- `seans_para` (Ranaldo 2009, JBF; Breedon, Ranaldo 2013, JMCB): paralar kendi ülkelerinin işlem saatlerinde değer
  kaybeder. ABD saatlerinde yabancı paralar uzun; `tam` türünde ayrıca her para kendi saatlerinde kısa.

Dış veriler (FOMC günleri, hisse endeksi günlük kapanışları) çekirdeğe dışarıdan verilir (`fomc_ayarla`,
`endeks_ayarla`; turnuva koşudan önce bir kez çağırır). Çekirdek G/Ç yapmaz. FOMC takvimi önceden ilan edilir; endeks
günü d'nin kapanışı ancak d + 1 gün 00:00 UTC'de kullanılır.
"""
from __future__ import annotations

import numpy as np

from tradebot.cekirdek.aileler import Panel

SAAT_MS = 3_600_000
GUN_MS = 86_400_000
NY_KAPANIS_SAAT = 21          # UTC; FOMC penceresi önceki günün bu saatinde başlar
FOMC_PENCERE = {"on": 16, "gun": 21, "iki": 24 + 21}   # karar günü 00:00 UTC'den pencere sonu (saat)
ABD_SEANS = (13, 21)          # UTC saat [bas, bit)
YEREL_SEANS = {"EUR": (7, 13), "GBP": (7, 13), "CHF": (7, 13), "JPY": (0, 7), "AUD": (0, 7), "NZD": (0, 7)}
HEDGE_PARA = ("EUR", "GBP", "JPY")   # kendi hisse endeksi olan paralar (ay sonu `kendi` ölçütü)

_FOMC = np.zeros(0, dtype=np.int64)
_ENDEKS: dict[str, tuple[np.ndarray, np.ndarray]] = {}


def fomc_ayarla(gunler_ms) -> None:
    """Planlı FOMC karar günleri (UTC gün başı, ms)."""
    global _FOMC
    _FOMC = np.sort(np.asarray(list(gunler_ms), dtype=np.int64))


def endeks_ayarla(seriler: dict[str, tuple[np.ndarray, np.ndarray]]) -> None:
    """Para → (günlük bar açılışı ms, kapanış). "USD" ABD endeksi, diğerleri o paranın ülke endeksi (yerel para)."""
    global _ENDEKS
    _ENDEKS = {k: (np.asarray(t, dtype=np.int64), np.asarray(c, dtype=float)) for k, (t, c) in seriler.items()}


def _bar_ms(t: np.ndarray) -> int:
    return int(np.min(np.diff(t))) if len(t) > 1 else SAAT_MS


def _sepet(p: Panel, aktif: np.ndarray, isaret: np.ndarray | None = None,
           paralar: tuple[str, ...] | None = None) -> np.ndarray:
    """Aktif barlarda seçili paraların eşit ağırlıklı sepeti (para başına ±1/m), enstrüman ağırlığına çevrilmiş."""
    if p.para_yon is None or p.paralar is None:
        raise ValueError("döviz akış: panelde para_yon/paralar yok (grup tanımında para: true)")
    n, k = p.close.shape
    sec = np.array([paralar is None or x in paralar for x in p.paralar])
    ev = p.evrende & sec[None, :]
    m = np.maximum(ev.sum(axis=1), 1)[:, None]
    yon = np.asarray(p.para_yon, dtype=float)[None, :]
    s = np.ones((n, 1)) if isaret is None else isaret[:, None]
    return np.where(ev & aktif[:, None], s * yon / m, 0.0)


# ------------------------------------------------------------------ FOMC günü dolar
def fomc_dolar(p: Panel, pencere: str = "gun") -> np.ndarray:
    """Planlı FOMC karar günü penceresinde yabancı para sepeti uzun (USD kısa). Pencere önceki gün 21:00 UTC'de
    başlar; `on`: karar günü 16:00 UTC (açıklamadan önce; FOMC öncesi kayma), `gun`: karar günü 21:00 UTC,
    `iki`: ertesi gün 21:00 UTC."""
    if pencere not in FOMC_PENCERE:
        raise ValueError(f"bilinmeyen pencere: {pencere}")
    tut = np.asarray(p.t, dtype=np.int64) + _bar_ms(p.t)
    aktif = np.zeros(len(tut), dtype=bool)
    if len(_FOMC):
        son = FOMC_PENCERE[pencere] * SAAT_MS
        i = np.searchsorted(_FOMC, tut - son, side="right")      # sonu tut'tan sonra olan ilk karar günü
        ok = i < len(_FOMC)
        f = _FOMC[np.minimum(i, len(_FOMC) - 1)]
        aktif = ok & (f - (24 - NY_KAPANIS_SAAT) * SAAT_MS <= tut)
    return _sepet(p, aktif)


# ------------------------------------------------------------------ ay sonu hedge dengelemesi
def _gun_takvimi(gun_ms: np.ndarray):
    g = (np.asarray(gun_ms, dtype=np.int64) // GUN_MS).astype("datetime64[D]")
    ay = g.astype("datetime64[M]")
    ay_basi = ay.astype("datetime64[D]")
    ay_sonu = (ay + np.timedelta64(1, "M")).astype("datetime64[D]") - np.timedelta64(1, "D")
    return g, ay_basi, ay_sonu


def _hafta_gunu(d: np.ndarray) -> np.ndarray:
    """Pazartesi 0 … Pazar 6 (1970-01-01 Perşembe)."""
    return (d.astype(np.int64) + 3) % 7


def _son_is_gunu(ay_sonu: np.ndarray, kacinci: int = 1) -> np.ndarray:
    """Ayın sondan `kacinci` iş günü (hafta içi; tatiller yok sayılır)."""
    d = ay_sonu.copy()
    hg = _hafta_gunu(d)
    d = d - np.where(hg == 5, 1, np.where(hg == 6, 2, 0)).astype("timedelta64[D]")
    for _ in range(kacinci - 1):
        d = d - np.timedelta64(1, "D")
        hg = _hafta_gunu(d)
        d = d - np.where(hg == 5, 1, np.where(hg == 6, 2, 0)).astype("timedelta64[D]")
    return d


def uk_yaz_saati(gun: np.ndarray) -> np.ndarray:
    """İngiltere yaz saati: Mart'ın son Pazarı ≤ gün < Ekim'in son Pazarı. `gun`: datetime64[D]."""
    g = np.asarray(gun, dtype="datetime64[D]")
    yil = g.astype("datetime64[Y]")

    def son_pazar(ay_ofset: int) -> np.ndarray:
        son = (yil + np.timedelta64(ay_ofset + 1, "M")).astype("datetime64[D]") - np.timedelta64(1, "D")
        return son - ((_hafta_gunu(son) - 6) % 7).astype("timedelta64[D]")

    return (g >= son_pazar(2)) & (g < son_pazar(9))


def fixing_ms(gun: np.ndarray) -> np.ndarray:
    """Londra 16:00 WM/R fixing anı (UTC ms): yaz saatinde 15:00 UTC, kışın 16:00 UTC."""
    g = np.asarray(gun, dtype="datetime64[D]")
    saat = np.where(uk_yaz_saati(g), 15, 16)
    return g.astype(np.int64) * GUN_MS + saat * SAAT_MS


def _ay_ici_getiri(para: str, an_ms: int, ay_basi_ms: int) -> float:
    """`an_ms`'de bilinen ay içi getiri: an'dan önce kapanmış son günlük kapanış / önceki ayın son kapanışı − 1."""
    if para not in _ENDEKS:
        return float("nan")
    t, c = _ENDEKS[para]
    kapanmis = t + GUN_MS
    j = np.searchsorted(kapanmis, an_ms, side="right") - 1
    b = np.searchsorted(kapanmis, ay_basi_ms, side="right") - 1
    if j < 0 or b < 0 or j <= b:
        return float("nan")
    return float(c[j] / c[b] - 1.0)


def ay_sonu_hedge(p: Panel, gun: int = 1, olcut: str = "sepet") -> np.ndarray:
    """Ayın sondan `gun`. iş gününün 00:00 UTC'sinden son iş gününün Londra fixing'ine kadar. Yön, girişte bilinen ay
    içi hisse getirisi farkından: ABD endeksi yabancıdan iyiyse yabancı paralar uzun (USD kısa), kötüyse kısa.
    `sepet`: fark = ABD − (EUR, GBP, JPY endekslerinin ortalaması), bütün paralar aynı yönde.
    `kendi`: yalnız EUR, GBP, JPY; her biri kendi endeksiyle (ABD − ülke) yön alır."""
    if olcut not in ("sepet", "kendi"):
        raise ValueError(f"bilinmeyen ölçüt: {olcut}")
    if p.paralar is None:
        raise ValueError("döviz akış: panelde paralar yok (grup tanımında para: true)")
    tut = np.asarray(p.t, dtype=np.int64) + _bar_ms(p.t)
    g, ay_basi, ay_sonu = _gun_takvimi(tut)
    giris = _son_is_gunu(ay_sonu, gun).astype(np.int64) * GUN_MS
    cikis = fixing_ms(_son_is_gunu(ay_sonu, 1))
    aktif = (tut >= giris) & (tut < cikis)
    ab = ay_basi.astype(np.int64) * GUN_MS
    n, k = p.close.shape
    out = np.zeros((n, k))
    if not aktif.any():
        return out
    onbellek: dict[int, dict[str, float]] = {}
    for e in np.unique(giris[aktif]):
        e = int(e)
        a0 = int(ab[aktif & (giris == e)][0])
        onbellek[e] = {x: _ay_ici_getiri(x, e, a0) for x in ("USD",) + HEDGE_PARA}
    isaret = np.zeros(n)
    if olcut == "sepet":
        for e, r in onbellek.items():
            yab = [r[x] for x in HEDGE_PARA if np.isfinite(r[x])]
            if np.isfinite(r["USD"]) and yab:
                isaret[aktif & (giris == e)] = np.sign(r["USD"] - np.mean(yab))
        return _sepet(p, aktif & (isaret != 0), isaret)
    yon = np.asarray(p.para_yon, dtype=float)
    for j, x in enumerate(p.paralar):
        if x not in HEDGE_PARA:
            continue
        for e, r in onbellek.items():
            if np.isfinite(r["USD"]) and np.isfinite(r[x]):
                m = aktif & (giris == e)
                out[m, j] = np.sign(r["USD"] - r[x]) * yon[j] / len(HEDGE_PARA)
    return np.where(p.evrende, out, 0.0)


# ------------------------------------------------------------------ seans saati
def seans_para(p: Panel, tur: str = "abd") -> np.ndarray:
    """ABD saatlerinde (13–21 UTC) yerel seansı tanımlı paralar uzun (USD kendi saatlerinde değer kaybeder). `tam`:
    ayrıca her para kendi saatlerinde kısa (Avrupa paraları 07–13, Asya-Pasifik 00–07 UTC). CAD'nin yerel saatleri
    ABD'ninkiyle aynı: dışarıda."""
    if tur not in ("abd", "tam"):
        raise ValueError(f"bilinmeyen tür: {tur}")
    if p.paralar is None or p.para_yon is None:
        raise ValueError("döviz akış: panelde paralar yok (grup tanımında para: true)")
    tut = np.asarray(p.t, dtype=np.int64) + _bar_ms(p.t)
    saat = (tut % GUN_MS) // SAAT_MS
    n, k = p.close.shape
    sec = np.array([x in YEREL_SEANS for x in p.paralar])
    ev = p.evrende & sec[None, :]
    m = np.maximum(ev.sum(axis=1), 1)
    para_w = np.zeros((n, k))
    abd = (saat >= ABD_SEANS[0]) & (saat < ABD_SEANS[1])
    for j, x in enumerate(p.paralar):
        if x not in YEREL_SEANS:
            continue
        para_w[abd, j] = 1.0
        if tur == "tam":
            b, s = YEREL_SEANS[x]
            para_w[(saat >= b) & (saat < s), j] = -1.0
    return np.where(ev, para_w * np.asarray(p.para_yon, dtype=float)[None, :] / m[:, None], 0.0)
