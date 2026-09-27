"""MT5 köprüsü (Faz 8): sunucu saatinden UTC'ye, yalnız kapanmış bar, saat farkı ölçümü, takılma, HTTP uçtan uca.

Gerçek MetaTrader5 paketi yalnız Windows'ta: burada sahte modül (Spike 08'de görülen davranışlarla) kullanılır.
"""
import threading
import time
from http.server import ThreadingHTTPServer
from types import SimpleNamespace as NS

import pytest

from tradebot.mt5 import istemci, kopru
from tradebot.mt5.istemci import KopruHatasi, Mt5Istemci

FARK = 3 * 3_600_000                     # NCM sunucusu: İstanbul (+3)
T0 = 1_790_000_100_000 // 900_000 * 900_000   # 15 dk sınırı (UTC ms)


class SahteMt5:
    TIMEFRAME_M1, TIMEFRAME_M5, TIMEFRAME_M15, TIMEFRAME_M30 = 1, 5, 15, 30
    TIMEFRAME_H1, TIMEFRAME_H4, TIMEFRAME_D1 = 16385, 16388, 16408

    def __init__(self, simdi_ms: int) -> None:
        self.simdi_ms = simdi_ms
        self.tik_ms = simdi_ms + FARK - 2_000          # taze tik (sunucu saatiyle)
        # sunucu saatiyle M15 barlar: T0'dan önceki 40 bar + şu an açık olan bar
        self.barlar = [((T0 + FARK) // 1000 - 900 * i, 100.0 + i, 101.0 + i, 99.0 + i, 100.5 + i, 10 + i, 3, 0)
                       for i in range(40, -1, -1)]
        self.istekler = []

    def terminal_info(self):
        return NS(connected=True, trade_allowed=True)

    def account_info(self):
        return NS(login=316722, server="NCMInvestmentMenkul-Demo", currency="USD")

    def symbols_get(self):
        return [NS(name="GOLD", path="Forex\\Metals\\GOLD_USD\\GOLD")]

    def symbol_select(self, *_):
        return True

    def symbol_info(self, ad):
        return NS(name=ad, point=0.01, digits=2, trade_contract_size=100.0, volume_min=0.01) if ad == "GOLD" else None

    def symbol_info_tick(self, _):
        return NS(bid=2650.1, ask=2650.4, last=0.0, time_msc=self.tik_ms)

    def copy_rates_range(self, sembol, tf, bas, bit):
        self.istekler.append((sembol, tf, bas, bit))
        b, s = bas.timestamp(), bit.timestamp()
        return [r for r in self.barlar if b <= r[0] <= s]

    def last_error(self):
        return (1, "Success")


def test_fark_adayi():
    simdi = T0 + 123_456
    assert kopru.fark_adayi(simdi + FARK - 2_000, simdi) == FARK            # taze tik
    assert kopru.fark_adayi(simdi + FARK - 2 * 86_400_000, simdi) is None  # hafta sonu bayat tik (±14 saat dışı)
    assert kopru.fark_adayi(simdi + FARK - 7 * 60_000, simdi) is None      # 15 dk'nın katı değil: bayat
    assert kopru.fark_adayi(simdi - 5 * 3_600_000 + 500, simdi) == -5 * 3_600_000


def test_kapanmis_barlar_utc_ve_acik_bar_atilir():
    satir = [((T0 + FARK) // 1000 - 900, 1, 2, 0.5, 1.5, 7, 3, 0), ((T0 + FARK) // 1000, 1, 2, 0.5, 1.5, 7, 3, 0)]
    out = kopru.kapanmis_barlar(satir, FARK, 900, T0 + 60_000)  # ikinci bar T0'da açıldı, henüz kapanmadı
    assert out == [[T0 - 900_000, 1.0, 2.0, 0.5, 1.5, 7, 3, 0]]
    assert len(kopru.kapanmis_barlar(satir, FARK, 900, T0 + 900_000)) == 2   # kapanış anında kapanmış sayılır


def test_isci_zaman_asimi_ve_takilma():
    cikti = threading.Event()
    isci = kopru.Isci(takilma_sn=1.5, cik=cikti.set)
    assert isci.calistir(lambda: 42) == 42
    with pytest.raises(ValueError):
        isci.calistir(lambda: int("x"))
    with pytest.raises(kopru.ZamanAsimi):
        isci.calistir(lambda: time.sleep(4), zaman_asimi=0.3)
    assert cikti.wait(5)   # takılan çağrı süreci sonlandırır (gözetmen yeniden başlatır)


def test_fark_olcumu_uc_ardisik_ister():
    m = SahteMt5(T0 + 60_000)
    k = kopru.Kopru(m, isci=None, fark_varsayilan_ms=0, saat=lambda: m.simdi_ms)
    k.izlenen = {"GOLD"}
    for beklenen in (0, 0, FARK):
        k.fark_olc()
        assert k.fark_ms == beklenen
    m.tik_ms -= 3 * 86_400_000       # piyasa kapandı: bayat tik farkı bozmaz
    k.fark_olc()
    assert k.fark_ms == FARK and k.saglik()["fark_kaynak"] == "olculen"


@pytest.fixture
def sunucu():
    m = SahteMt5(T0 + 60_000)
    k = kopru.Kopru(m, kopru.Isci(takilma_sn=60, cik=lambda: None), FARK, saat=lambda: m.simdi_ms)
    s = ThreadingHTTPServer(("127.0.0.1", 0), kopru.isleyici(k, cagri_sn=2))
    threading.Thread(target=s.serve_forever, daemon=True).start()
    yield m, k, Mt5Istemci(f"http://127.0.0.1:{s.server_address[1]}", zaman_asimi=10)
    s.shutdown()


def test_http_uctan_uca(sunucu, monkeypatch):
    m, k, ist = sunucu
    s = ist.saglik()
    assert s["bagli"] and s["hesap"] == 316722 and s["fark_sn"] == 10_800 and "SIFRE" not in str(s)
    assert ist.semboller() == [["GOLD", "Forex\\Metals\\GOLD_USD\\GOLD"]]
    assert ist.semboller(["GOLD"])["GOLD"]["trade_contract_size"] == 100.0
    q = ist.kotasyon(["GOLD"])
    assert q["kotasyon"]["GOLD"]["tik_ms"] == m.simdi_ms - 2_000     # UTC'ye çevrildi

    monkeypatch.setattr(kopru, "EN_COK_BAR", 7)      # sayfalama: 7 barlık parçalar
    monkeypatch.setattr(istemci, "EN_COK_BAR", 7)
    df = ist.mumlar("GOLD", "M15", T0 - 40 * 900_000, T0 + 900_000)
    assert len(m.istekler) >= 6
    assert df.height == 40                                   # T0'da açılan bar kapanmadı
    assert df["acilis_ms"].to_list() == [T0 - 900_000 * i for i in range(40, 0, -1)]
    assert df["acilis_ms"].is_unique().all() and df["close"][-1] == 101.5
    # istek sunucu saatine çevrildi
    assert m.istekler[0][2].timestamp() * 1000 == T0 - 40 * 900_000 + FARK


def test_http_hatalar(sunucu):
    m, k, ist = sunucu
    with pytest.raises(KopruHatasi, match="400"):
        ist._al("/mumlar", sembol="GOLD", tf="M7", bas_ms=0, bit_ms=1)
    with pytest.raises(KopruHatasi, match="404"):
        ist._al("/yok")
    m.copy_rates_range = lambda *a: time.sleep(3)
    with pytest.raises(KopruHatasi, match="504"):
        ist.mumlar("GOLD", "M15", T0 - 900_000, T0)
    m.copy_rates_range = lambda *a: None
    time.sleep(1.5)  # takılan çağrı bitsin
    with pytest.raises(KopruHatasi, match="MT5"):
        ist.mumlar("GOLD", "M15", T0 - 900_000, T0)


def test_bekci_mt5_kontrolu(sunucu, ayar):
    from tradebot import saglik
    _, _, ist = sunucu
    a = ayar.model_copy(update={"mt5_kopru_forex": ist.url})
    r = saglik.mt5_kontrol(a)
    assert r.durum == "OK" and "forex bağlı" in r.ayrinti and "+3.0 sa" in r.ayrinti
    a = a.model_copy(update={"mt5_kopru_viop": "http://127.0.0.1:9"})   # ulaşılamıyor
    r = saglik.mt5_kontrol(a)
    assert r.durum == "HATA" and r.ayrinti.startswith("forex bağlı") and "viop:" in r.ayrinti
    assert "mt5" in saglik.ORTAM


# --- katalog: VİOP takvimi, enstrümanlar, toplayıcı (Faz 8) ---

def test_viop_takvimi():
    from tradebot.veri.takvim import dt, takvim
    gun = [(str(dt(o))[11:16], str(dt(c))[11:16]) for o, c in takvim("viop_aksam").seanslar(
        1_790_294_400_000, 1_790_294_400_000 + 86_400_000) if str(dt(o))[:10] == "2026-09-25"]
    assert gun == [("06:40", "15:10"), ("16:15", "20:00")]                 # Spike 08: MT5 barlarıyla aynı
    assert [(str(dt(o))[11:16], str(dt(c))[11:16]) for o, c in takvim("viop").seanslar(
        1_790_294_400_000, 1_790_294_400_000) if str(dt(o))[:10] == "2026-09-25"] == [("06:40", "15:10")]  # gündüz
    arefe = [(str(dt(o))[11:16], str(dt(c))[11:16]) for o, c in takvim("viop_aksam").seanslar(
        1_773_878_400_000, 1_773_878_400_000) if str(dt(o))[:10] == "2026-03-19"]
    assert arefe == [("06:40", "09:30")]                                    # arefede akşam seansı yok
    on, onalti_otuz = 1_790_294_400_000 + 10 * 3_600_000, 1_790_294_400_000 + 16 * 3_600_000 + 1_800_000
    assert takvim("viop").acik_mi(on) and not takvim("viop").acik_mi(onalti_otuz)   # USDTRY akşam seansı yok
    assert takvim("viop_aksam").acik_mi(onalti_otuz)


def test_mt5_enstrumanlari_onekle_acilir():
    from tradebot.veri.enstruman import evren_yukle, mt5_enstrumanlari
    liste = mt5_enstrumanlari(evren_yukle(), {"forex": ["GOLD", "EURUSD", "AMD"],
                                              "viop": ["XU30_YAKINVADE", "F_XU0301026", "F_XU0301226", "F_USDTRY1026"]})
    k = {e.kimlik: (e.sinif, e.takvim) for e in liste}
    assert k == {"NCMFX:GOLD": ("metal", "fx_24x5"), "NCMFX:EURUSD": ("fx", "fx_24x5"),
                 "VIOP:XU30_YAKINVADE": ("endeks", "viop_aksam"), "VIOP:F_XU0301026": ("endeks_vadeli", "viop_aksam"),
                 "VIOP:F_XU0301226": ("endeks_vadeli", "viop_aksam"), "VIOP:F_USDTRY1026": ("doviz_vadeli", "viop")}


def test_gunluk_bar_seans_gunune_etiketlenir():
    import polars as pl

    from tradebot.veri.mt5 import katalog_barlari
    gun = 1_790_294_400_000                                    # 2026-09-25 00:00 UTC
    df = pl.DataFrame([[gun - 3 * 3_600_000, 1.0, 2.0, 0.5, 1.5, 70, 3, 9]], schema=istemci.SEMA, orient="row")
    k = katalog_barlari(df, "1d", FARK, gercek_hacim=True)     # MT5: 2026-09-24 21:00 UTC = sunucu 25'i 00:00
    assert k["acilis_ms"].to_list() == [gun] and k["volume"].to_list() == [9.0]
    assert katalog_barlari(df, "1h", FARK, gercek_hacim=False)["volume"].to_list() == [70.0]


class SahteMt5Cok(SahteMt5):
    """Birden çok sembol ve zaman dilimi: sunucu saatiyle hizalı sentetik barlar."""
    ADIM = {1: 60, 16385: 3600, 16408: 86_400}

    def symbols_get(self):
        return [NS(name=s, path=s) for s in ("GOLD", "XU30_YAKINVADE", "F_XU0301026")]

    def copy_rates_range(self, sembol, tf, bas, bit):
        self.istekler.append((sembol, tf, bas, bit))
        adim = self.ADIM[tf]
        b, s = int(bas.timestamp()), int(bit.timestamp())
        ilk = -(-b // adim) * adim
        return [(t, 10.0, 11.0, 9.0, 10.5, 5, 2, 7) for t in range(ilk, s + 1, adim)]


def test_toplayici_uctan_uca(ayar):
    from sqlalchemy import create_engine, select

    from tradebot.db import ham_dosya, metadata
    from tradebot.veri.depo import BarDepo
    from tradebot.veri.enstruman import evren_yukle
    from tradebot.veri.mt5 import Mt5Veri

    simdi = T0 + 60_000
    m5 = SahteMt5Cok(simdi)
    k = kopru.Kopru(m5, kopru.Isci(takilma_sn=60, cik=lambda: None), FARK, saat=lambda: simdi)
    s = ThreadingHTTPServer(("127.0.0.1", 0), kopru.isleyici(k, cagri_sn=10))
    threading.Thread(target=s.serve_forever, daemon=True).start()
    try:
        ist = Mt5Istemci(f"http://127.0.0.1:{s.server_address[1]}")
        m = create_engine(ayar.veritabani_url.get_secret_value())
        metadata.create_all(m)
        e = evren_yukle()
        e["mt5"]["derinlik_gun"] = {"1m": 1, "1h": 3, "1d": 10}
        v = Mt5Veri(ayar.veri_dizini, m, {"forex": ist, "viop": ist}, evren=e, saat=lambda: simdi)
        r = v.guncelle()
        assert not [x for x in r if x.get("hata")]
        kimlikler = {x["kimlik"] for x in r}
        assert {"NCMFX:GOLD", "VIOP:XU30_YAKINVADE", "VIOP:F_XU0301026"} <= kimlikler
        d = BarDepo(ayar.veri_dizini)
        h = d.oku("VIOP:F_XU0301026", "1h")
        assert h.height >= 71 and h["acilis_ms"].max() + 3_600_000 <= simdi    # yalnız kapanmış barlar
        assert (h["acilis_ms"] % 3_600_000 == 0).all() and h["volume"][0] == 7.0   # VİOP: gerçek hacim
        g = d.oku("NCMFX:GOLD", "1d")
        assert (g["acilis_ms"] % 86_400_000 == 0).all() and g["volume"][0] == 5.0  # gün başı etiketi; CFD: tik hacmi
        with m.connect() as b:
            assert b.execute(select(ham_dosya.c.anahtar).where(ham_dosya.c.kaynak == "mt5")).first() is not None
        # ikinci koşu: yeni bar yok, yalnız kalan istenir
        assert sum(x.get("yeni", 0) for x in v.guncelle()) == 0
    finally:
        s.shutdown()


def test_yogun_baslangic_seyrek_gecmisi_keser():
    import datetime as d
    from datetime import UTC, datetime

    import polars as pl

    from tradebot.veri.mt5 import yogun_baslangic

    def seri(a, b, adim):
        t, g = [], a
        while g < b:
            if g.weekday() < 5:
                t.append(int(g.timestamp() * 1000))
            g += adim
        return t
    gun, saat = d.timedelta(days=1), d.timedelta(hours=1)
    # NCM EURUSD: 2017–2021 günde tek "saatlik" bar, 2022'den gerçek saatlik
    t = seri(datetime(2017, 1, 2, tzinfo=UTC), datetime(2022, 1, 1, tzinfo=UTC), gun) + \
        seri(datetime(2022, 1, 3, tzinfo=UTC), datetime(2024, 1, 1, tzinfo=UTC), saat)
    assert yogun_baslangic(pl.Series(t)) == int(datetime(2022, 1, 1, tzinfo=UTC).timestamp() * 1000)
    # XU30_YAKINVADE: yoğun seride 6 aylık kurum deliği başlangıcı geri itmez
    t = seri(datetime(2016, 1, 4, tzinfo=UTC), datetime(2025, 10, 1, tzinfo=UTC), saat) + \
        seri(datetime(2026, 4, 1, tzinfo=UTC), datetime(2026, 9, 1, tzinfo=UTC), saat)
    assert yogun_baslangic(pl.Series(t)) == int(datetime(2016, 1, 1, tzinfo=UTC).timestamp() * 1000)
