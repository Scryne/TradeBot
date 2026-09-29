"""Dalga 7 yeni listeleme kısası: olay üretimi (listeleme anından, PIT), dışlamalar ve kilit motoruyla uçtan uca."""
import numpy as np
import polars as pl
import pytest

from tradebot.arastirma import kilit as kl
from tradebot.arastirma import listeleme as ls

G = 86_400_000
T0 = 1_700_006_400_000 // G * G


def test_olaylar_listeleme_gunu_dislamalar_ve_yeniden_listeleme():
    perp = {"NEW": {"liste_ms": T0 + 13 * 3_600_000}, "OLD": {"liste_ms": T0 - 400 * G}, "USDC": {"liste_ms": T0},
            "BTCDOM": {"liste_ms": T0}, "RELIST": {"liste_ms": T0}, "YOKMUM": {"liste_ms": T0 + 2 * G}}
    ilk = {"NEW": T0, "RELIST": T0 - 100 * G}
    e = ls.olaylar(perp, ilk, giris_gun=1, bitis_gun=14, bas_ms=T0 - 10 * G)
    assert dict(zip(e["sembol"].to_list(), e["gun_ms"].to_list(), strict=True)) == {
        "NEW": T0 + 14 * G, "YOKMUM": T0 + 16 * G}   # gün içi listeleme gün başına iner; mumu olmayan olay kalır
    with pytest.raises(ValueError):
        ls.olaylar(perp, ilk, 5, 5, T0)


def test_motorla_giris_listelemeden_sonra_cikis_bitis_gununde():
    n = 40
    fiyat = list(100 * 0.98 ** np.arange(n))                  # yeni token her gün −%2
    token = pl.DataFrame({"acilis_ms": [T0 + i * G for i in range(n)], "open": fiyat, "high": fiyat, "low": fiyat,
                          "close": fiyat, "volume": [1.0] * n})
    btc = token.with_columns(pl.lit(1.0).alias("open"))
    ev = ls.olaylar({"NEW": {"liste_ms": T0}}, {"NEW": T0}, giris_gun=1, bitis_gun=8, bas_ms=T0)
    a = kl.KilitAyar(giris=-7, cikis=0, notional=0.10)
    seri, o = kl.kos(ev, {"NEW": token}, {}, btc, pl.DataFrame(), a, T0, T0 + n * G)
    assert o["getiri"][0] == pytest.approx(7 * 0.02 - 2 * (a.ucret + a.kayma_token) - 2 * (a.ucret + a.kayma_btc), rel=1e-3)
    assert seri["gun_ms"].min() == T0 + G and seri["gun_ms"].max() == T0 + 8 * G


def test_zarar_kes_sikismada_erken_kapatir():
    n = 40
    fiyat = list(100 * 1.10 ** np.arange(n))                  # kısa sıkıştırması: her gün +%10
    token = pl.DataFrame({"acilis_ms": [T0 + i * G for i in range(n)], "open": fiyat, "high": fiyat, "low": fiyat,
                          "close": fiyat, "volume": [1.0] * n})
    btc = token.with_columns(pl.lit(1.0).alias("open"))
    ev = ls.olaylar({"NEW": {"liste_ms": T0}}, {"NEW": T0}, giris_gun=1, bitis_gun=30, bas_ms=T0)
    tam = kl.kos(ev, {"NEW": token}, {}, btc, pl.DataFrame(), kl.KilitAyar(giris=-29, cikis=0), T0, T0 + n * G)[1]
    kes = kl.kos(ev, {"NEW": token}, {}, btc, pl.DataFrame(), kl.KilitAyar(giris=-29, cikis=0, zarar_kes=0.3),
                 T0, T0 + n * G)
    g = kes[1]["getiri"][0]
    assert tam["getiri"][0] < -2.0                            # kesmeden: 29 gün × −%10
    assert -0.35 < g <= -0.3                                  # 3 gün × −%10 + maliyet: eşik aşıldı, bir sonraki açılışta çıkış
    assert kes[0]["gun_ms"].max() == T0 + 4 * G               # giriş gün 1 açılışı, çıkış gün 4 açılışı
