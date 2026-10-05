"""Altın haber ivmesi (dalga 14; docs/turnuva/Dalga-14-Altin-Haber.md). XAUUSD 1 dakikalık barlar; saf ve nedensel.

Fikir: ABD makro verisinin (FOMC, NFP, CPI, PPI, haftalık işsizlik başvuruları) yayınlandığı dakikada altın sert
hareket eder. Yayından sonraki ilk k dakikadaki hareketin yönü sonraki h dakikada sürüyor mu (`yon = +1`, ivme), yoksa
geri mi dönüyor (`yon = −1`, dönüş)? Fiyatın haberi dakikalar içinde fiyatladığı bilinir (Andersen, Bollerslev,
Diebold, Vega 2003, AER 93(1)); ilk tepkinin ardından kısa süreli sürüklenme ya da aşırı tepki düzeltmesi, ölçülmesi
gereken açık sorudur.

Zaman kuralı: out[i] bar i'nin KAPANIŞINDA verilir, bar i+1 boyunca tutulur (kural 4: dolum sonraki barın açılışında).
Olay anı E = yayın dakikasının açılışı. Referans fiyat: E'den önceki son kapanış (bar E − 1 bar). Karar bar
E + (k − 1) bar'ın kapanışında (yayından k bar sonra): s = yon × işaret(kapanış − referans). Pozisyon h bar tutulur:
out[j … j + h − 1] = s, j karar barı (bar E + k açılışından E + k + h açılışına). Karar yalnız j'ye kadarki barlara
bakar; pencere verinin sonunda kırpılır (canlıda gelecek bar yokken de aynı karar).

Atlananlar: referans ya da karar barı eksikse (boşluk), hareket 0 ise. Aynı dakikadaki birden çok yayın (ör. CPI +
işsizlik) tek olaydır; pencereler örtüşürse önceki olay önceliklidir.

Olay anları çekirdeğe dışarıdan verilir (`olay_ayarla`; turnuva `config/haber_takvimi.yaml`'dan yükler). Takvim
önceden ilan edildiği için geleceği görmez.
"""
from __future__ import annotations

import numpy as np

from tradebot.cekirdek.temel import Barlar

BUYUK = ("FOMC", "NFP", "CPI")
SECIMLER = {"buyuk": BUYUK, "hepsi": BUYUK + ("PPI", "ISSIZLIK")}
_OLAY: list[tuple[str, int]] = []


def olay_ayarla(olaylar) -> None:
    """(tür, UTC ms) çiftleri. Turnuva ve canlı düğüm koşudan önce bir kez çağırır."""
    global _OLAY
    _OLAY = sorted((str(tur), int(t)) for tur, t in olaylar)


def anlar(secim: str = "buyuk") -> np.ndarray:
    turler = SECIMLER[secim]
    return np.unique(np.asarray([t for tur, t in _OLAY if tur in turler], dtype=np.int64))


def haber_ivme(b: Barlar, k: int = 1, h: int = 15, yon: int = 1, secim: str = "buyuk") -> np.ndarray:
    """Bar başına pozisyon ∈ {−1, 0, 1}: yayından k bar sonra ilk hareketin yönünde (yon = 1) ya da tersine (−1) h bar."""
    t = np.asarray(b.t, dtype=np.int64)
    out = np.zeros(len(t))
    if len(t) < 2 or k < 1 or h < 1:
        return out
    bar = int(np.min(np.diff(t)))
    c = np.asarray(b.close, dtype=float)
    son = -1
    for e in anlar(secim):
        i = int(np.searchsorted(t, e))
        j = i + k - 1
        if i < 1 or j >= len(t) or j <= son:
            continue
        if t[i] != e or t[i - 1] != e - bar or t[j] != e + (k - 1) * bar:
            continue
        s = float(np.sign(c[j] - c[i - 1])) * yon
        if s == 0.0:
            continue
        out[j:j + h] = s
        son = j + h - 1
    return out
