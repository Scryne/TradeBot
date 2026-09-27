"""Altın M15 aileleri: piyasada satılan çok stratejili EA'ların ("XAUUSD Adaptive Edge M15" vb.) açıkça tanımlanmış,
ölçülebilir karşılığı. EA 5 alış + 5 satış stratejisini adlandırmadan anlatıyor; burada her aile hem alış hem satış
yönlüdür ve gün içi altın literatüründeki bilinen bir fikre dayanır (docs/turnuva/Altin-M15.md).

Giriş aileleri (Barlar → bar başına giriş sinyali ∈ {-1, 0, 1}; yeni sinyal = sıfırdan/ters yönden geçiş):
- seans_kirilim: Asya seansı aralığının (UTC 00–07) Londra/NY saatlerinde kırılımı
- kanal_kirilim: son n barın tepe/dip kırılımı (Donchian)
- trend_geri_cekilme: EMA trendi yönünde RSI geri çekilmesi
- bant_donus: Bollinger z-skoru aşırılığından dönüş
- sikisma_kirilim: bant genişliği düşükken (sıkışma) bant kırılımı

İşlem yönetimi (`yonet`, EA'nın anlattığı risk katmanları, varsayılanları EA'nınkiler):
stop-loss = sl_atr × ATR(14), hedef = rr × stop (R/R 2), en uzun tutma `azami_bar` (192), günlük ±`gunluk_r` R sınırı
(EA: işlem başı %1 riskle günlük ±%3), günde `ardisik` ardışık kayıpta dur (3), haber filtresi (±`haber_dk` dakika
yeni giriş yok). Stop ve hedef bar KAPANIŞINDA denetlenir, çıkış sonraki barın açılışında (kural 4; boşlukta kayıp
1R'yi aşabilir, aleyhte).

Haber anları çekirdeğe dışarıdan verilir (`haber_ayarla`; turnuva `config/haber_takvimi.yaml`'dan yükler). Çekirdek
G/Ç yapmaz. Takvim önceden ilan edildiği için geleceği görmez.
"""
from __future__ import annotations

import numpy as np

from tradebot.cekirdek.aileler import rsi
from tradebot.cekirdek.gosterge import kayan_max, kayan_min, kayan_std, sma
from tradebot.cekirdek.temel import Barlar

GUN_MS = 86_400_000
SAAT_MS = 3_600_000
_HABER = np.zeros(0, dtype=np.int64)


def haber_ayarla(anlar_ms) -> None:
    """Yüksek etkili haber anları (UTC ms). Turnuva koşudan önce bir kez çağırır."""
    global _HABER
    _HABER = np.sort(np.asarray(list(anlar_ms), dtype=np.int64))


def _haber_yakin(bitis_ms: np.ndarray, dk: int) -> np.ndarray:
    """Bar kapanış anı bir haberin ±dk içinde mi (karar anı; giriş sonraki barın açılışında)."""
    if dk <= 0 or len(_HABER) == 0:
        return np.zeros(len(bitis_ms), dtype=bool)
    w = dk * 60_000
    sag = np.searchsorted(_HABER, bitis_ms - w, side="left")
    return (sag < len(_HABER)) & (_HABER[np.minimum(sag, len(_HABER) - 1)] <= bitis_ms + w)


def ema(x: np.ndarray, n: int) -> np.ndarray:
    out = np.full(len(x), np.nan)
    if len(x) < n:
        return out
    a = 2.0 / (n + 1)
    out[n - 1] = np.mean(x[:n])
    for i in range(n, len(x)):
        out[i] = a * x[i] + (1 - a) * out[i - 1]
    return out


def atr(b: Barlar, n: int = 14) -> np.ndarray:
    """Wilder ATR (nedensel)."""
    k = len(b)
    out = np.full(k, np.nan)
    if k <= n:
        return out
    onceki = np.concatenate([[b.close[0]], b.close[:-1]])
    tr = np.maximum(b.high - b.low, np.maximum(np.abs(b.high - onceki), np.abs(b.low - onceki)))
    out[n] = np.mean(tr[1:n + 1])
    for i in range(n + 1, k):
        out[i] = (out[i - 1] * (n - 1) + tr[i]) / n
    return out


# ------------------------------------------------------------------ giriş aileleri
def seans_kirilim_giris(b: Barlar, aralik_bit_saat: int = 7, son_saat: int = 16) -> np.ndarray:
    """UTC 00:00–aralik_bit_saat aralığının tepesi/dibi; aralık bittikten son_saat'e kadar kapanış tepeyi aşarsa +1,
    dibi kırarsa −1 (günde yön başına bir sinyal)."""
    n = len(b)
    out = np.zeros(n)
    bar_ms = int(np.min(np.diff(b.t))) if n > 1 else 0
    ust, alt, son_gun, isaret = -np.inf, np.inf, -1, set()
    for i in range(n):
        t = int(b.t[i])
        gun = t // GUN_MS
        if gun != son_gun:
            son_gun, ust, alt, isaret = gun, -np.inf, np.inf, set()
        saat_bitis = (t + bar_ms - gun * GUN_MS) / SAAT_MS
        if saat_bitis <= aralik_bit_saat:
            ust, alt = max(ust, b.high[i]), min(alt, b.low[i])
        elif saat_bitis <= son_saat and np.isfinite(ust):
            yon = 1 if b.close[i] > ust else -1 if b.close[i] < alt else 0
            if yon and yon not in isaret:
                out[i] = float(yon)
                isaret.add(yon)
    return out


def kanal_kirilim_giris(b: Barlar, n: int = 48) -> np.ndarray:
    """Kapanış önceki n barın tepesini aşarsa +1, dibini kırarsa −1."""
    k = len(b)
    out = np.zeros(k)
    if k <= n:
        return out
    ust = np.concatenate([[np.nan], kayan_max(b.high, n)[:-1]])
    alt = np.concatenate([[np.nan], kayan_min(b.low, n)[:-1]])
    out[b.close > ust] = 1.0
    out[b.close < alt] = -1.0
    return out


def trend_geri_cekilme_giris(b: Barlar, hizli: int = 50, yavas: int = 200, rsi_n: int = 14, esik: float = 30.0) -> np.ndarray:
    """EMA(hızlı) > EMA(yavaş) ve RSI < eşik → +1; EMA(hızlı) < EMA(yavaş) ve RSI > 100 − eşik → −1."""
    f, s, r = ema(b.close, hizli), ema(b.close, yavas), rsi(b.close, rsi_n)
    out = np.zeros(len(b))
    ok = np.isfinite(f) & np.isfinite(s) & np.isfinite(r)
    out[ok & (f > s) & (r < esik)] = 1.0
    out[ok & (f < s) & (r > 100 - esik)] = -1.0
    return out


def bant_donus_giris(b: Barlar, n: int = 20, z: float = 2.0) -> np.ndarray:
    """z = (kapanış − SMA) / std: z < −z → +1 (dönüş alımı), z > z → −1."""
    m, s = sma(b.close, n), kayan_std(b.close, n)
    zz = np.where(s > 0, (b.close - m) / np.where(s > 0, s, 1), np.nan)
    out = np.zeros(len(b))
    out[np.isfinite(zz) & (zz < -z)] = 1.0
    out[np.isfinite(zz) & (zz > z)] = -1.0
    return out


def sikisma_kirilim_giris(b: Barlar, n: int = 20, yuzdelik: float = 0.2, geriye: int = 480, taze: int = 8) -> np.ndarray:
    """Bant genişliği (2·std/SMA) son `geriye` barın alt `yuzdelik` diliminde (sıkışma) olduktan sonraki `taze` bar
    içinde kapanış üst bandı aşarsa +1, alt bandı kırarsa −1."""
    k = len(b)
    m, s = sma(b.close, n), kayan_std(b.close, n)
    gen = np.where(m > 0, 2 * s / np.where(m > 0, m, 1), np.nan)
    sik = np.zeros(k, dtype=bool)
    for i in range(geriye, k):
        p = gen[i - geriye:i]
        p = p[np.isfinite(p)]
        if len(p) > 10 and np.isfinite(gen[i]):
            sik[i] = gen[i] <= np.quantile(p, yuzdelik)
    yakin = np.zeros(k, dtype=bool)
    son = -10**9
    for i in range(k):
        if sik[i]:
            son = i
        yakin[i] = i - son <= taze
    out = np.zeros(k)
    ok = yakin & np.isfinite(m) & np.isfinite(s)
    out[ok & (b.close > m + 2 * s)] = 1.0
    out[ok & (b.close < m - 2 * s)] = -1.0
    return out


# ------------------------------------------------------------------ işlem yönetimi
def yonet(b: Barlar, giris: np.ndarray, sl_atr: float = 1.5, rr: float = 2.0, azami_bar: int = 192,
          gunluk_r: float = 3.0, ardisik: int = 3, haber_dk: int = 60, atr_n: int = 14) -> np.ndarray:
    """Giriş sinyalini yönetilen işlemlere çevirir → bar başına pozisyon ∈ {-1, 0, 1} (karar bar kapanışında).

    Yeni giriş: sinyal sıfırdan ya da ters yönden geçerken, pozisyon yokken, gün kilidi yokken, haber penceresi
    dışında. Çıkış: kapanış stop'u (−1R) ya da hedefi (+rr R) geçerse, `azami_bar` dolunca. Gün (UTC) boyunca gerçekleşen
    R toplamı ±gunluk_r'ye ulaşırsa ya da `ardisik` ardışık kayıp olursa o gün yeni işlem yok.
    """
    k = len(b)
    out = np.zeros(k)
    if k < 2:
        return out
    a = atr(b, atr_n)
    bar_ms = int(np.min(np.diff(b.t)))
    haber = _haber_yakin(np.asarray(b.t, dtype=np.int64) + bar_ms, haber_dk)
    poz, fiyat, risk, sure = 0.0, 0.0, 0.0, 0
    son_gun, r_gun, seri, kilit = -1, 0.0, 0, False
    onceki = 0.0
    for i in range(k):
        gun = int(b.t[i]) // GUN_MS
        if gun != son_gun:
            son_gun, r_gun, seri, kilit = gun, 0.0, 0, False
        c = b.close[i]
        if poz != 0.0:
            sure += 1
            r = (c - fiyat) * poz / risk
            if r <= -1.0 or r >= rr or sure >= azami_bar:
                poz = 0.0
                r_gun += r
                seri = seri + 1 if r < 0 else 0
                if r_gun <= -gunluk_r or r_gun >= gunluk_r or seri >= ardisik:
                    kilit = True
        g = giris[i]
        yeni = g != 0.0 and g != onceki
        onceki = g
        if poz == 0.0 and yeni and not kilit and not haber[i] and np.isfinite(a[i]) and a[i] > 0:
            poz, fiyat, risk, sure = float(np.sign(g)), c, sl_atr * a[i], 0
        out[i] = poz
    return out


def _yonetilen(giris_fonk):
    def f(b: Barlar, sl_atr: float = 1.5, rr: float = 2.0, azami_bar: int = 192, gunluk_r: float = 3.0,
          ardisik: int = 3, haber_dk: int = 60, **p) -> np.ndarray:
        return yonet(b, giris_fonk(b, **p), sl_atr, rr, azami_bar, gunluk_r, ardisik, haber_dk)
    f.__name__ = giris_fonk.__name__.removesuffix("_giris")
    f.__doc__ = f"{giris_fonk.__name__} + yonet (EA risk katmanları)."
    return f


seans_kirilim = _yonetilen(seans_kirilim_giris)
kanal_kirilim = _yonetilen(kanal_kirilim_giris)
trend_geri_cekilme = _yonetilen(trend_geri_cekilme_giris)
bant_donus = _yonetilen(bant_donus_giris)
sikisma_kirilim = _yonetilen(sikisma_kirilim_giris)


def ea_birlesik(b: Barlar, sl_atr: float = 1.5, rr: float = 2.0, azami_bar: int = 192, gunluk_r: float = 3.0,
                ardisik: int = 3, haber_dk: int = 60) -> np.ndarray:
    """EA gibi: beş aile birlikte (her biri varsayılan parametreyle, kendi yönetimiyle), en fazla 3 açık işlem.
    Pozisyon = kırpılmış toplam / 3 ∈ [-1, 1]."""
    ortak = dict(sl_atr=sl_atr, rr=rr, azami_bar=azami_bar, gunluk_r=gunluk_r, ardisik=ardisik, haber_dk=haber_dk)
    toplam = sum(f(b, **ortak) for f in (seans_kirilim, kanal_kirilim, trend_geri_cekilme, bant_donus, sikisma_kirilim))
    return np.clip(toplam, -3.0, 3.0) / 3.0
