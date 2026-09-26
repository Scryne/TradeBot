"""Faz 6: zekâ katmanı (ağ ve model çağrıları sahte)."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import func, insert, select

from tradebot.db import enstruman, jev_yargi, metadata, metin, motor, olay
from tradebot.metin.binance_duyuru import BinanceDuyuru, govde_metni
from tradebot.veri.depo import HamDepo
from tradebot.zeka import a1_binance as a1
from tradebot.zeka import olay as ol
from tradebot.zeka.jev import JevIstemci, donmus, soru_sha
from tradebot.zeka.servis import Zeka
from tradebot.zeka.yukseltme import Yukseltme, coz

KOK = Path(__file__).resolve().parents[1]


@pytest.fixture
def m(ayar):
    e = motor(ayar)
    metadata.create_all(e)
    return e


# ------------------------------------------------------------------ toplayıcı
def _govde(*paragraflar):
    return json.dumps({"node": "root", "child": [
        {"node": "element", "tag": "p", "child": [{"node": "text", "text": p}]} for p in paragraflar]})


def test_govde_metni():
    assert govde_metni(_govde("Binance will delist  ICX.", "Trading ends on 2026-09-03.")) == \
        "Binance will delist ICX.\nTrading ends on 2026-09-03."
    assert govde_metni("bozuk json{") == "bozuk json{"


class SahteHttp:
    def __init__(self, makaleler):
        self.makaleler, self.istenen = makaleler, []

    def al(self, url, params=None):
        self.istenen.append((url, dict(params or {})))
        if "list" in url:
            arts = [a for a in self.makaleler if a["katalog"] == params["catalogId"]]
            return json.dumps({"data": {"catalogs": [{"articles": [
                {"code": a["code"], "title": a["baslik"], "releaseDate": a["zaman"]} for a in arts]}]}}).encode()
        a = next(x for x in self.makaleler if x["code"] == params["articleCode"])
        return json.dumps({"data": {"title": a["baslik"], "body": _govde(a["govde"]), "publishDate": a["zaman"]}}).encode()


def test_toplayici_yeni_ve_tekrarsiz(m, ayar):
    http = SahteHttp([
        {"katalog": 161, "code": "c1", "baslik": "Binance Will Delist ICX on 2026-09-03", "govde": "Delist ICX.", "zaman": 1000},
        {"katalog": 49, "code": "c2", "baslik": "Binance Adds XYZ", "govde": "News.", "zaman": 2000},
    ])
    t = BinanceDuyuru(HamDepo(ayar.veri_dizini, m), m, http)
    ids = t.topla([161, 49])
    assert len(ids) == 2
    with m.connect() as b:
        r = b.execute(select(metin).where(metin.c.dis_kimlik == "c1")).one()
    assert r.yayin_ms == 1000 and r.katalog == "delist" and r.govde == "Delist ICX." and len(r.ham_sha) == 64
    detay = sum("detail" in u for u, _ in http.istenen)
    assert t.topla([161, 49]) == [] and sum("detail" in u for u, _ in http.istenen) == detay  # gövde yeniden istenmez


# ------------------------------------------------------------------ Jev istemcisi
class Cevap:
    def __init__(self, **d):
        self.d = d

    def model_dump(self, mode="json"):
        return self.d


class SahteJev:
    def __init__(self, cevaplar=None, hata=None):
        self.cevaplar, self.hata, self.cagri = cevaplar or {}, hata, 0

    def system_one(self, state, sorular, model=None):
        self.cagri += 1
        if self.hata:
            raise RuntimeError(self.hata)
        secim, guven, p = self.cevaplar.get(state["varlik"], ("not_about_asset", 0.95, {"not_about_asset": 0.95}))
        return SimpleNamespace(model="jev-1.13.0", usage=SimpleNamespace(input_tokens=1500), answers={
            "etki": Cevap(type="choice", choice=secim, confidence=guven, probabilities=p),
            "aciliyet": Cevap(type="score", score=1.0, confidence=0.9)})


def test_jev_kaydeder_ve_dondurur(m):
    j = JevIstemci(m, "jev-1.13.0", istemci=SahteJev({"ICX": ("token_delist", 0.97, {"token_delist": 0.97})}))
    st = a1.state("Delist ICX", "Binance will delist ICX.", "ICX")
    y = j.sor(a1.ROL, "metin:1|BINANCE:ICXUSDT", st, a1.SORULAR)
    assert y.secim("etki")[:2] == ("token_delist", 0.97) and y.model == "jev-1.13.0" and y.hata is None
    assert donmus(m, a1.SORULAR, st)["etki"]["choice"] == "token_delist"
    assert donmus(m, a1.SORULAR, a1.state("Delist ICX", "Binance will delist ICX.", "ETH")) is None
    h = JevIstemci(m, "jev-1.13.0", istemci=SahteJev(hata="Unknown model")).sor(a1.ROL, "x", st, a1.SORULAR)
    assert h.hata and h.secim("etki") == (None, 0.0, {})
    with m.connect() as b:
        assert b.execute(select(func.count()).select_from(jev_yargi)).scalar() == 2


def test_soru_tanimlari_spike04_ile_birebir():
    """A1 soruları Spike 04-A'da ölçülenle aynı olmalı (değişiklik = yeni rol sürümü + yeni ölçüm)."""
    yol = KOK / "research" / "spikes" / "04_jev" / "veto_binance.py"
    spec = importlib.util.spec_from_file_location("spike_veto_binance", yol)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert soru_sha(a1.SORULAR) == soru_sha({"etki": mod.ETKI, "aciliyet": mod.ACILIYET})
    assert a1.VETO == mod.VETO


# ------------------------------------------------------------------ yükseltme
def test_coz_dusunme_ve_gecersiz():
    assert coz('<think>maybe {"etki": "token_delist"}</think> {"etki": "transfers_suspended"}', "etki",
               {"token_delist", "transfers_suspended"}) == "transfers_suspended"
    assert coz('{"etki": "uydurma"}', "etki", {"token_delist"}) is None
    assert coz("cevap yok", "etki", {"token_delist"}) is None


def test_yukseltme_yedek_zinciri(m):
    cagrilar = []

    def isle(req: httpx.Request):
        model = json.loads(req.content)["model"]
        cagrilar.append(model)
        if model == "a":
            return httpx.Response(500)
        if model == "b":
            return httpx.Response(200, json={"choices": [{"message": {"content": "bilmiyorum"}}]})
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"etki": "token_delist"}'}}]})

    y = Yukseltme(m, "https://x/v1", ["a", "b", "c"], "anahtar", http=httpx.Client(transport=httpx.MockTransport(isle)))
    secim, model = y.sec(a1.ROL, "h", a1.ETKI.model_dump(mode="json"), a1.state("t", "g", "ICX"))
    assert (secim, model) == ("token_delist", "c") and cagrilar == ["a", "b", "c"]
    with m.connect() as b:
        hatalar = list(b.execute(select(jev_yargi.c.model_istenen, jev_yargi.c.hata).where(jev_yargi.c.saglayici == "nvidia")))
    assert [h for _, h in hatalar][:2] != [None, None] and hatalar[-1][1] is None
    assert Yukseltme(m, "https://x/v1", [], "k").sec(a1.ROL, "h", {}, {}) == (None, None)  # model yok → hazır değil


def test_yukseltme_429_bekler_ve_tekrar_dener(m):
    sayac = {"n": 0}

    def isle(req: httpx.Request):
        sayac["n"] += 1
        if sayac["n"] < 3:
            return httpx.Response(429)
        return httpx.Response(200, json={"choices": [{"message": {"content": '{"etki": "token_delist"}'}}]})

    y = Yukseltme(m, "https://x/v1", ["a"], "k", http=httpx.Client(transport=httpx.MockTransport(isle)), hiz_bekleme=(0, 0))
    assert y.sec(a1.ROL, "h", a1.ETKI.model_dump(mode="json"), a1.state("t", "g", "ICX")) == ("token_delist", "a")
    sayac["n"] = -10  # hep 429: bekleme tükenince sıradaki modele (yok) → None
    assert y.sec(a1.ROL, "h", a1.ETKI.model_dump(mode="json"), a1.state("t", "g", "ICX")) == (None, None)


# ------------------------------------------------------------------ A1 karar kuralı
@pytest.mark.parametrize("secim,guven,p,yuk,denendi,veto,on_ek", [
    ("token_delist", 0.97, {}, None, False, True, "jev"),
    ("other_pairs_or_products_removed", 0.95, {}, None, False, False, "jev"),
    ("positive_or_neutral", 0.40, {}, "token_conversion", True, True, "yukseltme"),
    ("token_delist", 0.40, {}, "other_pairs_or_products_removed", True, False, "yukseltme"),
    ("other_pairs_or_products_removed", 0.40, {"other_pairs_or_products_removed": 0.4, "token_delist": 0.35,
                                               "not_about_asset": 0.25}, None, True, True, "belirsiz"),
    ("positive_or_neutral", 0.45, {"positive_or_neutral": 0.45, "not_about_asset": 0.4, "token_delist": 0.15},
     None, False, False, "belirsiz"),
    (None, 0.0, {}, None, True, False, "belirsiz"),  # Jev hatası, yükseltme de yok: olasılık yok → veto yok, uyarı var
])
def test_a1_karar(secim, guven, p, yuk, denendi, veto, on_ek):
    v, neden = a1.karar(secim, guven, p, yuk, denendi)
    assert v is veto and neden.startswith(on_ek)


def test_a1_adaylar():
    bazlar = {"ICX", "SCRT", "STORJ", "BTC", "ETH", "BNB"}
    assert a1.adaylar("Binance Will Delist ICX, SCRT, STORJ on 2026-09-03",
                      "ICX/USDT, SCRT/BTC and STORJ/USDT will be removed. BNB fees. ICX again. Ice", bazlar) == \
        ["ICX", "SCRT", "STORJ", "BTC", "BNB"]  # BTC "SCRT/BTC" çiftinde geçiyor: aday; etkiyi Jev ayırır


# ------------------------------------------------------------------ servis uçtan uca + point-in-time veto
def test_zeka_turu_veto_ve_pit(m, ayar):
    with m.begin() as b:
        for s in ("ICX", "SCRT", "BTC"):
            b.execute(insert(enstruman).values(kimlik=f"BINANCE:{s}USDT", piyasa="BINANCE", sembol=f"{s}USDT", sinif="kripto",
                                               takvim="kripto_7x24", para_birimi="USDT", kaynak="binance", durum="aktif",
                                               meta={}, guncellendi=__import__("datetime").datetime.now()))
    yayin = 1_700_000_000_000
    http = SahteHttp([{"katalog": 161, "code": "d1", "baslik": "Binance Will Delist ICX, SCRT",
                       "govde": "ICX and SCRT spot pairs will be removed. BTC fees unchanged.", "zaman": yayin}])
    jev = SahteJev({"ICX": ("token_delist", 0.97, {"token_delist": 0.97}),
                    "SCRT": ("positive_or_neutral", 0.42, {"positive_or_neutral": 0.42, "token_delist": 0.40,
                                                           "not_about_asset": 0.18})})
    z = Zeka(m, JevIstemci(m, "jev-1.13.0", istemci=jev), Yukseltme(m, "u", [], None),
             BinanceDuyuru(HamDepo(ayar.veri_dizini, m), m, http),
             {"jev": {"esik": 0.5}, "binance": {"kataloglar": [161]}})
    r = z.tur()
    assert r["yeni_metin"] == 1 and jev.cagri == 3  # ICX, SCRT, BTC
    gecerli = yayin + ol.GERIYE_DONUK_GECIKME_MS  # geçmiş duyuru → yayın + gecikme
    assert ol.aktif_vetolar(m, gecerli - 1) == set()  # yayından önce veto görünmez (point-in-time)
    assert ol.aktif_vetolar(m, gecerli) == {"BINANCE:ICXUSDT", "BINANCE:SCRTUSDT"}  # SCRT: belirsiz → riski azalt
    with m.connect() as b:
        uyari = b.execute(select(olay.c.enstruman).where(olay.c.tur == "uyari")).scalars().all()
    assert uyari == ["BINANCE:SCRTUSDT"]
    z.tur()
    assert jev.cagri == 3  # aynı (metin, varlık) tekrar sorulmaz
    ol.yaz(m, "veto", "BINANCE:BTCUSDT", 10, "süreli", "test", bitis_ms=20)
    assert "BINANCE:BTCUSDT" in ol.aktif_vetolar(m, 15) and "BINANCE:BTCUSDT" not in ol.aktif_vetolar(m, 20)


def test_belirsizleri_yukselt_yalniz_veto_ekler(m, ayar):
    with m.begin() as b:
        for s in ("AAA", "BBB", "CCC"):
            b.execute(insert(enstruman).values(kimlik=f"BINANCE:{s}USDT", piyasa="BINANCE", sembol=f"{s}USDT", sinif="kripto",
                                               takvim="kripto_7x24", para_birimi="USDT", kaynak="binance", durum="aktif",
                                               meta={}, guncellendi=__import__("datetime").datetime.now()))
    yayin = 1_700_000_000_000
    http = SahteHttp([{"katalog": 161, "code": "d1", "baslik": "Notice AAA BBB CCC", "govde": "AAA BBB CCC.", "zaman": yayin}])
    belirsiz = {"not_about_asset": 0.45, "positive_or_neutral": 0.40, "token_delist": 0.15}
    jev = SahteJev({"AAA": ("token_delist", 0.45, {"token_delist": 0.45, "not_about_asset": 0.40}),  # belirsiz → veto
                    "BBB": ("not_about_asset", 0.45, belirsiz),                                     # belirsiz, veto yok
                    "CCC": ("not_about_asset", 0.45, belirsiz)})
    yuk_cevap = {"AAA": "not_about_asset", "BBB": "usdt_pair_removed", "CCC": "positive_or_neutral"}

    def isle(req: httpx.Request):
        istem = json.loads(req.content)["messages"][1]["content"]
        varlik = next(v for v in yuk_cevap if f'"varlik": "{v}"' in istem)
        return httpx.Response(200, json={"choices": [{"message": {"content": json.dumps({"etki": yuk_cevap[varlik]})}}]})

    top = BinanceDuyuru(HamDepo(ayar.veri_dizini, m), m, http)
    ayar_z = {"jev": {"esik": 0.5}, "binance": {"kataloglar": [161]}}
    z = Zeka(m, JevIstemci(m, "jev-1.13.0", istemci=jev), Yukseltme(m, "u", [], None), top, ayar_z)
    z.tur()
    gecerli = yayin + ol.GERIYE_DONUK_GECIKME_MS
    assert ol.aktif_vetolar(m, gecerli) == {"BINANCE:AAAUSDT"}
    assert z.belirsizleri_yukselt() == {"hazir": False}

    y = Yukseltme(m, "https://x/v1", ["c"], "k", http=httpx.Client(transport=httpx.MockTransport(isle)))
    z2 = Zeka(m, JevIstemci(m, "jev-1.13.0", istemci=jev), y, top, ayar_z)
    r = z2.belirsizleri_yukselt()
    assert r == {"hazir": True, "yukseltildi": 3, "yeni_veto": 1, "korunan_veto": 1, "basarisiz": 0}
    assert ol.aktif_vetolar(m, gecerli - 1) == set()  # yeni veto da point-in-time: uyarının anında
    assert ol.aktif_vetolar(m, gecerli) == {"BINANCE:AAAUSDT", "BINANCE:BBBUSDT"}  # AAA kaldırılmadı
    assert z2.belirsizleri_yukselt()["yukseltildi"] == 0  # tekrar sorulmaz


def test_veto_kaldirma_onayli_ve_pit(m):
    v = ol.yaz(m, "veto", "BINANCE:ADAUSDT", 100, "A1 belirsiz", a1.ROL)
    w = ol.yaz(m, "veto", "BINANCE:INJUSDT", 100, "A1 belirsiz", a1.ROL)
    with pytest.raises(ValueError):
        ol.kaldir(m, v, 100, "yanlış", onay=" ")  # onaysız olmaz
    with pytest.raises(ValueError):
        ol.kaldir(m, 999, 100, "yok", onay="Scryne")
    ol.kaldir(m, v, 100, "yalnız ADA/TUSD", onay="Scryne 2026-09-26")  # geriye dönük: hiç görünmez
    ol.kaldir(m, w, 150, "yalnız INJ/TUSD", onay="Scryne 2026-09-26")  # 150'den itibaren
    assert ol.aktif_vetolar(m, 120) == {"BINANCE:INJUSDT"} and ol.aktif_vetolar(m, 150) == set()
    assert sorted(ol.tum_vetolar(m)) == [("BINANCE:ADAUSDT", 100, 100), ("BINANCE:INJUSDT", 100, 150)]


def test_toplayici_tek_duyuru_hatasinda_durmaz(m, ayar):
    http = SahteHttp([
        {"katalog": 161, "code": "iyi", "baslik": "A", "govde": "a", "zaman": 1},
        {"katalog": 161, "code": "kotu", "baslik": "B", "govde": "b", "zaman": 2},
    ])
    asil = http.al

    def al(url, params=None):
        if params and params.get("articleCode") == "kotu":
            raise RuntimeError("429")
        return asil(url, params)

    http.al = al
    t = BinanceDuyuru(HamDepo(ayar.veri_dizini, m), m, http)
    assert len(t.topla([161])) == 1  # kötü atlandı, iyi yazıldı
    http.al = asil
    assert len(t.topla([161])) == 1  # sonraki turda kötü de gelir
