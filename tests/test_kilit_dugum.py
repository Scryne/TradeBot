"""Kilit kolu paper düğümü (canli/kilit.py): günlük karar, tavan, bacak eşitliği, funding, durdurma, yeniden başlatma."""
import json
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, func, insert, select

from tradebot.canli import kilit as kd
from tradebot.canli.defter import PaperDefter
from tradebot.canli.gozetmen import Gozetmen, dugum_kollari, son_isaret_ms
from tradebot.db import metadata, paper_emir, paper_emir_olay, paper_karar, paper_kol, paper_ozkaynak

G = 86_400_000
S = 3_600_000
D0 = 1_790_640_000_000 // G * G          # bir UTC günü başı
TOKENLER = ["AAA", "BBB", "CCC", "DDD", "EEE", "FFF"]   # 6 olay, tavan 5 (BTC ≤ 0,5 / 0,1)


class Saat:
    def __init__(self, ms):
        self.ms = ms

    def __call__(self):
        return self.ms / 1000


def _sayfa(gun_ms: int, semboller) -> bytes:
    veri = {"props": {"pageProps": {"data": [
        {"tSymbol": s, "gecko_id": s.lower(), "name": s, "maxSupply": 1000.0, "events": [
            {"unlockType": "cliff", "timestamp": gun_ms // 1000 + 3600, "category": "insiders", "noOfTokens": [50]}]}
        for s in semboller]}}}
    return f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(veri)}</script>'.encode()


class SahteBorsa:
    def __init__(self):
        self.perp = {s: {"sembol": f"{s}USDT", "durum": "TRADING", "adim": 0.001, "asgari_notional": 5.0}
                     for s in TOKENLER}
        self.perp["ZZZ"] = {"sembol": "ZZZUSDT", "durum": "SETTLING", "adim": 1.0, "asgari_notional": 5.0}
        self.perp["BTC"] = {"sembol": "BTCUSDT", "durum": "TRADING", "adim": 0.001, "asgari_notional": 100.0}
        self.fiyat = {v["sembol"]: 10.0 for v in self.perp.values()} | {"BTCUSDT": 80_000.0}
        self.fon: list[tuple[int, float, float]] = []
        self.takvim_hata = False
        self.sayfa = _sayfa(D0 + 7 * G, TOKENLER + ["ZZZ"])

    def perpler(self, kaydet=False):
        return self.perp

    def kotasyon(self):
        return {s: (p * 0.9999, p * 1.0001) for s, p in self.fiyat.items()}

    def isaret(self):
        return dict(self.fiyat)

    def gun_acilisi(self, sembol, gun_ms):
        return self.fiyat[sembol]

    def funding(self, sembol, bas_ms):
        return [(t, r, self.fiyat[sembol]) for t, r, _ in self.fon if t >= bas_ms]

    def takvim(self, gun_ms):
        if self.takvim_hata:
            raise ConnectionError("defillama yok")
        return self.sayfa, "sha-" + str(gun_ms)


@pytest.fixture()
def kur(tmp_path):
    m = create_engine(f"sqlite:///{tmp_path / 'k.db'}")
    metadata.create_all(m)
    saat = Saat(D0 + 60_000)
    borsa = SahteBorsa()
    d = kd.KilitDugumu(PaperDefter(m, "test"), kd.ayarlar(), borsa, saat=saat)
    d.ac()
    return m, d, saat, borsa


def _net(m, kol):
    with m.connect() as b:
        rows = b.execute(select(paper_emir_olay.c.enstruman, func.sum(paper_emir_olay.c.miktar))
                         .where(paper_emir_olay.c.kol == kol, paper_emir_olay.c.tur == "dolum")
                         .group_by(paper_emir_olay.c.enstruman)).all()
    return {k: float(q) for k, q in rows if abs(float(q)) > 1e-9}


def test_gunluk_karar_tavan_ve_piyasa_notr(kur):
    m, d, saat, borsa = kur
    assert "karar" not in d.tur()                        # 00:01: işaret var, karar 00:05'ten sonra
    saat.ms = D0 + 6 * 60_000
    r = d.tur()["karar"]
    assert r["ac"] == 5 and r["dolum"] == 10             # 5 olay × 2 bacak; 6. tavan, ZZZ işlem görmüyor
    net = _net(m, d.kol.ad)
    btc = net.pop("BINANCEF:BTCUSDT") * 80_000
    kisa = sum(q * 10.0 for q in net.values())
    assert btc == pytest.approx(-kisa, rel=0.02) and btc == pytest.approx(50_000, rel=0.02)   # BTC ≤ 0,5 × 100 bin
    with m.connect() as b:
        ayr = b.execute(select(paper_karar.c.ayrinti)).scalar()
    assert {x["neden"] for x in ayr["red"]} == {"tavan", "islem_gormuyor"} and ayr["takvim_sha"]
    assert d.tur() == {}                                 # aynı gün ikinci karar / çift emir yok
    with m.connect() as b:
        assert b.execute(select(func.count()).select_from(paper_karar)).scalar() == 1


def test_funding_kisa_alir_uzun_oder_ve_cikis_gunu_kapanir(kur):
    m, d, saat, borsa = kur
    saat.ms = D0 + 6 * 60_000
    d.tur()
    borsa.fon = [(D0 + 8 * S, 0.001, 0.0)]
    saat.ms = D0 + 9 * S + 30_000
    oz = d.tur()["isaret"]
    with m.connect() as b:
        fon = b.execute(select(paper_emir_olay.c.enstruman, paper_emir_olay.c.ucret)
                        .where(paper_emir_olay.c.tur == "fonlama")).all()
    ucret = {k: u for k, u in fon}
    assert ucret["BINANCEF:BTCUSDT"] > 0 and all(u < 0 for k, u in ucret.items() if "BTC" not in k)
    assert oz["fonlama"] == 6
    assert d.tur() == {}                                 # aynı funding ikinci kez yazılmaz
    saat.ms = D0 + 7 * G + 6 * 60_000                    # açılım günü: hepsi kapanır
    r = d.tur()["karar"]
    assert r["kapat"] == 5 and _net(m, d.kol.ad) == {}


def test_durdurma_saat_basinda_kapatir_yeni_olay_acmaz(kur):
    m, d, saat, borsa = kur
    saat.ms = D0 + 6 * 60_000
    d.tur()
    d.defter.kol_olay_yaz(d.kol.ad, "durdur", {"neden": "telegram"}, D0 + 20 * 60_000)
    saat.ms = D0 + S + 60_000
    r = d.tur()["isaret"]
    assert len(r["kapatilan"]) == 5 and _net(m, d.kol.ad) == {}


def test_planli_kapanis_yeni_olay_acmaz_aciki_saat_basinda_kapatir(kur):
    m, d, saat, borsa = kur
    borsa.perp["AAA"]["teslim_ms"] = D0 + 10 * G           # Binance AAA perp'in kaldırılacağını duyurdu
    saat.ms = D0 + 6 * 60_000
    r = d.tur()["karar"]
    assert r["ac"] == 5 and "BINANCEF:AAAUSDT" not in _net(m, d.kol.ad)   # AAA reddedildi, yeri FFF'ye kaldı
    with m.connect() as b:
        ayr = b.execute(select(paper_karar.c.ayrinti)).scalar()
    assert ayr["teslim_planli"] == ["AAA"] and {"AAA", "ZZZ"} == {x["sembol"] for x in ayr["red"]
                                                                   if x["neden"] == "islem_gormuyor"}
    borsa.perp["BBB"]["teslim_ms"] = D0 + 10 * G           # açık pozisyonun perp'i için duyuru
    saat.ms = D0 + S + 60_000
    r = d.tur()["isaret"]
    assert r["kapatilan"] == [("BBB", "teslim_planli")] and "BINANCEF:BBBUSDT" not in _net(m, d.kol.ad)
    assert len([k for k in _net(m, d.kol.ad) if "BTC" not in k]) == 4


def test_takvim_yoksa_bekler_sonra_yalniz_kapanis(kur):
    m, d, saat, borsa = kur
    borsa.takvim_hata = True
    saat.ms = D0 + 6 * 60_000
    assert "bekliyor" in d.tur()["karar"]
    saat.ms = D0 + 40 * 60_000
    r = d.tur()["karar"]
    assert r["ac"] == 0 and _net(m, d.kol.ad) == {}
    with m.connect() as b:
        assert b.execute(select(paper_karar.c.veri_hash)).scalar() == "takvim_yok"


def test_yeniden_baslatmada_eksik_emirler_tamamlanir(kur, monkeypatch):
    m, d, saat, borsa = kur
    saat.ms = D0 + 6 * 60_000
    gercek = d._yurut
    monkeypatch.setattr(d, "_yurut", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("çöktü")))
    with pytest.raises(RuntimeError):
        d.tur()                                          # karar yazıldı, emir yok
    monkeypatch.setattr(d, "_yurut", gercek)
    r = d.tur()
    assert r["devam"]["dolum"] == 10 and len(_net(m, d.kol.ad)) == 6
    assert d.tur() == {}


def test_btc_bacagi_reddedilirse_token_geri_alinir(kur):
    m, d, saat, borsa = kur
    borsa.perp["BTC"]["asgari_notional"] = 0.0
    borsa.fiyat["BTCUSDT"] = 1e9                         # lot adımına yuvarlanınca BTC miktarı 0
    saat.ms = D0 + 6 * 60_000
    d.tur()
    assert _net(m, d.kol.ad) == {}                       # tek bacak açıkta kalmaz
    with m.connect() as b:
        assert b.execute(select(func.count()).select_from(paper_emir).where(
            paper_emir.c.istemci_emir_id.like("%-GT"))).scalar() == 5


def test_gozetmen_dugum_basina_kalp_atisi(kur):
    m, d, saat, borsa = kur
    with m.begin() as b:   # Nautilus düğümünün kolu: 5 saat önce son işaret
        b.execute(insert(paper_kol).values(kol="ma_yon@x@1h", acilis=datetime.now(UTC),
                                           baslangic_ms=D0, baslangic_ozkaynak=1e5, sinif="B", tanim={}, kod_surumu="t"))
        b.execute(insert(paper_ozkaynak).values(kol="ma_yon@x@1h", zaman_ms=D0 - 5 * S, ozkaynak=1e5, nakit=1e5,
                                                pozisyon={}, fiyat={}))
    d.tur()                                              # kilit işareti: taze
    assert set(dugum_kollari(m)) == {"paper", "kilit"}
    assert son_isaret_ms(m, "paper") == D0 - 5 * S and son_isaret_ms(m, "kilit") == D0
    gp = Gozetmen(m, lambda k: {}, dugum="paper", saat=saat, onay_tur=1, isinma_sn=0)
    gk = Gozetmen(m, lambda k: {}, dugum="kilit", saat=saat, onay_tur=1, isinma_sn=0)
    assert gp.kontrol()["durum"] == "donma" and gk.kontrol()["durum"] == "canli"
