"""Piyasa başına maliyet modeli (değişmez kural 4: maliyet hep aleyhte; belirsizlikte kötü yöne yuvarla).

Taraf başı maliyet (bps) = ücret × (1 + ücret vergisi) + yarım spread + kayma. Spread verisi varsa (Dukascopy) bardaki
spread kullanılır, yoksa varsayılan yarım spread. CFD/marjin pozisyonları elde tutulduğu süre için yıllık finansman
öder (uzun ya da kısa fark etmeksizin aleyhte). Spot pozisyonlar finansman ödemez.

Varsayımlar (2026-09; paper aşamasında gerçek dolumlarla ölçülüp güncellenir, Faz 11):
- Binance spot: VIP0 taker %0,10 (BNB indirimi yok), yarım spread 1 bps, kayma 2 bps (büyük coinler; küçükler için
  likiditeye bağlı ek Faz 5'te).
- Dukascopy (FX/CFD): komisyon 0,5 bps (doğrulanmamış, kötü yönde tahmin), spread veriden, kayma 0,5 bps; finansman
  yıllık FX %2, metal %4, emtia %4, endeks %6 (≈ gösterge faiz + aracı kurum payı).
- ABD ETF: komisyon 1 bps, yarım spread 1 bps, kayma 1 bps.
- BIST hisse: komisyon 4 bps + BSMV (%5), yarım spread 5 bps, kayma 5 bps.
"""
from __future__ import annotations

from dataclasses import dataclass

YIL_MS = 365.25 * 86_400_000


@dataclass(frozen=True)
class MaliyetModeli:
    ad: str
    ucret_bps: float
    yari_spread_bps: float
    kayma_bps: float
    finansman_yillik: float = 0.0
    ucret_vergisi: float = 0.0
    spread_veriden: bool = False

    def taraf_bps(self, yari_spread_bps: float | None = None) -> float:
        ys = self.yari_spread_bps if yari_spread_bps is None else yari_spread_bps
        return self.ucret_bps * (1 + self.ucret_vergisi) + ys + self.kayma_bps


MODELLER = {
    "BINANCE": MaliyetModeli("binance_spot", ucret_bps=10.0, yari_spread_bps=1.0, kayma_bps=2.0),
    "DUKASCOPY:fx": MaliyetModeli("cfd_fx", 0.5, 0.5, 0.5, finansman_yillik=0.02, spread_veriden=True),
    "DUKASCOPY:metal": MaliyetModeli("cfd_metal", 0.5, 1.0, 0.5, finansman_yillik=0.04, spread_veriden=True),
    "DUKASCOPY:emtia": MaliyetModeli("cfd_emtia", 0.5, 1.5, 0.5, finansman_yillik=0.04, spread_veriden=True),
    "DUKASCOPY:endeks": MaliyetModeli("cfd_endeks", 0.5, 0.5, 0.5, finansman_yillik=0.06, spread_veriden=True),
    "ARCA": MaliyetModeli("abd_etf", 1.0, 1.0, 1.0),
    "BIST:hisse": MaliyetModeli("bist_hisse", 4.0, 5.0, 5.0, ucret_vergisi=0.05),
    "BIST:endeks": MaliyetModeli("bist_endeks_vadeli_vekil", 2.0, 2.0, 2.0),  # endeks doğrudan alınamaz; VİOP vekili
}


def model(piyasa: str, sinif: str) -> MaliyetModeli:
    for anahtar in (f"{piyasa}:{sinif}", piyasa):
        if anahtar in MODELLER:
            return MODELLER[anahtar]
    raise KeyError(f"maliyet modeli yok: {piyasa}/{sinif}")
