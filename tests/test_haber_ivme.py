"""Altın haber ivmesi (dalga 14): zamanlama, yön, atlama kuralları, nedensellik; işsizlik takvimi kuralı."""
from datetime import date

import numpy as np

from tradebot.cekirdek import haber as hb
from tradebot.cekirdek.temel import Barlar
from tradebot.veri import haber_takvimi as ht

DK = 60_000
T0 = 1_757_075_400_000  # 5 Eylül 2025 12:30 UTC (NFP)


def _barlar(close: np.ndarray, t0: int = T0 - 10 * DK) -> Barlar:
    t = t0 + np.arange(len(close), dtype=np.int64) * DK
    return Barlar(t=t, open=close, high=close, low=close, close=close, volume=np.ones(len(close)))


def _seri(yukari: bool = True) -> np.ndarray:
    c = np.full(60, 100.0)
    c[10:] = 101.0 if yukari else 99.0   # olay barı (indeks 10) ve sonrası
    return c


def test_ivme_zamanlama_ve_yon():
    hb.olay_ayarla([("NFP", T0)])
    b = _barlar(_seri(True))
    out = hb.haber_ivme(b, k=1, h=15, yon=1)
    # karar olay barının kapanışında (k=1 → j=10), 15 bar tutulur: out[10..24] = +1
    assert out[:10].tolist() == [0.0] * 10
    assert out[10:25].tolist() == [1.0] * 15
    assert out[25:].sum() == 0.0
    assert (hb.haber_ivme(b, k=1, h=15, yon=-1)[10:25] == -1.0).all()
    assert (hb.haber_ivme(_barlar(_seri(False)), k=5, h=15, yon=1)[14:29] == -1.0).all()


def test_secim_ve_atlama():
    hb.olay_ayarla([("ISSIZLIK", T0)])
    b = _barlar(_seri(True))
    assert hb.haber_ivme(b, secim="buyuk").sum() == 0.0      # işsizlik büyük seçimde yok
    assert hb.haber_ivme(b, secim="hepsi").sum() == 15.0
    hb.olay_ayarla([("NFP", T0)])
    assert hb.haber_ivme(_barlar(np.full(60, 100.0))).sum() == 0.0   # hareket yok → işlem yok
    c = _seri(True)
    t = T0 - 10 * DK + np.arange(60, dtype=np.int64) * DK
    t[9:] += DK                                                      # olaydan önceki bar eksik
    b = Barlar(t=t, open=c, high=c, low=c, close=c, volume=np.ones(60))
    assert hb.haber_ivme(b).sum() == 0.0


def test_ortusme_ve_ayni_dakika():
    hb.olay_ayarla([("CPI", T0), ("ISSIZLIK", T0), ("PPI", T0 + 5 * DK)])
    out = hb.haber_ivme(_barlar(_seri(True)), k=1, h=15, secim="hepsi")
    assert out.sum() == 15.0   # aynı dakika tek olay; 5 dk sonraki olay ilk pencerenin içinde → atlanır


def test_nedensellik_kirpma():
    hb.olay_ayarla([("NFP", T0)])
    c = _seri(True)
    tam = hb.haber_ivme(_barlar(c), k=1, h=15)
    for n in range(11, 60):   # veri n. barda kesilse de o ana kadarki kararlar aynı
        assert (hb.haber_ivme(_barlar(c[:n]), k=1, h=15) == tam[:n]).all()


def test_issizlik_kurali():
    g = ht.issizlik_tarihleri(date(2025, 11, 1), date(2026, 1, 10))
    assert "20251126" in g and "20251127" not in g     # Şükran Günü → çarşamba
    assert "20251224" in g and "20251225" not in g     # Noel perşembe → çarşamba
    assert "20260101" not in g and "20251231" in g     # yılbaşı perşembe → çarşamba
    assert "20251106" in g and "20260108" in g          # olağan perşembeler
    assert len(g) == 10
