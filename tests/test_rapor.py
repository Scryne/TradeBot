"""Haftalık paper raporu: defterden getiri, düşüş, maliyet ayrımı (yürütme ↔ gecikme), Jev A/B, agresif, bekleyen hafta."""
import dataclasses

import pytest
from sqlalchemy import create_engine

from tests.test_canli import kol_yap
from tradebot.canli import dagitici as dg
from tradebot.canli import rapor
from tradebot.canli.defter import PaperDefter
from tradebot.canli.karar import Karar, KolDurum
from tradebot.db import metadata

H = dg.hafta_basi(1_790_000_000_000)
SAAT = 3_600_000


def _karar(kol, bar_ms, gecikmeli=False):
    import numpy as np
    z = np.zeros(1)
    return Karar(kol, bar_ms, ("BINANCE:AAAUSDT",), z, z, z, z, np.array([True]), np.array([100.0]), "normal", (), {})


def test_haftalik_rapor(tmp_path):
    m = create_engine(f"sqlite:///{tmp_path / 'r.db'}")
    metadata.create_all(m)
    df = PaperDefter(m, "t")
    a = dataclasses.replace(kol_yap(), ad="x@g@1h", baslangic_ozkaynak=100.0)
    j = dataclasses.replace(a, ad="x@g@1h+jev")
    ag = dataclasses.replace(a, ad="agresif@g", strateji="agresif", sinif="gozlem")
    for k in (a, j, ag):
        df.kol_ac(k, H - 7 * 86_400_000)
    yol = {a.ad: [100, 110, 99, 104.5], j.ad: [100, 110, 99, 105.6], ag.ad: [100, 120, 90, 100]}
    zaman = [H - 2 * SAAT, H - SAAT, H + 5 * SAAT, H + 30 * SAAT]  # ikisi hafta öncesi
    for k, oz in yol.items():
        for t, o in zip(zaman, oz, strict=True):
            df.ozkaynak_yaz(k, t, KolDurum(ozkaynak=o, nakit=o), {})

    import tradebot.canli.defter as dm
    zamanlar = iter([H + SAAT, H + 2 * SAAT])
    orijinal = dm.time.time
    dm.time.time = lambda: next(zamanlar) / 1000
    try:
        k1 = df.karar_yaz(_karar(a.ad, H), "h", gecikmeli=False)
        k2 = df.karar_yaz(_karar(a.ad, H + SAAT), "h", gecikmeli=True)
    finally:
        dm.time.time = orijinal
    # zamanında: gönderim 100, dolum 100,05 (alış: 5 bps aleyhte) + ücret 10 bps
    e1 = df.emir_yaz(a.ad, k1, "c1", "BINANCE:AAAUSDT", 1.0, 1.0, 99.0, "karar", {}, gonderim_fiyati=100.0)
    df.olay_yaz(e1, a.ad, "dolum", "BINANCE:AAAUSDT", 1.0, 100.05, 100.05 * 0.001, H + SAAT + 1)
    # gecikmeli satış: karar 100, gönderim 99 (satışta −1% → 100 bps aleyhte gecikme kayması)
    e2 = df.emir_yaz(a.ad, k2, "c2", "BINANCE:AAAUSDT", -1.0, -1.0, 100.0, "karar", {}, gonderim_fiyati=99.0)
    df.olay_yaz(e2, a.ad, "dolum", "BINANCE:AAAUSDT", -1.0, 99.0, 0.0, H + 2 * SAAT + 1)
    df.kol_olay_yaz(a.ad, "durdur", {"neden": "mutabakat"}, zaman_ms=H + 3 * SAAT)

    r = rapor.ozetle(rapor.topla(m, H))
    x = {k["kol"]: k for k in r["kollar"]}[a.ad]
    assert x["hafta"] == pytest.approx(104.5 / 110 - 1) and x["toplam"] == pytest.approx(0.045)
    assert x["en_kotu_dusus"] == pytest.approx(99 / 110 - 1)
    assert x["yurutme_bps"] == pytest.approx(15.0, abs=1e-6) and x["gecikme_bps"] == pytest.approx(100.0, rel=1e-3)
    assert x["islem"] == 2 and x["karar"] == 2 and x["olay"] == ["durdur"]
    assert r["jev_ab"] == [pytest.approx({"kol": a.ad, "hafta_fark": 105.6 / 110 - 104.5 / 110, "toplam_fark": 0.011,
                                          "veto": 0})]
    ag_r = r["agresif"][0]
    assert ag_r["hafta"] == pytest.approx(100 / 120 - 1) and ag_r["kaynak_ort"] == pytest.approx(x["hafta"])
    md = rapor.markdown(r)
    assert "x@g@1h" in md and "Jev A/B" in md and "Agresif" in md
    assert "x@g@1h+jev" not in rapor.telegram_ozeti(r) and "durdur" in rapor.telegram_ozeti(r)


def test_bekleyen_hafta(tmp_path):
    simdi = H + 7 * 86_400_000 + 10 * 60_000            # sonraki Pazartesi 00:10: henüz erken
    assert rapor.bekleyen_hafta(tmp_path, simdi, H - dg.HAFTA_MS) == H - dg.HAFTA_MS
    simdi += 30 * 60_000                                  # 00:40
    assert rapor.bekleyen_hafta(tmp_path, simdi, H - dg.HAFTA_MS) == H
    (tmp_path / "rapor").mkdir()
    import datetime as dt
    (tmp_path / "rapor" / f"paper-{dt.datetime.fromtimestamp(H / 1000, dt.UTC).date()}.md").write_text("x")
    assert rapor.bekleyen_hafta(tmp_path, simdi, H - dg.HAFTA_MS) is None
    assert rapor.bekleyen_hafta(tmp_path / "yok", simdi, H + dg.HAFTA_MS) is None   # paper hafta bittikten sonra başladı
    assert rapor.bekleyen_hafta(tmp_path / "yok", simdi, None) is None             # hiç paper kolu yok
    assert rapor.bekleyen_hafta(tmp_path / "yok", simdi, H + 3 * 86_400_000) == H   # hafta içinde başladı: raporlanır


def test_gunluk_ozet(tmp_path):
    from datetime import UTC, datetime

    from tradebot import denetim
    from tradebot.cli import gunluk_ozet_zamani

    m = create_engine(f"sqlite:///{tmp_path / 'g.db'}")
    metadata.create_all(m)
    df = PaperDefter(m, "t")
    a = dataclasses.replace(kol_yap(), ad="x@g@1h", baslangic_ozkaynak=100.0)
    j = dataclasses.replace(a, ad="x@g@1h+jev")
    eski = dataclasses.replace(a, ad="eski@g@1h")
    for k in (a, j, eski):
        df.kol_ac(k, H - 7 * 86_400_000)
    simdi = H + 30 * SAAT
    for k, oz in ((a.ad, [100, 102, 101]), (j.ad, [100, 102, 103])):
        for t, o in zip([H - SAAT, H + 5 * SAAT, H + 29 * SAAT], oz, strict=True):   # ilki 24 saatten önce
            df.ozkaynak_yaz(k, t, KolDurum(ozkaynak=o, nakit=o), {})
    df.ozkaynak_yaz(eski.ad, H - SAAT, KolDurum(ozkaynak=99, nakit=99), {})          # emekli: pencerede işaret yok
    denetim.kaydet(m, "veri", "gece_isi", {"binance": {"dosya": 3}, "yahoo": {"hata": "HTTPError: 503"}},
                   zaman=datetime.fromtimestamp((simdi - 3 * SAAT) / 1000, UTC))
    metin = rapor.gunluk_ozet(m, simdi, "Sağlık: hepsi OK")
    # pencere [H+6s, H+30s): başlangıç H+5s işareti (102) → 101; başlangıçtan 100 → 101
    assert "Sağlık: hepsi OK" in metin and "x@g@1h: -0.98% · +1.00%" in metin
    assert "Jev farkı +1.96%" in metin and "x@g@1h+jev:" not in metin         # Jev'li kopya yalnız fark olarak
    assert "HATALI adım: yahoo" in metin and "Jev: yeni olay yok" in metin
    assert "eski@g@1h" not in metin and "+1 kol dönemde işaret yazmadı" in metin
    # zamanlama: sessiz saat bitmeden yok, bittikten sonra bir kez
    sabah = int(datetime(2026, 9, 28, 4, 59, tzinfo=UTC).timestamp() * 1000)
    assert gunluk_ozet_zamani(sabah, 5, tmp_path) is None
    yol = gunluk_ozet_zamani(sabah + 2 * 60_000, 5, tmp_path)
    assert yol is not None and yol.name == "gunluk-2026-09-28.txt"
    yol.parent.mkdir(parents=True)
    yol.write_text("x")
    assert gunluk_ozet_zamani(sabah + 3 * SAAT, 5, tmp_path) is None


def test_kanit_kapisi():
    """Gerçek para kapısı: haftalık getiri Pazartesi sınırlarından, açılış yarım haftası atlanır, ≥ 26 hafta + PSR."""
    import numpy as np

    hf = dg.HAFTA_MS
    bas = H + 3 * 86_400_000  # hafta ortasında açılış: ilk sınır H + hf
    assert rapor.kanit_kapisi([], H)["gecti"] is False
    rng = np.random.default_rng(0)
    g = 0.01 + 0.01 * rng.standard_normal(40)            # haftalık Sharpe ~1: güçlü
    oz = 100 * np.exp(np.concatenate([[0.0], np.cumsum(g)]))
    isaret = [(bas, 100.0)] + [(H + (i + 1) * hf - SAAT, float(o)) for i, o in enumerate(oz)]
    k = rapor.kanit_kapisi(isaret, H + 41 * hf)
    assert k["hafta"] == 40 and k["sr"] > 0.5 and k["psr"] > 0.95 and k["gecti"]
    kisa = rapor.kanit_kapisi(isaret[:12], H + 11 * hf)   # aynı güçlü seri, 10 hafta: asgari hafta yüzünden geçmez
    assert kisa["hafta"] == 10 and not kisa["gecti"] and kisa["gerekli_hafta"] == rapor.KANIT_ASGARI_HAFTA
    zayif = [(t, 100.0 * (1 + 0.02 * ((i % 2) * 2 - 1))) for i, (t, _) in enumerate(isaret)]
    z = rapor.kanit_kapisi(zayif, H + 41 * hf)
    assert not z["gecti"] and (z["sr"] is None or z["sr"] <= 0.1)
