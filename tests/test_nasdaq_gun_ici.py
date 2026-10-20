"""Nasdaq gün içi düğümü: dakikadan saatlik bar, 15:00 NY girişi, 15:59 çıkışı, durdurma, nakit tavanı."""
from datetime import UTC, datetime

import numpy as np
import pytest

from tradebot.canli import nasdaq_gun_ici as gi
from tradebot.canli.defter import PaperDefter
from tradebot.db import metadata, motor

DK = 60_000


def _ms(s: str) -> int:
    return int(datetime.fromisoformat(s).replace(tzinfo=UTC).timestamp() * 1000)


def test_saatlik_yalniz_kapanmis_saatler():
    t = _ms("2026-10-19T13:30:00") + np.arange(150, dtype=np.int64) * DK      # 09:30 → 11:59 NY
    c = 100 + np.arange(150, dtype=float)
    b = gi.saatlik(t, c, c + 0.5, c - 0.5, c, _ms("2026-10-19T15:59:30"))     # 11:00 NY saati henüz bitmedi
    assert list(b.t) == [_ms("2026-10-19T13:00:00"), _ms("2026-10-19T14:00:00")]
    assert b.close[0] == c[29] and b.open[0] == c[0] and b.close[1] == c[89]


def test_agirlik_nakit_tavani():
    c = 100 * np.exp(np.cumsum(np.full(80, 0.001) + np.tile([0.01, -0.01], 40)))
    w = gi.agirlik(c, 0.25, 60, 1.0)
    assert 0 < w <= 1.0
    assert gi.agirlik(c[:30], 0.25, 60, 1.0) == 0.0          # yetersiz geçmiş: nakit


def _yapi():
    return {"frenler": True, "nasdaq_gun_ici": {
        "ad": "d20:gun_ici_ivme@qqq@1h", "strateji": "gun_ici_ivme", "parametre": {"tutma": 1, "kisa": False},
        "boyut": {"hedef_vol": 0.25, "kaldirac": 1.0, "vol_pencere_gun": 60}, "yurutme": "ic",
        "baslangic_ozkaynak": 100_000}}


def test_alpaca_hesabi_gunluk_kollarla_paylasilmaz():
    gunluk = {"yurutme": "otomatik", "kollar": [{"ad": "a"}, {"ad": "b", "yurutme": "ic"}]}
    y = _yapi() | {"nasdaq": gunluk}
    for yur in ("alpaca", "otomatik"):
        y["nasdaq_gun_ici"] = _yapi()["nasdaq_gun_ici"] | {"yurutme": yur}
        with pytest.raises(ValueError, match="paylaşamaz"):
            gi.ayarlar(y)
    y["nasdaq_gun_ici"]["yurutme"] = "ic"
    assert gi.ayarlar(y).yurutme == "ic"
    y["nasdaq"] = {"yurutme": "otomatik", "kollar": [{"ad": "b", "yurutme": "ic"}]}   # günlükte Alpaca kolu yok
    y["nasdaq_gun_ici"]["yurutme"] = "alpaca"
    assert gi.ayarlar(y).yurutme == "alpaca"


def test_canli_ayar_tek_hesap_kuralina_uyar():
    assert gi.ayarlar().yurutme == "ic"


class SahteKaynak:
    """Önceki gün 16:00 NY kapanışı 100; bugün 10:00 NY 101 (r1 > 0); fiyat dakika başı sabit artar."""

    def __init__(self) -> None:
        bas = _ms("2026-10-16T13:30:00")
        gun1 = bas + np.arange(390, dtype=np.int64) * DK
        gun2 = _ms("2026-10-19T13:30:00") + np.arange(390, dtype=np.int64) * DK
        self.t = np.r_[gun1, gun2]
        self.c = np.r_[np.full(390, 100.0), 101.0 + np.arange(390) * 0.001]

    def dakikalik(self):
        return self.t, self.c, self.c, self.c, self.c

    def gunluk_kapanis(self):
        return 100 * np.exp(np.cumsum(np.tile([0.008, -0.008], 50)))

    def son_fiyat(self):
        return 101.2


def _dugum(ayar):
    m = motor(ayar)
    metadata.create_all(m)
    s = {"t": 0}
    d = gi.GunIciDugumu(PaperDefter(m, "test"), gi.ayarlar(_yapi()), SahteKaynak(), None, saat=lambda: s["t"] / 1000)
    d.ac()
    return d, s


def test_giris_1500_cikis_1559(ayar):
    d, s = _dugum(ayar)
    s["t"] = _ms("2026-10-19T18:00:30")                      # 14:00 NY: sinyal yok
    r = d.tur()
    assert r["karar"]["sinyal"] == 0.0
    s["t"] = _ms("2026-10-19T19:00:30")                      # 15:00 NY: r1 > 0 → uzun
    r = d.tur()
    assert r["karar"]["sinyal"] == 1.0 and r["karar"]["dolum"] > 0
    adet = d.defter.durum(d.kol).adet["ARCA:QQQ"]
    assert 0 < adet * 101.0 <= 100_000 * 1.01                 # brüt ≤ 1x
    s["t"] = _ms("2026-10-19T19:30:00")
    assert "cikis" not in d.tur()
    s["t"] = _ms("2026-10-19T19:59:10")                      # 15:59 NY: çıkış
    assert d.tur()["cikis"]["dolum"] == pytest.approx(-adet)
    assert not d.defter.durum(d.kol).adet


def test_elle_durdurma_hemen_kapatir(ayar):
    d, s = _dugum(ayar)
    s["t"] = _ms("2026-10-19T19:00:30")
    d.tur()
    d.defter.kol_olay_yaz(d.kol.ad, "durdur", {"neden": "telegram"})
    s["t"] = _ms("2026-10-19T19:10:00")
    assert d.tur()["cikis"]["dolum"] < 0 and not d.defter.durum(d.kol).adet
