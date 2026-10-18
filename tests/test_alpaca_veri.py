"""Alpaca veri indiricisi: sayfa çözme, sayfalama + ham kayıt, üyelik dönemi sorguları (asof)."""
import json
from datetime import UTC, datetime

import httpx
from sqlalchemy import create_engine

from tradebot.db import metadata
from tradebot.veri import alpaca_veri as av
from tradebot.veri.depo import BarDepo, HamDepo


def _ms(s):
    return int(datetime.fromisoformat(s).replace(tzinfo=UTC).timestamp() * 1000)


def _sayfa(sembol, ts, tok=None):
    return json.dumps({"bars": {sembol: [{"t": t, "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 10} for t in ts]},
                       "next_page_token": tok}).encode()


def test_gunluk_bar_seans_gunune_etiketlenir():
    df = av.sayfa_coz(_sayfa("ATVI", ["2023-10-02T04:00:00Z", "2016-01-04T05:00:00Z"]), "ATVI", "1d")
    assert df["acilis_ms"].to_list() == [_ms("2016-01-04"), _ms("2023-10-02")]
    assert (df["adj_close"] == df["close"]).all()


def test_sayfalama_ve_ham_kayit(tmp_path):
    m = create_engine(f"sqlite:///{tmp_path / 'a.db'}")
    metadata.create_all(m)
    sayfalar = [_sayfa("X", ["2016-01-04T05:00:00Z"], "tok1"), _sayfa("X", ["2016-01-05T05:00:00Z"])]
    istenen = []

    def isle(req):
        istenen.append(dict(req.url.params))
        return httpx.Response(200, content=sayfalar[len(istenen) - 1])

    v = av.AlpacaVeri("k", "g", HamDepo(tmp_path, m), BarDepo(tmp_path / "alpaca"), aralik_sn=0,
                      istemci=httpx.Client(transport=httpx.MockTransport(isle)))
    df = v.bars("X", "1d", _ms("2016-01-01"), _ms("2016-02-01"), asof="2020-01-02")
    assert len(df) == 2 and istenen[1]["page_token"] == "tok1" and istenen[0]["asof"] == "2020-01-02"
    assert istenen[0]["adjustment"] == "all" and istenen[0]["feed"] == "sip"
    assert len(HamDepo(tmp_path, m).dosyalar("alpaca")) == 2


def test_sorgular_eski_sembol_ve_asof():
    y2020 = b"---\nyear: 2020\ntickers_on_Jan_1:\n  - FB\n  - ATVI\nchanges:\n  '2021-06-09':\n    difference:\n      - FB\n" \
            b"    union:\n      - META\n  '2023-10-13':\n    difference:\n      - ATVI\n"
    q = av.sorgular({"sembol_esleme": {"FB": "META"}}, {2020: y2020}, _ms("2026-10-16"))
    d = {(k, s): (asof, bit) for k, s, asof, bit in q}
    assert d[("NASDAQ:META", "FB")][0] == "2021-06-08"           # FB, kendi döneminin son günüyle sorgulanır
    assert d[("NASDAQ:ATVI", "ATVI")] == ("2023-10-12", _ms("2023-10-18"))
    assert ("NASDAQ:META", "META") in d
