"""A3: SEC 8-K toplayıcısı (ağ sahte) ve rol arayüzü."""
import json

from sqlalchemy import create_engine, select

from tradebot.db import metadata, metin
from tradebot.metin import sec
from tradebot.veri.depo import HamDepo
from tradebot.zeka import a3_sec as a3

SUB = {"name": "Activision Blizzard, Inc.", "filings": {"recent": {
    "form": ["8-K", "10-Q", "8-K"], "acceptanceDateTime": ["2022-01-19T12:00:32.000Z", "2022-01-20T12:00:00.000Z",
                                                          "2022-01-21T21:05:00.000Z"],
    "items": ["1.01,5.03,9.01", "", "5.02,9.01"], "accessionNumber": ["0001-22-1", "0001-22-2", "0001-22-3"],
    "primaryDocument": ["a8k.htm", "q.htm", "b8k.htm"], "filingDate": ["2022-01-19", "2022-01-20", "2022-01-21"]}}}
BASLIK = b"&lt;TYPE&gt;EX-99.1\n&lt;SEQUENCE&gt;2\n&lt;FILENAME&gt;pr_merger.htm\n"


class SahteHttp:
    def __init__(self):
        self.istenen = []

    def al(self, url, params=None):
        self.istenen.append(url)
        if url == sec.TICKER_URL:
            return json.dumps({"0": {"cik_str": 718877, "ticker": "ATVI"}}).encode()
        if "submissions" in url:
            return json.dumps(SUB).encode()
        if url.endswith("index-headers.html"):
            return BASLIK
        if url.endswith("pr_merger.htm"):
            return b"<p>Microsoft to acquire <b>Activision Blizzard</b> for $95.00 per share</p>"
        return b"<html><script>x</script><p>Item 1.01 Entry into a Material Definitive Agreement</p></html>"


def test_toplayici_rutin_atlar_ek99_ekler_tekrar_yazmaz(tmp_path):
    m = create_engine(f"sqlite:///{tmp_path / 's.db'}")
    metadata.create_all(m)
    http = SahteHttp()
    s = sec.Sec8K(HamDepo(tmp_path, m), m, http, uyeler=lambda: ["NASDAQ:ATVI"])
    yeni = s._kaydet("NASDAQ:ATVI", 718877, SUB, 0)
    assert len(yeni) == 2                                          # 10-Q değil, iki 8-K
    with m.connect() as b:
        r = {x.dis_kimlik: x for x in b.execute(select(metin))}
    birlesme, yonetici = r["0001-22-1"], r["0001-22-3"]
    assert not birlesme.meta["atla"] and "EXHIBIT 99" in birlesme.govde and "$95.00" in birlesme.govde
    assert "script" not in birlesme.govde and "Item 1.01" in birlesme.baslik
    assert yonetici.meta["atla"] and yonetici.govde == ""          # yalnız 5.02/9.01: modele sorulmaz, belge inmez
    assert birlesme.yayin_ms == sec.ms("2022-01-19T12:00:32.000Z") and birlesme.ham_sha
    assert s._kaydet("NASDAQ:ATVI", 718877, SUB, 0) == []          # aynı başvuru ikinci kez yazılmaz


def test_canli_sirayla_yoklar(tmp_path):
    m = create_engine(f"sqlite:///{tmp_path / 's.db'}")
    metadata.create_all(m)
    http = SahteHttp()
    s = sec.Sec8K(HamDepo(tmp_path, m), m, http, uyeler=lambda: ["NASDAQ:ATVI", "NASDAQ:YOK"])
    s.canli({"sec": {"sira": 1}})
    assert sum("submissions" in u for u in http.istenen) == 1     # yalnız CIK'i bilinen üye


def test_rol_hedef_ve_durum():
    class M:
        meta = {"kodlar": ["ATVI"], "atla": False, "kalemler": ["1.01"], "sirket": "Activision"}
        baslik, govde = "Activision 8-K: Item 1.01", "metin"

    assert a3.hedefler(M, {"NASDAQ:ATVI"}) == ["NASDAQ:ATVI"]
    assert a3.hedefler(M, set()) == []
    st = a3.hedef_state(M, "NASDAQ:ATVI")
    assert st["sembol"] == "ATVI" and st["bildirim"]["kalemler"] == ["1.01"]
    assert a3.veto_suresi_ms("accounting_problem", {"sec": {"veto_gun": {"accounting_problem": 30}}}) == 30 * 86_400_000
    assert a3.veto_suresi_ms("bankruptcy_or_delisting", {"sec": {"veto_gun": {}}}) is None   # kalıcı
    assert set(a3.ETKI.criteria) >= a3.VETO
