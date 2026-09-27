"""Bekçi (2026-09-27 denetimi): paper kalp atışı, gece işi, yedek yaşı, log triyajı, bildirim susturma."""
import json
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine

from tradebot import denetim, saglik
from tradebot.bildirim import Bildirici
from tradebot.canli.defter import PaperDefter
from tradebot.canli.karar import KolDurum
from tradebot.db import metadata

T = 1_790_000_000_000


def _db(ayar):
    m = create_engine(ayar.veritabani_url.get_secret_value())
    metadata.create_all(m)
    return m


def test_paper_kalp_atisi(ayar):
    m = _db(ayar)
    assert saglik.paper_kontrol(ayar, T).durum == "HATA"  # hiç işaret yok
    PaperDefter(m, "t").ozkaynak_yaz("k", T, KolDurum(ozkaynak=1.0, nakit=1.0), {})
    assert saglik.paper_kontrol(ayar, T + 61 * 60_000).durum == "OK"
    assert saglik.paper_kontrol(ayar, T + 80 * 60_000).durum == "UYARI"
    assert saglik.paper_kontrol(ayar, T + 3 * 3_600_000).durum == "HATA"


def test_gece_isi_yasi(ayar):
    m = _db(ayar)
    simdi = datetime(2026, 9, 27, 12, tzinfo=UTC)
    assert saglik.gece_kontrol(ayar, simdi).durum == "HATA"
    denetim.kaydet(m, "veri", "gece_isi", {}, zaman=simdi - timedelta(hours=10))
    assert saglik.gece_kontrol(ayar, simdi).durum == "OK"
    assert saglik.gece_kontrol(ayar, simdi + timedelta(hours=20)).durum == "UYARI"
    assert saglik.gece_kontrol(ayar, simdi + timedelta(hours=45)).durum == "HATA"


def test_yedek_yasi_ve_hata(ayar, tmp_path):
    a = ayar.model_copy(update={"yedek_dizini": tmp_path})
    simdi = datetime(2026, 9, 27, 12, tzinfo=UTC)
    assert saglik.yedek_kontrol(a, simdi).durum == "HATA"
    (tmp_path / "son.json").write_text(json.dumps({"dosya": "x.dump", "bayt": 1e8, "sha256": "ab",
                                                   "zaman": "2026-09-27T02:15:00Z"}))
    r = saglik.yedek_kontrol(a, simdi)
    assert r.durum == "OK" and "x.dump" in r.ayrinti
    assert saglik.yedek_kontrol(a, simdi + timedelta(hours=20)).durum == "HATA"
    (tmp_path / "son_hata.json").write_text(json.dumps({"zaman": "2026-09-27T03:00:00Z", "hata": "x"}))
    assert saglik.yedek_kontrol(a, simdi).durum == "HATA"


def test_log_triyaj(tmp_path):
    f = tmp_path / "paper-calis.jsonl"
    f.write_text(json.dumps({"level": "error", "event": "eski", "bilesen": "x"}) + "\n")
    t = saglik.LogTriyaj(tmp_path)
    assert t.yeni_hatalar() == []  # ilk bakış: geçmiş bildirilmez
    with f.open("a") as fh:
        fh.write(json.dumps({"level": "info", "event": "karar", "bilesen": "canli.dugum"}) + "\n")
        fh.write(json.dumps({"level": "error", "event": "mutabakat_farki_kol_durdu", "bilesen": "canli.dugum",
                             "kol": "k"}) + "\n")
        fh.write('{"level": "error", "event": "yar')  # yarım satır: sonraki tura
    h = t.yeni_hatalar()
    assert [x["olay"] for x in h] == ["mutabakat_farki_kol_durdu"] and h[0]["ozet"]["kol"] == "k"
    with f.open("a") as fh:
        fh.write('im"}\n')
    assert [x["olay"] for x in t.yeni_hatalar()] == ["yarim"]
    f.write_text(json.dumps({"level": "critical", "event": "dondu"}) + "\n")  # döndü: baştan
    assert [x["olay"] for x in t.yeni_hatalar()] == ["dondu"]


def test_bildirim_susturma_ve_kanal(ayar):
    giden = []
    a = ayar.model_copy(update={"telegram_sohbet": "1"})
    assert not Bildirici(a, gonderici=giden.append).gonder("KRITIK", "x")  # token yok: yalnız log
    from pydantic import SecretStr
    a = a.model_copy(update={"telegram_token": SecretStr("t")})
    b = Bildirici(a, sessiz_sn=3600, gonderici=giden.append)
    assert b.gonder("KRITIK", "paper durdu", anahtar="k") and not b.gonder("KRITIK", "paper durdu", anahtar="k")
    assert b.gonder("BILGI", "düzeldi")
    assert len(giden) == 2 and "KRITIK" in giden[0]


def test_olu_adam_sinyali(ayar, monkeypatch):
    giden = []

    class Yanit:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    monkeypatch.setattr(saglik.urllib.request, "urlopen", lambda req, timeout: giden.append(req.full_url) or Yanit())
    assert saglik.olu_adam(ayar, []) is None                        # adres yok: sinyal yok
    a = ayar.model_copy(update={"olu_adam_url": "https://hc-ping.com/abc"})
    ok = [saglik.Sonuc("paper", "OK", ""), saglik.Sonuc("sirlar", "UYARI", "")]
    assert saglik.olu_adam(a, ok) and giden[-1] == "https://hc-ping.com/abc"
    assert saglik.olu_adam(a, [saglik.Sonuc("paper", "HATA", "")]) and giden[-1] == "https://hc-ping.com/abc/fail"
    assert saglik.olu_adam(a, [saglik.Sonuc("dns", "HATA", "")]) and giden[-1] == "https://hc-ping.com/abc"  # kritik değil
