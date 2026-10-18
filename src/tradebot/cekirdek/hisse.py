"""ABD hisse (Nasdaq-100) kesitsel stratejileri, dalga 19 (docs/turnuva/Dalga-19-Nasdaq.md). Saf ve nedensel (kural 3):
çıktı[t] yalnız close[: t + 1] ve evrende[: t + 1]'e bağlıdır. Hepsi yalnız uzun, ağırlıkların toplamı ≤ 1 (kalan nakit).
Boyut (oynaklık hedefi, tavanlar) çekirdeğin dışında: `boyut.panel_oynaklik_hedefi`.

`evrende[t, j]`: j, t gününde Nasdaq-100 üyesi ve fiyat serisi o üyelik dönemini kapsıyor (`veri.nasdaq100`). Evrenden
çıkan hisse o gün ağırlık 0 alır (ertesi açılışta satılır).

Piyasa filtresi (`filtre` > 0): evrendeki hisselerin eşit ağırlıklı endeksi (`esit_endeks`) kendi `filtre` günlük
basit ortalamasının altındaysa nakit. Endeks yalnız evrendeki hisselerin günlük getirilerinden kurulur (dış seri yok).
"""
from __future__ import annotations

import numpy as np

from tradebot.cekirdek.aileler import Panel, hafta_basi
from tradebot.cekirdek.gosterge import sma


def ay_basi(t_ms: np.ndarray) -> np.ndarray:
    """Bar, ayın İLK barı mı (karar o barın kapanışında; ertesi açılışta dolum)."""
    ay = np.asarray(t_ms, dtype=np.int64).astype("datetime64[ms]").astype("datetime64[M]")
    return np.r_[True, ay[1:] != ay[:-1]]


def gunluk_getiri(p: Panel) -> np.ndarray:
    """[n, k] basit getiri; yalnız iki gün üst üste evrende ve tanımlıysa (yoksa NaN)."""
    c = p.close
    r = np.full(c.shape, np.nan)
    with np.errstate(invalid="ignore", divide="ignore"):
        r[1:] = c[1:] / c[:-1] - 1.0
    ok = np.zeros(c.shape, dtype=bool)
    ok[1:] = p.evrende[1:] & p.evrende[:-1]
    return np.where(ok & np.isfinite(r), r, np.nan)


def esit_endeks(p: Panel) -> np.ndarray:
    """Evrenin eşit ağırlıklı endeks seviyesi (1'den başlar; evren boşken getiri 0)."""
    r = gunluk_getiri(p)
    say = np.isfinite(r).sum(axis=1)
    ort = np.where(say > 0, np.nansum(r, axis=1) / np.maximum(say, 1), 0.0)
    return np.cumprod(1.0 + ort)


def piyasa_acik(p: Panel, filtre: int) -> np.ndarray:
    """[n] bool: piyasa filtresi riske izin veriyor mu (filtre ≤ 0: hep izin). Isınmada izin yok (bilinmeyen = nakit)."""
    n = len(p)
    if filtre <= 0:
        return np.ones(n, dtype=bool)
    e = esit_endeks(p)
    m = sma(e, filtre)
    return np.isfinite(m) & (e > m)


def _yenile(t: np.ndarray, aylik: bool) -> np.ndarray:
    return ay_basi(t) if aylik else hafta_basi(t)


def _sec(puan: np.ndarray, gecerli: np.ndarray, n: int, en_yuksek: bool) -> np.ndarray:
    aday = np.flatnonzero(gecerli & np.isfinite(puan))
    if len(aday) == 0:
        return aday
    sira = np.argsort(-puan[aday] if en_yuksek else puan[aday], kind="stable")
    return aday[sira][:n]


def hisse_momentum(p: Panel, geriye: int = 252, atla: int = 21, ust_n: int = 10, filtre: int = 0,
                   aylik: bool = True) -> np.ndarray:
    """Kesitsel momentum (Jegadeesh-Titman 1993; 12-1 ay): evrende [t − geriye, t − atla] getirisi en yüksek `ust_n`
    hisse, her biri 1/ust_n. Getirisi negatif olan seçilmez (mutlak momentum: kalan nakitte). Sıralama ayın ilk
    barında (`aylik`) ya da haftanın ilk barında yenilenir; arada evrenden çıkan hisse 0'a iner. Piyasa filtresi
    kapanınca hemen nakde geçilir, açılınca bir sonraki yenilemede girilir."""
    n, k = p.close.shape
    out = np.zeros((n, k))
    yenile = _yenile(p.t, aylik)
    acik = piyasa_acik(p, filtre)
    son = np.zeros(k)
    for i in range(n):
        if yenile[i]:
            son = np.zeros(k)
            if i >= geriye and acik[i]:
                with np.errstate(invalid="ignore", divide="ignore"):
                    g = p.close[i - atla] / p.close[i - geriye] - 1.0
                # Üyelik öncesi fiyat da t'de bilinir (hisse endekse girmeden işlem görüyordu): pencere başında fiyat
                # olması yeter; yeniden kullanılan sembol riski üyelik dönemi kapsamıyla zaten ayıklandı
                gecerli = p.evrende[i] & np.isfinite(p.close[i - geriye])
                sec = _sec(g, gecerli, ust_n, True)
                sec = sec[g[sec] > 0]
                son[sec] = 1.0 / ust_n
        elif not acik[i]:
            son = np.zeros(k)
        out[i] = np.where(p.evrende[i], son, 0.0)
    return out


def kisa_donus(p: Panel, geriye: int = 5, alt_n: int = 10, trend: int = 200, filtre: int = 0) -> np.ndarray:
    """Kısa vadeli dönüş (Lehmann 1990, Jegadeesh 1990; büyük hisselerde likidite sağlama primi, Nagel 2012): son
    `geriye` günün en çok düşen `alt_n` hissesi, her biri 1/alt_n, bir hafta tutulur (haftanın ilk barında yenilenir).
    `trend` > 0: yalnız kapanışı kendi `trend` günlük ortalamasının üstünde olanlar (düşen bıçak yerine trend içi geri
    çekilme; Connors tarzı)."""
    n, k = p.close.shape
    out = np.zeros((n, k))
    yenile = hafta_basi(p.t)
    acik = piyasa_acik(p, filtre)
    ort = np.column_stack([sma(p.close[:, j], trend) for j in range(k)]) if trend > 0 else None
    son = np.zeros(k)
    for i in range(n):
        if yenile[i]:
            son = np.zeros(k)
            if i >= geriye and acik[i]:
                with np.errstate(invalid="ignore", divide="ignore"):
                    g = p.close[i] / p.close[i - geriye] - 1.0
                gecerli = p.evrende[i] & np.isfinite(p.close[i - geriye])
                if ort is not None:
                    gecerli &= np.isfinite(ort[i]) & (p.close[i] > ort[i])
                sec = _sec(g, gecerli, alt_n, False)
                sec = sec[g[sec] < 0]
                son[sec] = 1.0 / alt_n
        elif not acik[i]:
            son = np.zeros(k)
        out[i] = np.where(p.evrende[i], son, 0.0)
    return out


def dusuk_oynaklik(p: Panel, pencere: int = 60, ust_n: int = 20, filtre: int = 0, aylik: bool = True) -> np.ndarray:
    """Düşük oynaklık (Ang-Hodrick-Xing-Zhang 2006, Blitz-van Vliet 2007): son `pencere` günün günlük getiri std'si en
    düşük `ust_n` hisse, eşit ağırlık; ayın ilk barında yenilenir. Pencerenin en az %90'ı tanımlı olmalı."""
    n, k = p.close.shape
    out = np.zeros((n, k))
    r = gunluk_getiri(p)
    yenile = _yenile(p.t, aylik)
    acik = piyasa_acik(p, filtre)
    son = np.zeros(k)
    for i in range(n):
        if yenile[i]:
            son = np.zeros(k)
            if i >= pencere and acik[i]:
                w = r[i - pencere + 1: i + 1]
                ok = np.isfinite(w)
                tanimli = ok.sum(axis=0)
                ort = np.where(ok, w, 0.0).sum(axis=0) / np.maximum(tanimli, 1)
                var = (np.where(ok, w - ort, 0.0) ** 2).sum(axis=0) / np.maximum(tanimli - 1, 1)
                sd = np.where(tanimli >= 2, np.sqrt(var), np.nan)   # örneklem std (ddof=1), tanımlı değerlerle
                gecerli = p.evrende[i] & (tanimli >= 0.9 * pencere)
                sec = _sec(sd, gecerli, ust_n, False)
                son[sec] = 1.0 / ust_n
        elif not acik[i]:
            son = np.zeros(k)
        out[i] = np.where(p.evrende[i], son, 0.0)
    return out


def esit_agirlik(p: Panel, filtre: int = 200, aylik: bool = True) -> np.ndarray:
    """Evrenin tamamı eşit ağırlıklı (1/üye sayısı), piyasa filtresi açıkken; ayın ilk barında yenilenir. `filtre` = 0
    al-tut kıyasıdır (bilgi). Zaman serisi trendi (Faber 2007) Nasdaq-100 eşit ağırlıklı endeksinde."""
    n, k = p.close.shape
    out = np.zeros((n, k))
    yenile = _yenile(p.t, aylik)
    acik = piyasa_acik(p, filtre)
    son = np.zeros(k)
    for i in range(n):
        if yenile[i] or not acik[i] or (acik[i] and not son.any()):
            son = np.zeros(k)
            m = p.evrende[i] & np.isfinite(p.close[i])
            if acik[i] and m.any():
                son[m] = 1.0 / m.sum()
        out[i] = np.where(p.evrende[i], son, 0.0)
    return out
