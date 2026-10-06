"""Bekçi (2026-09-27 denetimi): paper kalp atışı, gece işi, yedek yaşı, log triyajı, bildirim susturma."""
import json
from datetime import UTC, datetime, timedelta

import pytest
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


def test_kilit_takvim_tazeligi(ayar):
    from sqlalchemy import insert

    from tradebot.db import ham_dosya, paper_kol

    g = 86_400_000
    gun = T // g * g
    m = _db(ayar)
    assert saglik.kilit_takvim_kontrol(ayar, gun).durum == "OK"            # kilit kolu yok: bilgi
    with m.begin() as b:
        b.execute(insert(paper_kol).values(kol="d13:kilit_kisa@kilit_perp@1d", acilis=datetime.now(UTC),
                                           baslangic_ms=gun, baslangic_ozkaynak=1e5, sinif="A", kod_surumu="t",
                                           tanim={"grup_tanim": {"dugum": "kilit"}}))
    assert saglik.kilit_takvim_kontrol(ayar, gun).durum == "HATA"          # hiç indirilmedi
    with m.begin() as b:
        b.execute(insert(ham_dosya).values(kaynak="defillama", anahtar=f"unlocks/gunluk/{gun}", yol="x", sha256="a" * 64,
                                           boyut=1, indirildi=datetime.now(UTC)))
    assert saglik.kilit_takvim_kontrol(ayar, gun + 3_600_000).durum == "OK"
    assert saglik.kilit_takvim_kontrol(ayar, gun + g + 30 * 60_000).durum == "OK"     # yarının takvimi 00:40'a kadar
    r = saglik.kilit_takvim_kontrol(ayar, gun + g + 50 * 60_000)
    assert r.durum == "UYARI" and "yalnız kapanış" in r.ayrinti
    assert saglik.kilit_takvim_kontrol(ayar, gun + 2 * g + 50 * 60_000).durum == "HATA"


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
    b = Bildirici(a, sessiz_sn=3600, gonderici=giden.append, saat=lambda: datetime(2026, 9, 27, 12, tzinfo=UTC))
    assert b.gonder("KRITIK", "paper durdu", anahtar="k") and not b.gonder("KRITIK", "paper durdu", anahtar="k")
    assert b.gonder("BILGI", "düzeldi")
    assert len(giden) == 2 and "KRITIK" in giden[0]


def test_sessiz_saat_biriktirir_kritik_gecer(ayar):
    from pydantic import SecretStr

    from tradebot.bildirim import sessiz_mi
    assert sessiz_mi(19, (19, 5)) and sessiz_mi(23, (19, 5)) and sessiz_mi(4, (19, 5))
    assert not sessiz_mi(5, (19, 5)) and not sessiz_mi(12, (19, 5)) and sessiz_mi(3, (2, 6))
    giden, simdi = [], [datetime(2026, 9, 27, 21, tzinfo=UTC)]   # İstanbul 00:00
    a = ayar.model_copy(update={"telegram_sohbet": "1", "telegram_token": SecretStr("t")})
    b = Bildirici(a, gonderici=giden.append, saat=lambda: simdi[0])
    assert not b.gonder("UYARI", "dns: UYARI") and not b.gonder("BILGI", "haftalık rapor")
    assert b.gonder("KRITIK", "paper: HATA")                 # kritik gece de anında
    assert b.bosalt() == 0 and len(giden) == 1               # hâlâ gece
    simdi[0] = datetime(2026, 9, 28, 5, 5, tzinfo=UTC)
    assert b.bosalt() == 2 and len(giden) == 2 and b.bekleyen == []
    assert "gece biriken 2" in giden[1] and "dns: UYARI" in giden[1] and "haftalık rapor" in giden[1]
    assert b.bosalt() == 0
    simdi[0] = datetime(2026, 9, 28, 20, tzinfo=UTC)         # uzun birikim: sınırda bölünür
    for i in range(30):
        b.gonder("UYARI", f"{i}: " + "x" * 300)
    simdi[0] = datetime(2026, 9, 29, 6, tzinfo=UTC)
    assert b.bosalt() == 30 and len(giden) == 5 and all(len(m) <= 4000 for m in giden)


def test_durum_izleyici_ortam_onay_ister():
    S = saglik.Sonuc
    iz = saglik.DurumIzleyici(onay=3)
    tur = lambda ad, d: iz.isle(S(ad, d, ""))  # noqa: E731
    # açılış: sorunsuz → bildirim yok; kritik kontrol ilk turda
    assert tur("dns", "OK") == (True, False) and tur("paper", "OK") == (True, False)
    assert tur("paper", "HATA") == (True, True) and iz.bildirilen["paper"] == "HATA"
    assert tur("paper", "OK") == (True, True) and iz.bildirilen["paper"] == "OK"
    # tek turluk DNS sıçraması bildirilmez (host'ta 2026-09-27: HATA → 5 dk sonra OK)
    assert tur("dns", "HATA")[1] is False and tur("dns", "OK")[1] is False and tur("dns", "OK")[1] is False
    # UYARI/HATA arasında gidip gelen kalıcı sorun: UYARI olarak onaylanır, sonra HATA'ya yükselir
    assert [tur("dns", d)[1] for d in ("HATA", "UYARI", "HATA")] == [False, False, True]
    assert iz.bildirilen["dns"] == "UYARI"
    assert [tur("dns", d)[1] for d in ("HATA", "HATA")] == [False, True] and iz.bildirilen["dns"] == "HATA"
    # düzelme de onay ister; tek iyi tur yetmez
    assert [tur("dns", d)[1] for d in ("OK", "HATA", "OK", "OK", "OK")] == [False, False, False, False, True]
    assert iz.bildirilen["dns"] == "OK"
    # sırlar hiç bildirilmez
    assert tur("sirlar", "UYARI") == (True, False)


def test_en_kisa_gidis_donus():
    # 2. örnekte bağlantı gecikmesi (4 sn): orta nokta sapar; en kısa örnek gerçek farkı (+0,1) verir
    assert saglik.en_kisa_gidis_donus([(100.0, 100.2, 100.2), (200.0, 204.1, 204.1), (300.0, 300.15, 300.1)]) \
        == pytest.approx(0.1)


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
