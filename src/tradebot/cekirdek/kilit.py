"""Kilit açılımı kolu (Dalga 6) — saf karar çekirdeği (kural 3): backtest (`arastirma/kilit.py`) ve paper düğümü
(`canli/kilit.py`) günlük kararı bu fonksiyonla verir. I/O yok; yalnız karar anında bilinenleri görür.

Gün kararı (00:00 UTC açılışı, gün `g`):
1. Kapat: çıkış günü gelen (`cikis_ms <= g`) ya da artık işlem görmeyen pozisyonlar; `hepsini_kapat` (kol durduruldu,
   acil durdurma) varsa hepsi. Kapatma önce yapılır, açılışa yer açar.
2. Aç: açılım günü `T` için `T + giris == g` olan olaylar (sembol sırasıyla), token perp'i işlem görüyorsa ve aynı olay
   zaten açık değilse. `yeni_risk` yanlışsa (fren, durdurma) açılmaz. Çıkış günü girişte sabitlenir (`T + cikis`):
   takvim sonradan kayarsa pozisyon ilk planla kapanır.
3. Tavan: olay başına bacak nominali `notional`. Açık olayların brüt toplamı (2 × nominal) `azami_brut`'u, BTC uzun
   bacağının toplamı `azami_btc`'yi aşamaz; aşacaksa yeni olay kırpılır, yer yoksa reddedilir (kural 6).

Nominal özkaynağa oranla ölçülür. Kaldıraç tavanı `KALDIRAC_TAVANI` (3x) kodda sabittir, bunun üstü doğrulanmaz.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from tradebot.cekirdek.boyut import KALDIRAC_TAVANI, kaldirac_dogrula

GUN_MS = 86_400_000


@dataclass(frozen=True)
class KilitKural:
    giris: int = -7                    # açılım gününe göre giriş günü
    cikis: int = 0                     # açılım gününe göre çıkış günü
    notional: float = 0.10             # olay başına bacak nominali / özkaynak
    azami_brut: float = KALDIRAC_TAVANI
    azami_btc: float = float("inf")    # BTC uzun bacağı toplamı / özkaynak (risk motoru enstrüman tavanı)

    def __post_init__(self) -> None:
        kaldirac_dogrula(self.azami_brut)
        if self.giris > 0 or self.giris >= self.cikis:
            raise ValueError("giriş açılımdan önce ya da açılım günü olmalı ve çıkıştan önce gelmeli")
        if not 0 < self.notional <= self.azami_brut / 2:
            raise ValueError("notional (0, azami_brut/2] aralığında olmalı")


@dataclass(frozen=True)
class Olay:
    sembol: str        # token tabanı (TIA)
    gun_ms: int        # açılım günü (UTC 00:00)
    oran: float        # açılan / azami arz


@dataclass(frozen=True)
class Pozisyon:
    sembol: str
    olay_ms: int       # açılım günü
    giris_ms: int
    cikis_ms: int      # planlanan çıkış günü
    notional: float    # bacak nominali / özkaynak (giriş anında)

    @property
    def anahtar(self) -> tuple[str, int]:
        return self.sembol, self.olay_ms


@dataclass(frozen=True)
class GunKarari:
    gun_ms: int
    kapat: tuple[tuple[Pozisyon, str], ...]      # (pozisyon, neden: cikis | islem_gormuyor | durdur)
    ac: tuple[Pozisyon, ...]
    red: tuple[tuple[Olay, str], ...]            # (olay, neden: islem_gormuyor | tavan | yeni_risk_yok)
    acik: tuple[Pozisyon, ...]                   # karardan sonra açık kalanlar + yeniler


def gun_karari(gun_ms: int, olaylar: Iterable[Olay], acik: Iterable[Pozisyon], islem_goren: set[str], k: KilitKural,
               yeni_risk: bool = True, hepsini_kapat: bool = False) -> GunKarari:
    if gun_ms % GUN_MS:
        raise ValueError("gun_ms UTC gün başı olmalı")
    kalan, kapat = [], []
    for p in sorted(acik, key=lambda p: (p.giris_ms, p.sembol)):
        if hepsini_kapat:
            kapat.append((p, "durdur"))
        elif p.cikis_ms <= gun_ms:
            kapat.append((p, "cikis"))
        elif p.sembol not in islem_goren:
            kapat.append((p, "islem_gormuyor"))
        else:
            kalan.append(p)
    acik_anahtar = {p.anahtar for p in kalan} | {p.anahtar for p, _ in kapat}
    ac, red = [], []
    bugun = sorted((o for o in olaylar if o.gun_ms + k.giris * GUN_MS == gun_ms), key=lambda o: o.sembol)
    for o in bugun:
        if (o.sembol, o.gun_ms) in acik_anahtar:
            continue
        if hepsini_kapat or not yeni_risk:
            red.append((o, "yeni_risk_yok"))
            continue
        if o.sembol not in islem_goren:
            red.append((o, "islem_gormuyor"))
            continue
        btc = sum(p.notional for p in kalan + ac)
        n = min(k.notional, (k.azami_brut - 2 * btc) / 2, k.azami_btc - btc)
        if n <= 1e-12:
            red.append((o, "tavan"))
            continue
        ac.append(Pozisyon(o.sembol, o.gun_ms, gun_ms, o.gun_ms + k.cikis * GUN_MS, n))
        acik_anahtar.add((o.sembol, o.gun_ms))
    return GunKarari(gun_ms, tuple(kapat), tuple(ac), tuple(red), tuple(kalan + ac))
