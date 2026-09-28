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
    m = kur(f"sqlite:///{d / 'o.db'}", SIMDI, gun=10, veri_dizini=d)
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
    assert p["durum"]["kol"] == 12 and not p["durum"]["bayat"]
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


def test_bayat_veri_isaretlenir(ortam):
    m, d = ortam
    p = veri.pano(m, SIMDI + 3 * veri.SAAT_MS, d)
    assert p["durum"]["bayat"]


def test_kol_ayrintisi_ikiziyle(ortam):
    m, _ = ortam
    k = veri.kol(m, "tsmom@kripto_btc_eth@4h+jev", SIMDI)
    assert k["ikiz"] == "tsmom@kripto_btc_eth@4h" and k["seri"] and k["ikiz_seri"]
    assert veri.kol(m, "yok@x", SIMDI) is None


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
    assert r.status_code == 200 and r.json()["durum"]["kol"] == 12
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
