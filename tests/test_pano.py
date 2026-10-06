"""Faz 10 web pano: veri şekli, salt okunurluk, sır sızmaması (sentetik SQLite defter)."""
import pytest
from fastapi.testclient import TestClient

from tradebot.ayar import Ayarlar
from tradebot.pano import veri
from tradebot.pano.ornek import kur
from tradebot.pano.sunucu import SaglikOnbellek, uygulama
from tradebot.saglik import Sonuc

SIMDI = 1_790_608_000_000


@pytest.fixture(scope="module")
def ortam(tmp_path_factory):
    d = tmp_path_factory.mktemp("pano")
    m = kur(f"sqlite:///{d / 'o.db'}", SIMDI, gun=10, veri_dizini=d, kilit=True)
    return m, d


def test_kol_bilgi_adlari_ayirir():
    k = veri.kol_bilgi("d2:donchian_ls@kripto_btc_eth@4h+jev")
    assert (k["taban"], k["jev"], k["strateji"], k["dalga"], k["zd"], k["tur"]) == \
        ("d2:donchian_ls@kripto_btc_eth@4h", True, "donchian_ls", "d2", "4h", "kol")
    assert veri.kol_bilgi("ma_yon@kripto_btc_eth@1h")["dalga"] == "d1"
    assert veri.kol_bilgi("agresif@kripto_btc_eth")["tur"] == "agresif"


def test_pano_ozeti_defterle_tutarli(ortam):
    m, d = ortam
    p = veri.pano(m, SIMDI, d, "test")
    assert p["durum"]["kol"] == 14 and not p["durum"]["bayat"]
    assert p["turnuva"]["gun"] == 11 and p["turnuva"]["toplam_gun"] == 84
    # şerit: her kol bir satır, 72 saat; maruziyet özkaynak işaretinden
    assert len(p["serit"]["saatler"]) == veri.SERIT_SAAT
    assert {s["kol"] for s in p["serit"]["satirlar"]} == {k["kol"] for k in p["kollar"]}
    assert all(len(s["hucreler"]) == veri.SERIT_SAAT for s in p["serit"]["satirlar"])
    # getiri haftalık raporla aynı hesap: son işaret / başlangıç − 1
    for k in p["kollar"]:
        assert k["toplam"] == pytest.approx(k["ozkaynak"] / k["baslangic_ozkaynak"] - 1)
    # turnuva sonuç dosyası plana bağlanır
    plan = {x["kimlik"]: x for x in p["defter"]["planlar"]}
    assert plan["2026-09-28-viop2-tasima"]["karar"] == "KALDI"
    assert plan["2026-09-25-d1-trend"]["karar"] == "B"


def test_toparlanma_dolum_sayilmaz(tmp_path):
    from sqlalchemy import insert

    from tradebot.db import paper_emir_olay

    m = kur(f"sqlite:///{tmp_path / 'o.db'}", SIMDI, gun=4)
    kol = "ma_yon@kripto_btc_eth@1h"
    once = veri.pano(m, SIMDI)["serit"]["satirlar"]
    with m.begin() as b:
        b.execute(insert(paper_emir_olay).values(emir_id=0, kol=kol, tur="toparlanma", enstruman="BINANCE:BTCUSDT",
                                                 miktar=1.0, fiyat=1.0, ucret=0.0, zaman_ms=SIMDI - 1000, ayrinti={}))
    sonra = veri.pano(m, SIMDI)["serit"]["satirlar"]
    assert once == sonra
    assert all(d["tur"] == "dolum" for d in veri.kol(m, kol, SIMDI)["dolumlar"])


def test_bayat_veri_isaretlenir(ortam):
    m, d = ortam
    p = veri.pano(m, SIMDI + 3 * veri.SAAT_MS, d)
    assert p["durum"]["bayat"]


def test_kol_ayrintisi_ikiziyle(ortam):
    m, _ = ortam
    k = veri.kol(m, "tsmom@kripto_btc_eth@4h+jev", SIMDI)
    assert k["ikiz"] == "tsmom@kripto_btc_eth@4h" and k["seri"] and k["ikiz_seri"]
    assert veri.kol(m, "yok@x", SIMDI) is None


def test_kilit_kollari_olay_sonucu_ve_takvim(ortam):
    from tradebot.pano import kilit as pk
    from tradebot.pano.ornek import KILIT

    m, d = ortam
    k = veri.pano(m, SIMDI, d)["kilit"]
    paper, demo = k["kollar"]
    assert (paper["kol"], paper["gercek"], demo["kol"], demo["ortam"]) == (KILIT, False, KILIT + "#gercek", "demo")
    assert k["kural"]["giris"] == -7 and k["kapi"]["asgari_hafta"] == 26
    assert k["sonraki_karar_ms"] > SIMDI and k["sonraki_karar_ms"] % pk.GUN_MS == pk.KARAR_GECIKME_MS
    # paper: MOVE ve CARV açılım gününde kapandı, SEI ve STRK açık; olay sonucu nakit + açık bacak değeri
    assert {e["sembol"] for e in paper["acik"]} == {"SEI", "STRK"}
    kap = {e["sembol"]: e for e in paper["kapanan"]}
    assert set(kap) == {"MOVE", "CARV"} and all(e["neden"] == "cikis" and e["btc_dahil"] for e in kap.values())
    dkap = {e["sembol"]: e for e in demo["kapanan"]}                  # Demo'da olay = yalnız token bacağı
    assert dkap["CARV"]["sonuc"] < 0 < dkap["MOVE"]["sonuc"]          # token düştüyse kısa kazanır
    assert paper["kapanan_ozet"] == {"adet": 2, "kazanan": sum(e["sonuc"] > 0 for e in kap.values()),
                                     "toplam": pytest.approx(sum(e["sonuc"] for e in kap.values()))}
    assert paper["fonlama"] > 0                                       # kısa bacak funding alır (örnek)
    # Demo: SEI kararda var ama borsa düşürdü → dolum yok, ret gerekçesi görünür; BTC koruması olaya bağlı değil
    sei = next(x for kr in demo["kararlar"] for x in kr["ac"] if x["sembol"] == "SEI")
    assert sei["dolum"] is False and "-1000" in demo["retler"][0]["gerekce"]
    assert {e["sembol"] for e in demo["acik"]} == {"STRK"} and not any(e["btc_dahil"] for e in demo["acik"])
    # yaklaşan: takvim hamdan; durum paper koluna göre
    y = {e["sembol"]: e["durum"] for e in k["yaklasan"]["olaylar"]}
    assert y == {"SEI": "acik", "STRK": "acik", "ARB": "kacti", "QUAI": "perp_yok", "ZRO": "bekliyor",
                 "APR": "bekliyor", "EIGEN": "bekliyor"}


def test_durdurulan_kol_calisan_sayilmaz(tmp_path):
    from sqlalchemy import insert

    from tradebot.db import paper_kol_olay

    m = kur(f"sqlite:///{tmp_path / 'o.db'}", SIMDI, gun=4)
    kol = "ma_yon@kripto_btc_eth@1h"
    once = veri.pano(m, SIMDI)
    with m.begin() as b:
        b.execute(insert(paper_kol_olay).values(kol=kol, zaman_ms=SIMDI - 1000, tur="durdur", kod_surumu="t",
                                                ayrinti={"neden": "scryne_hepsini_kapat"}))
    p = veri.pano(m, SIMDI)
    assert (p["durum"]["kol"], p["durum"]["durdurulan"]) == (once["durum"]["kol"] - 1, 1)
    assert kol not in {s["kol"] for s in p["serit"]["satirlar"]}
    assert next(k for k in p["kollar"] if k["kol"] == kol)["durduruldu"]
    k = veri.kol_bilgi("d13:kilit_kisa@kilit_perp@1d#gercek")
    assert (k["zd"], k["hesap"], k["strateji"], k["dalga"]) == ("1d", "gercek", "kilit_kisa", "d13")


def test_kilit_durdurulan_kol_gizlenir():
    from tradebot.pano.kilit import durduruldu

    assert durduruldu([("durdur", {"neden": "scryne_hepsini_kapat"})])
    assert not durduruldu([("durdur", {"neden": "x"}), ("devam", {"neden": "y"})])
    assert not durduruldu([("durdur", {"neden": "mutabakat"})])       # mutabakat durdurması elle sayılmaz


def test_ornek_veri_canliya_yazmaz():
    with pytest.raises(ValueError):
        kur("postgresql+psycopg://x@y/z", SIMDI)


@pytest.fixture()
def istemci(ortam):
    m, d = ortam
    a = Ayarlar(veri_dizini=d, telegram_token="gizli-token-degeri")
    sag = SaglikOnbellek(a, kontrol=lambda _a: [Sonuc("sirlar", "OK", "tümü tanımlı", {"telegram_token": True})])
    sag._yenile()
    return TestClient(uygulama(m, a, None, saat=lambda: SIMDI, saglik_onbellek=sag))


def test_api_salt_okunur_ve_basliklar(istemci):
    r = istemci.get("/api/pano")
    assert r.status_code == 200 and r.json()["durum"]["kol"] == 14
    assert "frame-ancestors 'none'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store"
    for yontem in ("post", "put", "delete", "patch"):
        assert getattr(istemci, yontem)("/api/pano").status_code == 405
    assert istemci.get("/api/kol/" + "tsmom@kripto_btc_eth@4h%2Bjev").json()["jev"] is True
    assert istemci.get("/api/kol/yok").status_code == 404
    assert istemci.get("/docs").status_code == 404


def test_saglik_olcum_ve_sir_panoya_gitmez(istemci):
    r = istemci.get("/api/saglik").json()
    assert r["hazir"] and r["kontroller"][0] == {"ad": "sirlar", "durum": "OK", "ayrinti": "tümü tanımlı"}
    govde = istemci.get("/api/pano").text + istemci.get("/api/saglik").text
    assert "gizli-token-degeri" not in govde
