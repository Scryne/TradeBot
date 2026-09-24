from datetime import UTC, datetime

import pytest
from sqlalchemy import text, update

from tradebot import denetim
from tradebot.db import denetim_izi, metadata, motor


@pytest.fixture
def m(ayar):
    e = motor(ayar)
    metadata.create_all(e)
    return e


def test_zincir_saglam_ve_ardisik(m):
    h1 = denetim.kaydet(m, "test", "a", {"x": 1})
    h2 = denetim.kaydet(m, "test", "b", {"y": [1, 2], "z": "ş"})
    assert h1 != h2
    saglam, kirik, n = denetim.dogrula(m)
    assert saglam and kirik is None and n == 2
    with m.connect() as b:
        onceki = b.execute(text("SELECT onceki_hash FROM denetim_izi WHERE id = 2")).scalar()
    assert onceki == h1


def test_degistirilen_kayit_yakalanir(m):
    for i in range(3):
        denetim.kaydet(m, "test", f"olay{i}", {"i": i})
    with m.begin() as b:  # saldırgan veriyi değiştirir
        b.execute(update(denetim_izi).where(denetim_izi.c.id == 2).values(veri={"i": 999}))
    saglam, kirik, _ = denetim.dogrula(m)
    assert not saglam and kirik == 2


def test_silinen_kayit_yakalanir(m):
    for i in range(3):
        denetim.kaydet(m, "test", f"olay{i}", {"i": i})
    with m.begin() as b:
        b.execute(text("DELETE FROM denetim_izi WHERE id = 2"))
    saglam, kirik, _ = denetim.dogrula(m)
    assert not saglam and kirik == 3


def test_ayni_icerik_farkli_zaman_farkli_hash(m):
    t = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)
    h1 = denetim.kaydet(m, "test", "ayni", {"k": 1}, zaman=t)
    h2 = denetim.kaydet(m, "test", "ayni", {"k": 1}, zaman=t)
    assert h1 != h2  # zincir: önceki hash farklı
    assert denetim.dogrula(m)[0]
