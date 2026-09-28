"""Faz 6: RSS/Atom toplayıcısı (ağ sahte)."""
from sqlalchemy import select

from tradebot.db import metadata, metin, motor
from tradebot.metin import rss
from tradebot.veri.depo import HamDepo
from tradebot.zeka.servis import Zeka

RSS = b"""<?xml version="1.0"?><rss version="2.0" xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>
<item><title>FOMC statement</title><link>https://fed/a</link><guid>https://fed/a</guid>
<pubDate>Wed, 16 Sep 2026 14:00:00 -0400</pubDate><description>short</description></item>
<item><title>Zamansiz</title><link>https://fed/b</link><guid>https://fed/b</guid></item>
<item><title>Haber</title><link>https://x/c</link><guid>c-1</guid><pubDate>Sat, 26 Sep 2026 13:21:12 +0000</pubDate>
<content:encoded><![CDATA[<p>Bitcoin <b>ETF</b></p><p>ikinci</p>]]></content:encoded></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom">
<entry><id>tag:a,1</id><title>Karar</title><link href="https://ecb/x"/><published>2026-09-24T14:00:00+02:00</published>
<updated>2026-09-25T09:00:00+02:00</updated><summary>ozet</summary></entry></feed>"""

SAYFA = b"<html><nav><p>Menu</p></nav><div id=\"article\"><p>The Committee decided to raise.</p><p>x</p></div>" \
        b"<footer><p>Adres</p></footer></html>"


class SahteHttp:
    def __init__(self, yanitlar):
        self.yanitlar, self.istenen = yanitlar, []

    def al(self, url, params=None):
        self.istenen.append(url)
        return self.yanitlar[url]


def test_ogeler_rss_ve_atom():
    o = rss.ogeler(RSS)
    assert [x["kimlik"] for x in o] == ["https://fed/a", "https://fed/b", "c-1"]
    assert o[0]["yayin_ms"] == 1789581600000  # 14:00 EDT = 18:00 UTC
    assert o[1]["yayin_ms"] is None
    assert o[2]["govde"] == "Bitcoin ETF\nikinci"  # content:encoded, description'dan önce
    a = rss.ogeler(ATOM)[0]
    assert a["link"] == "https://ecb/x" and a["yayin_ms"] == rss.zaman_ms("2026-09-24T12:00:00+00:00")  # published
    assert rss.zaman_ms("2026-09-24T12:00:00") is None  # saat dilimsiz: belirsiz


def test_bolge_ve_paragraflar():
    h = SAYFA.decode()
    assert rss.paragraflar(rss.bolge(h, ['id="article"', "<footer"])) == "The Committee decided to raise."
    assert "Menu" in rss.paragraflar(rss.bolge(h, ["yok", "<footer"]))  # işaret yoksa baştan


def test_toplayici_sayfa_zamansiz_ve_tekrarsiz(ayar):
    m = motor(ayar)
    metadata.create_all(m)
    http = SahteHttp({"https://fed/rss": RSS, "https://fed/a": SAYFA, "https://x/c": b"<p>indirilmemeli</p>"})
    akis = {"ad": "fed", "url": "https://fed/rss", "katalog": "merkez_bankasi", "sayfa": True,
            "bolge": ['id="article"', "<footer"]}
    t = rss.RssToplayici(HamDepo(ayar.veri_dizini, m), m, [akis], http)
    assert len(t.akis_topla(akis)) == 2  # zamansız öğe atlandı
    with m.connect() as b:
        r = {x.dis_kimlik: x for x in b.execute(select(metin).where(metin.c.kaynak == "rss:fed"))}
    assert r["https://fed/a"].govde == "The Committee decided to raise." and r["c-1"].meta == {"link": "https://x/c"}
    assert t.akis_topla(akis) == [] and http.istenen.count("https://fed/a") == 1


def test_rolsuz_kaynak_servis_turunu_bozmaz(ayar):
    m = motor(ayar)
    metadata.create_all(m)
    http = SahteHttp({"https://fed/rss": RSS, "https://fed/a": SAYFA})
    t = rss.RssToplayici(HamDepo(ayar.veri_dizini, m), m, [{"ad": "fed", "url": "https://fed/rss"}], http)
    z = Zeka(m, None, None, [t], {"jev": {"esik": 0.5}})
    assert z.tur() == {"yeni_metin": 2, "olay": 0, "basarili": {"rss"}}
    assert z.tur() == {"yeni_metin": 0, "olay": 0, "basarili": {"rss"}}  # aralık dolmadı: akış yeniden istenmez
    assert http.istenen.count("https://fed/rss") == 1
