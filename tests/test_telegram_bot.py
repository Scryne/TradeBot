"""Telegram botu (D4): Jev yönlendirmesi sahte; güvenlik kuralları ve olayların düğüme etkisi."""
import dataclasses

import pytest
from sqlalchemy import create_engine

from tests.test_canli import KAYIT, SahteBarlar, kol_yap, sentetik_depo
from tradebot.canli.defter import PaperDefter
from tradebot.canli.karar import KolDurum
from tradebot.db import metadata
from tradebot.telegram_bot import Bot


def _cevap(komut, kg=0.95, kol="hepsi", kolg=0.95, net=0.9):
    return {"komut": {"choice": komut, "confidence": kg}, "kol": {"choice": kol, "confidence": kolg}, "net": {"noul": net}}


@pytest.fixture
def ortam(tmp_path):
    m = create_engine(f"sqlite:///{tmp_path / 'b.db'}")
    metadata.create_all(m)
    a = dataclasses.replace(kol_yap(), ad="ma_yon@t@1h", baslangic_ozkaynak=100.0)
    j = dataclasses.replace(a, ad="ma_yon@t@1h+jev", ayar=dataclasses.replace(a.ayar, jev_veto=True))
    df = PaperDefter(m, "t")
    for k in (a, j):
        df.kol_ac(k, 0)
        df.ozkaynak_yaz(k.ad, 1_790_000_000_000, KolDurum(ozkaynak=104.0, nakit=50.0, adet={"BINANCE:AAAUSDT": 0.5}),
                        {"BINANCE:AAAUSDT": 108.0})
    siradaki = {}
    bot = Bot(m, tmp_path, [a, j], lambda s, q: siradaki["c"], simdi=lambda: 1_790_000_100)
    return bot, siradaki, df, a, j, m


def test_okuma_komutu_kodla_cevaplanir(ortam):
    bot, c, _, a, _, _ = ortam
    c["c"] = _cevap("kol_durumu", kol=a.ad)
    r = bot.isle("ma yön kolu nasıl")
    assert "ma_yon@t@1h" in r and "+4.00%" in r and "AAA %52" in r
    c["c"] = _cevap("bilinmiyor")
    assert "tahmini" in bot.isle("BTC yarın ne olur")


def test_riski_artiran_serbest_metinle_asla(ortam):
    bot, c, df, a, _, _ = ortam
    c["c"] = _cevap("riski_artir", kg=1.0, kol=a.ad)
    r = bot.isle("ma yön kolunu tekrar başlat")
    assert "/devam" in r and bot.bekleyen is None
    assert "Onay bekleyen" in bot.isle("evet") and df.kol_olaylari() == []


def test_durdurma_onayli_ve_belirsizde_adaylar(ortam):
    bot, c, df, a, j, _ = ortam
    c["c"] = _cevap("kol_durdur", kol=a.ad, net=0.26)            # "ma yön kolunu durdur": iki kopya var
    r = bot.isle("ma yön kolunu durdur")
    assert a.ad in r and j.ad in r and bot.bekleyen is None
    c["c"] = _cevap("kol_durdur", kg=0.6, kol=a.ad)               # düşük güven: eylem yok
    assert "Emin olamadım" in bot.isle("şunu durdursan mı") and bot.bekleyen is None
    c["c"] = _cevap("kol_durdur", kol=j.ad)
    assert j.ad in bot.isle("jevli ma yön kolunu durdur") and df.kol_olaylari() == []  # onay yok → olay yok
    assert "Tamam" in bot.isle("evet")
    o = df.kol_olaylari()
    assert [(x.kol, x.tur, x.ayrinti["neden"]) for x in o] == [(j.ad, "durdur", "telegram")]


def test_onay_suresi_dolar(ortam, monkeypatch):
    bot, c, df, _, _, _ = ortam
    c["c"] = _cevap("tumunu_durdur", kg=1.0)
    bot.isle("her şeyi durdur")
    bot.bekleyen.zaman -= 121
    assert "süresi doldu" in bot.isle("evet") and df.kol_olaylari() == []


def test_devam_acik_komut_ve_onay(ortam):
    bot, _, df, a, _, _ = ortam
    assert "tam yazılmalı" in bot.isle("/devam ma yön")
    assert "RİSKİ ARTIRIR" in bot.isle(f"/devam {a.ad}")
    bot.isle("evet")
    assert [x.tur for x in df.kol_olaylari(a.ad)] == ["devam"]


def test_dugum_elle_durdurmayi_uygular_ve_yeniden_baslatmada_korur(tmp_path, ayar):
    from tradebot.canli import dugum
    from tradebot.db import motor

    m = motor(ayar)
    metadata.create_all(m)
    depo, t = sentetik_depo(tmp_path, n=24 * 5)
    k1 = dataclasses.replace(kol_yap(), ad="k1", baslangic_ozkaynak=100.0)
    k2 = dataclasses.replace(k1, ad="k2")
    df = PaperDefter(m, "t")
    for k in (k1, k2):
        df.kol_ac(k, int(t[0]))
    b = dugum.Beyin(m, [k1, k2], df, SahteBarlar(depo), KAYIT)
    df.kol_olay_yaz("k1", "durdur", {"neden": "telegram"})
    df.kol_olay_yaz("k2", "durdur", {"neden": "mutabakat"})     # düğümün kendi yazdığı: yeniden başlatmada kalkar
    b._olaylari_uygula()
    assert b.durdurulan == {"k1"}
    b2 = dugum.Beyin(m, [k1, k2], df, SahteBarlar(depo), KAYIT)  # yeniden başlatma
    assert b2.durdurulan == {"k1"}
    df.kol_olay_yaz("k1", "devam", {"neden": "telegram"})
    b2._olaylari_uygula()
    assert b2.durdurulan == set() and dugum.Beyin(m, [k1, k2], df, SahteBarlar(depo), KAYIT).durdurulan == set()


def test_ayri_dugum_kollari_hepsini_durdura_girer():
    from tradebot.telegram_bot import ayri_dugum_kollari

    adlar = {k.ad for k in ayri_dugum_kollari()}
    assert {"d6b:kilit_kisa@kilit_perp@1d", "d9:doviz_tasima@g10_doviz@1d", "am15:kanal_kirilim@xau_m15@15m",
            "d10:fomc_dolar@g10_saatlik@1h"} <= adlar
