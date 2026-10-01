"""Faz 12 gerçek yürütme: Binance USDⓈ-M istemcisi (sahte HTTP), gerçek kol ayarları, gözetmenin Binance kapatması."""
import hashlib
import hmac
from urllib.parse import parse_qsl, urlsplit

import httpx
import pytest
from sqlalchemy import create_engine, func, select

from tradebot.canli import kilit as kd
from tradebot.canli.binance_emir import BorsaHatasi, VadeliIstemci, miktar_metni
from tradebot.canli.gozetmen import Gozetmen
from tradebot.canli.kollar import oku
from tradebot.db import metadata, paper_emir_olay, paper_kol_olay, paper_ozkaynak


class SahteBinance:
    def __init__(self, gizli="g"):
        self.gizli, self.istekler, self.emirler = gizli, [], {}
        self.poz = {"MOVEUSDT": -100.0}
        self.dual = False
        self.kisit = {"enableWithdrawals": False, "ipRestrict": True}
        self.gelir = [{"incomeType": "FUNDING_FEE", "income": "0.5", "symbol": "MOVEUSDT", "time": 1000 + i,
                       "tranId": i, "asset": "USDT"} for i in range(1500)]

    def __call__(self, req: httpx.Request) -> httpx.Response:
        u = urlsplit(str(req.url))
        q = dict(parse_qsl(u.query))
        imzasiz = u.query.rsplit("&signature=", 1)[0]
        assert q["signature"] == hmac.new(self.gizli.encode(), imzasiz.encode(), hashlib.sha256).hexdigest()
        assert req.headers["X-MBX-APIKEY"] == "a"
        self.istekler.append((req.method, u.netloc, u.path, q))
        yol = u.path
        if yol == "/fapi/v1/order" and req.method == "POST":
            if q["newClientOrderId"] in self.emirler:
                return httpx.Response(400, json={"code": -4116, "msg": "clientOrderId is duplicated"})
            qty = float(q["quantity"]) * (1 if q["side"] == "BUY" else -1)
            self.emirler[q["newClientOrderId"]] = {"orderId": len(self.emirler) + 1, "status": "FILLED",
                                                   "executedQty": q["quantity"], "avgPrice": "1.25"}
            self.poz[q["symbol"]] = self.poz.get(q["symbol"], 0.0) + qty
            return httpx.Response(200, json=self.emirler[q["newClientOrderId"]])
        if yol == "/fapi/v1/order":
            return httpx.Response(200, json=self.emirler[q["origClientOrderId"]])
        if yol == "/fapi/v3/positionRisk":
            return httpx.Response(200, json=[{"symbol": s, "positionAmt": str(v)} for s, v in self.poz.items()])
        if yol == "/fapi/v3/account":
            return httpx.Response(200, json={"totalMarginBalance": "1000.5"})
        if yol == "/fapi/v1/income":
            bas = int(q["startTime"])
            r = [x for x in self.gelir if x["time"] >= bas][: int(q["limit"])]
            return httpx.Response(200, json=r)
        if yol == "/fapi/v1/marginType":
            return httpx.Response(400, json={"code": -4046, "msg": "No need to change margin type."})
        if yol == "/fapi/v1/leverage":
            return httpx.Response(200, json={"leverage": 2})
        if yol == "/fapi/v1/positionSide/dual":
            return httpx.Response(200, json={"dualSidePosition": self.dual})
        if yol == "/sapi/v1/account/apiRestrictions":
            return httpx.Response(200, json=self.kisit)
        return httpx.Response(404, json={"code": -1, "msg": "yok"})


def _ist(sahte, ortam="demo"):
    return VadeliIstemci(ortam, "a", "g", http=httpx.Client(transport=httpx.MockTransport(sahte)), saat=lambda: 1_790_000_000)


def test_miktar_metni():
    assert miktar_metni(0.1 + 0.2) == "0.3" and miktar_metni(-12.0) == "12" and miktar_metni(0.001) == "0.001"


def test_emir_imzali_ve_tekrarda_sorgular():
    s = SahteBinance()
    ist = _ist(s)
    r = ist.emir("MOVEUSDT", 100.0, "KG1-MOVE-1-KT", True)
    assert r == {"adet": 100.0, "fiyat": 1.25, "durum": "FILLED", "emir_id": 1}
    post = [q for m, _, y, q in s.istekler if y == "/fapi/v1/order" and m == "POST"][0]
    assert post["reduceOnly"] == "true" and post["type"] == "MARKET" and post["newOrderRespType"] == "RESULT"
    assert ist.pozisyonlar() == {}                                     # kapandı (0 adet filtrelenir)
    r2 = ist.emir("MOVEUSDT", 100.0, "KG1-MOVE-1-KT", True)            # aynı kimlik: −4116 → sorgu, çift emir yok
    assert r2["adet"] == 100.0 and ist.pozisyonlar() == {}
    ist.emir("CARVUSDT", -50.0, "KG2-CARV-2-AT", False)                # açılış: önce marjin tipi (zararsız) + kaldıraç
    yollar = [y for _, _, y, _ in s.istekler]
    assert "/fapi/v1/marginType" in yollar and "/fapi/v1/leverage" in yollar
    assert all(n == "demo-fapi.binance.com" for _, n, _, _ in s.istekler)


def test_gelir_sayfali_ve_tekil_kimlik():
    s = SahteBinance()
    g = _ist(s).gelir(0)
    assert len(g) == 1500 and g[0]["tranId"] == "FUNDING_FEE:0" and g[0]["gelir"] == 0.5


def test_dogrula_hedge_modu_ve_ana_ag_kisitlari():
    s = SahteBinance()
    assert _ist(s).dogrula()["ozkaynak"] == 1000.5                     # demo: apiRestrictions sorulmaz
    assert not any(y == "/sapi/v1/account/apiRestrictions" for _, _, y, _ in s.istekler)
    assert _ist(s, "ana").dogrula()["kisit"] == {"enableWithdrawals": False, "ipRestrict": True}
    assert any(n == "api.binance.com" for _, n, _, _ in s.istekler)
    s.kisit = {"enableWithdrawals": True, "ipRestrict": True}
    with pytest.raises(RuntimeError, match="çekim"):
        _ist(s, "ana").dogrula()
    s.kisit = {"enableWithdrawals": False, "ipRestrict": False}
    with pytest.raises(RuntimeError, match="IP"):
        _ist(s, "ana").dogrula()
    s.dual = True
    with pytest.raises(RuntimeError, match="hedge"):
        _ist(s).dogrula()


def test_borsa_hatasi_yukselir():
    def h(req):
        return httpx.Response(400, json={"code": -2019, "msg": "Margin is insufficient."})
    ist = VadeliIstemci("demo", "a", "g", http=httpx.Client(transport=httpx.MockTransport(h)))
    with pytest.raises(BorsaHatasi) as e:
        ist.emir("MOVEUSDT", -1.0, "x", True)
    assert e.value.kod == -2019


def test_gercek_kol_ayarlari_tavan_ve_onay():
    d = oku()
    d = d | {"kilit_gercek": {"ad": "d6b:kilit_kisa@kilit_perp@1d#gercek", "ortam": "demo", "sermaye": 1000}}
    ay = kd.ayarlar(d, blok="kilit_gercek")
    assert ay.kol.ad.endswith("#gercek") and ay.kol.baslangic_ozkaynak == 1000 and ay.kol.grup["dugum"] == "kilit_gercek"
    assert ay.kural == kd.ayarlar(d).kural                              # kural paper koluyla aynı
    with pytest.raises(ValueError, match="tavan"):
        kd.ayarlar(d | {"kilit_gercek": d["kilit_gercek"] | {"sermaye": 5000}}, blok="kilit_gercek")
    with pytest.raises(ValueError, match="onay"):
        kd.ayarlar(d | {"kilit_gercek": d["kilit_gercek"] | {"ortam": "ana"}}, blok="kilit_gercek")
    ana = kd.ayarlar(d | {"kilit_gercek": d["kilit_gercek"] | {"ortam": "ana", "onay": "Scryne 2026-11-01"}},
                     blok="kilit_gercek")
    assert ana.gercek["ortam"] == "ana"


def test_gozetmen_gercek_kolu_binance_te_kapatir_ve_deftere_yazar(tmp_path):
    m = create_engine(f"sqlite:///{tmp_path / 'g.db'}")
    metadata.create_all(m)
    from tradebot.canli.defter import PaperDefter

    d = oku() | {"kilit_gercek": {"ad": "k#gercek", "ortam": "demo", "sermaye": 1000}}
    ay = kd.ayarlar(d, blok="kilit_gercek")
    defter = PaperDefter(m, "t")
    defter.kol_ac(ay.kol, 0)
    defter.olay_yaz(0, ay.kol.ad, "dolum", "BINANCEF:MOVEUSDT", -100.0, 1.0, 0.0, 10, {})
    with m.begin() as b:
        b.execute(paper_ozkaynak.insert().values(kol=ay.kol.ad, zaman_ms=0, ozkaynak=1000, nakit=1000, pozisyon={},
                                                 fiyat={}))
    s = SahteBinance()
    g = Gozetmen(m, lambda k: {}, dugum="kilit_gercek", binance=_ist(s), saat=lambda: 10 * 3600, onay_tur=1,
                 isinma_sn=0)
    r = g.kontrol()
    assert r["durum"] == "donma" and s.poz["MOVEUSDT"] == 0
    with m.connect() as b:
        assert b.execute(select(func.sum(paper_emir_olay.c.miktar)).where(paper_emir_olay.c.kol == ay.kol.ad)).scalar() == 0
        assert b.execute(select(paper_kol_olay.c.tur).where(paper_kol_olay.c.kol == ay.kol.ad)).scalar() == "durdur"
    g2 = Gozetmen(m, lambda k: {}, dugum="kilit_gercek", binance=None, saat=lambda: 20 * 3600, onay_tur=1, isinma_sn=0)
    with m.begin() as b:
        b.execute(paper_kol_olay.delete())
    with pytest.raises(RuntimeError, match="Binance istemcisi yok"):
        g2.kontrol()
