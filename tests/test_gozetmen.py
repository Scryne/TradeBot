"""Bağımsız gözetmen (risk katmanı 5): donma tespiti, yanlış alarm koruması, defterde kapatma, düğümün toparlanması."""
import pytest
from sqlalchemy import func, select

from tradebot.canli.gozetmen import NEDEN, Gozetmen, net_pozisyonlar
from tradebot.db import denetim_izi, paper_emir, paper_kol_olay
from tradebot.pano.ornek import kur

SIMDI = 1_790_608_000_000
SAAT = 3_600_000
KOTASYON = {"BINANCE:BTCUSDT": (80_000.0, 80_010.0), "BINANCE:ETHUSDT": (2_600.0, 2_600.5)}


class Saat:
    def __init__(self, ms):
        self.ms = ms

    def __call__(self):
        return self.ms / 1000


def say(m, tablo, *kosul):
    with m.connect() as b:
        return b.execute(select(func.count()).select_from(tablo).where(*kosul)).scalar()


@pytest.fixture()
def defter(tmp_path):
    return kur(f"sqlite:///{tmp_path / 'o.db'}", SIMDI, gun=16)


def test_canli_kalp_atisi_dokunmaz(defter):
    g = Gozetmen(defter, lambda k: KOTASYON, saat=Saat(SIMDI + 10 * 60_000))
    assert g.kontrol()["durum"] == "canli"
    assert say(defter, paper_kol_olay) == 0


def test_donma_isinma_ve_tur_onayi_olmadan_kapatmaz(defter):
    s = Saat(SIMDI + 4 * SAAT)
    g = Gozetmen(defter, lambda k: KOTASYON, saat=s)
    assert g.kontrol()["durum"] == "donma_suphesi"          # ısınma
    s.ms += 20 * 60_000
    assert g.kontrol()["durum"] == "donma_suphesi"          # ısınma geçti, 2. tur
    assert say(defter, paper_kol_olay) == 0 and net_pozisyonlar(defter)


def test_donma_kapatir_durdurur_ve_tekrar_yazmaz(defter):
    once = net_pozisyonlar(defter)
    assert once                                             # örnek defterde açık pozisyon var
    s = Saat(SIMDI + 3 * SAAT)
    g = Gozetmen(defter, lambda k: KOTASYON, kod_surumu="test", saat=s)
    s.ms += 20 * 60_000
    sonuclar = [g.kontrol() for _ in range(3)]
    r = sonuclar[-1]
    assert [x["durum"] for x in sonuclar] == ["donma_suphesi", "donma_suphesi", "donma"]
    assert net_pozisyonlar(defter) == {}                    # defter düz
    assert set(r["kapatilan"]) == set(once) and len(r["durdurulan"]) == 12
    for kol, poz in r["kapatilan"].items():
        for kim, v in poz.items():
            bid, ask = KOTASYON[kim]
            assert v["adet"] == pytest.approx(-once[kol][kim])
            assert v["fiyat"] < bid if v["adet"] < 0 else v["fiyat"] > ask   # aleyhte kayma
    assert say(defter, paper_emir, paper_emir.c.tur == "gozetmen") == sum(len(p) for p in once.values())
    assert say(defter, paper_kol_olay, paper_kol_olay.c.tur == "durdur") == 12
    assert say(defter, denetim_izi, denetim_izi.c.olay == "donma_kapatma") == 1
    s.ms += 5 * 60_000
    r2 = g.kontrol()                                        # aynı donma: yeni yazım yok
    assert r2["durum"] == "donma" and r2["kapatilan"] == {} and r2["durdurulan"] == []
    assert say(defter, paper_kol_olay) == 12


def test_kuru_ve_fiyat_hatasi_yazmaz(defter):
    s = Saat(SIMDI + 3 * SAAT)
    g = Gozetmen(defter, lambda k: KOTASYON, kuru=True, onay_tur=1, isinma_sn=0, saat=s)
    r = g.kontrol()
    assert r["kuru"] and r["kapatilacak"] and len(r["durdurulacak"]) == 12

    def bozuk(_k):
        raise ConnectionError("binance yok")
    g2 = Gozetmen(defter, bozuk, onay_tur=1, isinma_sn=0, saat=s)
    with pytest.raises(ConnectionError):
        g2.kontrol()
    assert say(defter, paper_kol_olay) == 0 and say(defter, paper_emir, paper_emir.c.tur == "gozetmen") == 0


def test_dugum_cozulunce_defterden_kurar_ve_sandboxi_duzler(tmp_path, ayar, monkeypatch):
    """Motor donmuş sanıldı, gözetmen defteri kapattı; motor sonra çözüldü: bellek defterden yenilenir, sandbox düzlenir,
    kol durdurulmuş kalır."""
    import dataclasses

    from tests.test_canli import KAYIT, SahteBarlar, SahteStrateji, kol_yap, sentetik_depo
    from tradebot.canli import dugum
    from tradebot.canli.defter import PaperDefter
    from tradebot.db import metadata, motor

    monkeypatch.setattr(dugum, "aktif_vetolar", lambda m, t: set())
    m = motor(ayar)
    metadata.create_all(m)
    depo, t = sentetik_depo(tmp_path, n=24 * 40)
    k1 = dataclasses.replace(kol_yap(frenler=False), baslangic_ozkaynak=100_000.0)
    df = PaperDefter(m, "test")
    df.kol_ac(k1, int(t[0]))
    b = dugum.Beyin(m, [k1], df, SahteBarlar(depo), KAYIT)
    s1 = b.stratejiler[k1.ad] = SahteStrateji(b, k1)
    kapanis = int(t[-1]) + SAAT
    monkeypatch.setattr(dugum.time, "time", lambda: (kapanis + 5_000) / 1000)
    assert b.saat_kapandi(kapanis)
    assert b.durum[k1.ad].adet and s1.poz                   # pozisyon var (bellek + sandbox)
    kot = {k: (float(depo.oku(k, "1h")["close"][-1]),) * 2 for k in KAYIT}
    g = Gozetmen(m, lambda k: kot, onay_tur=1, isinma_sn=0, saat=Saat(kapanis + 3 * SAAT))
    assert g.kontrol()["durum"] == "donma"
    b._olaylari_uygula()                                    # motor çözüldü, bir sonraki kapanışta olayları okur
    assert b.durum[k1.ad].adet == {} and k1.ad in b.durdurulan
    assert all(abs(v) < 1e-9 for v in s1.poz.values())       # sandbox deftere eşitlendi (toparlanma)
    assert s1.gonderilen[-1][2] == "toparlanma"
    with m.connect() as c:
        assert c.execute(select(paper_kol_olay.c.ayrinti)).scalar()["neden"] == NEDEN
