"""`tradebot` komut satırı."""
from __future__ import annotations

import json
import time
from pathlib import Path

import typer

from tradebot import __version__, saglik
from tradebot.ayar import ayarlar
from tradebot.kayit import kur, log

uygulama = typer.Typer(help="TradeBot — kurumsal, çok piyasalı, otonom trade sistemi", no_args_is_help=True)
db_uygulama = typer.Typer(help="Veritabanı işlemleri", no_args_is_help=True)
uygulama.add_typer(db_uygulama, name="db")
veri_uygulama = typer.Typer(help="Veri platformu (Faz 2)", no_args_is_help=True)
uygulama.add_typer(veri_uygulama, name="veri")
arastirma_uygulama = typer.Typer(help="Araştırma motoru (Faz 3): test planı ve tarama", no_args_is_help=True)
uygulama.add_typer(arastirma_uygulama, name="arastirma")
zeka_uygulama = typer.Typer(help="Zekâ katmanı (Faz 6): toplayıcılar, Jev rolleri, olaylar", no_args_is_help=True)
uygulama.add_typer(zeka_uygulama, name="zeka")
paper_uygulama = typer.Typer(help="Paper canlı (Faz 7): Nautilus düğümü, defter", no_args_is_help=True)
uygulama.add_typer(paper_uygulama, name="paper")
mt5_uygulama = typer.Typer(help="MT5 köprüsü (Faz 8): host Windows'taki köprüleri sorgular", no_args_is_help=True)
uygulama.add_typer(mt5_uygulama, name="mt5")


def _mt5(hesap: str):
    from tradebot.mt5.istemci import Mt5Istemci

    url = getattr(ayarlar(), f"mt5_kopru_{hesap}", None)
    if not url:
        raise typer.BadParameter(f"TRADEBOT_MT5_KOPRU_{hesap.upper()} tanımlı değil")
    return Mt5Istemci(url)


@mt5_uygulama.command("durum")
def mt5_durum(hesap: str = typer.Argument("forex", help="forex | viop")) -> None:
    """Köprü sağlığı: terminal bağlı mı, sunucu saat farkı, son taze tik."""
    typer.echo(json.dumps(_mt5(hesap).saglik(), ensure_ascii=False, indent=1))


@mt5_uygulama.command("kotasyon")
def mt5_kotasyon(hesap: str, semboller: str = typer.Argument(..., help="virgüllü, ör. GOLD,EURUSD")) -> None:
    """Son bid/ask (tik zamanı UTC)."""
    typer.echo(json.dumps(_mt5(hesap).kotasyon(semboller.split(",")), ensure_ascii=False, indent=1))


@mt5_uygulama.command("mumlar")
def mt5_mumlar(hesap: str, sembol: str, zd: str = typer.Option("M15", "--zd"),
               saat: float = typer.Option(6.0, help="Son kaç saat")) -> None:
    """Son kapanmış barlar (UTC)."""
    simdi = int(time.time() * 1000)
    typer.echo(_mt5(hesap).mumlar(sembol, zd, simdi - int(saat * 3_600_000), simdi))

_ISARET = {"OK": "✓", "UYARI": "!", "HATA": "✗"}


@uygulama.command()
def surum() -> None:
    """Sürümü yazar."""
    typer.echo(__version__)


@uygulama.command("saglik")
def saglik_komutu(
    dongu: int = typer.Option(0, help="Saniye; 0 ise tek sefer, >0 ise sürekli kontrol ve durum değişiminde log."),
    json_cikti: bool = typer.Option(False, "--json", help="Makine okunur çıktı"),
) -> None:
    """Host/konteyner sağlığı: DNS, saat, veritabanı, disk, sırlar; host'ta paper kalp atışı, gece işi, yedek.
    `--dongu`: bekçi. Onaylı durum değişimi (`saglik.DurumIzleyici`) ve servis loglarındaki yeni hatalar Telegram'a
    (tanımlıysa) bildirilir; KRITIK dışındakiler sessiz saatte biriktirilir."""
    from tradebot.bildirim import Bildirici

    a = ayarlar()
    kur(a)
    kayitci = log("saglik")
    izleyici = saglik.DurumIzleyici()
    bildirici = Bildirici(a)
    triyaj = saglik.LogTriyaj(a.log_dizini) if dongu and a.log_dizini is not None else None
    gozetmen_var = dongu and a.ortam == "host" and a.veritabani_url is not None
    gozetmenler = [_gozetmen_kur(a, dugum=d) for d in DUGUMLER] if gozetmen_var else []
    while True:
        sonuclar = saglik.hepsi(a)
        if json_cikti:
            typer.echo(json.dumps([s.__dict__ for s in sonuclar], ensure_ascii=False))
        elif not dongu:
            for s in sonuclar:
                typer.echo(f" {_ISARET[s.durum]} {s.ad:<11} {s.durum:<6} {s.ayrinti}")
        for s in sonuclar if dongu else []:  # tek seferlik komutun çıktısı temiz kalsın (--json ile)
            degisti, bildir = izleyici.isle(s)
            if degisti:
                yaz = kayitci.info if s.durum == "OK" else kayitci.warning
                yaz("saglik_durumu", kontrol=s.ad, durum=s.durum, ayrinti=s.ayrinti)
            if bildir:
                durum = izleyici.bildirilen[s.ad]  # onaylı durum (ham turunkiyle aynı olmayabilir)
                seviye = {"HATA": "KRITIK", "UYARI": "UYARI"}.get(durum, "BILGI")
                bildirici.gonder(seviye, f"{s.ad}: {durum} · {s.ayrinti}")
        if dongu:
            bildirici.bosalt()   # sessiz saatte biriken uyarılar, sabah tek mesaj
        for h in triyaj.yeni_hatalar() if triyaj else []:
            bildirici.gonder("KRITIK", f"{h['dosya']} · {h['bilesen']} · {h['olay']}\n"
                             f"{json.dumps(h['ozet'], ensure_ascii=False, default=str)[:600]}",
                             anahtar=f"log:{h['bilesen']}:{h['olay']}")
        for g in gozetmenler:
            _gozetmen_tur(g, bildirici, kayitci)
        if dongu and saglik.olu_adam(a, sonuclar) is False:
            kayitci.warning("olu_adam_sinyali_gitmedi")
        if dongu and a.ortam == "host" and a.veritabani_url is not None:
            _haftalik_rapor(a, bildirici, kayitci)
            _gunluk_ozet(a, bildirici, kayitci, izleyici)
        if not dongu:
            raise typer.Exit(saglik.cikis_kodu(sonuclar))
        time.sleep(dongu)


DUGUMLER = ("paper", "kilit")   # her süreç ayrı gözetmen (kalp atışı ayrı)


def _gozetmen_kur(a, **ayar):
    from tradebot.arastirma.defter import kod_surumu
    from tradebot.canli.gozetmen import Gozetmen, binance_kotasyon
    from tradebot.db import motor as db_motor
    from tradebot.veri.http import NazikIstemci

    return Gozetmen(db_motor(a), binance_kotasyon(NazikIstemci("gozetmen", deneme=3, zaman_asimi=15).al), kod_surumu(),
                    **ayar)


def _gozetmen_tur(g, bildirici, kayitci) -> dict:
    """Bağımsız gözetmen turu (katman 5): donma varsa kapatır ve KRİTİK bildirir; hata da KRİTİK (kapatılamadı)."""
    try:
        r = g.kontrol()
    except Exception as e:  # noqa: BLE001
        kayitci.error("gozetmen_hatasi", dugum=g.dugum, hata=f"{type(e).__name__}: {e}"[:300])
        bildirici.gonder("KRITIK", f"Gözetmen ({g.dugum}) kontrol edemedi ya da kapatamadı: {type(e).__name__}: {e}"[:400],
                         anahtar=f"gozetmen_hata:{g.dugum}")
        return {"durum": "hata"}
    if r["durum"] == "donma_suphesi":
        kayitci.warning("gozetmen_donma_suphesi", dugum=g.dugum, **r)
    elif r["durum"] == "donma" and (r.get("kapatilan") or r.get("durdurulan")) and not r.get("kuru"):
        parca = [f"{kol} {kim.split(':')[-1]} {v['adet']:+.5g}" for kol, p in r["kapatilan"].items()
                 for kim, v in p.items()]
        ad = "Paper motoru" if g.dugum == "paper" else f"{g.dugum} düğümü"
        bildirici.gonder("KRITIK", f"{ad} {r['yas_dk']:.0f} dakikadır kalp atışı yazmıyor: donmuş sayıldı.\n"
                         f"Pozisyonlar defterde kapatıldı: {'; '.join(parca) or 'açık pozisyon yoktu'}\n"
                         f"{len(r['durdurulan'])} kol durduruldu; yeniden açmak için /devam <kol> (onaylı).")
    return r


@uygulama.command("gozetmen")
def gozetmen_komutu(
    kuru: bool = typer.Option(True, "--kuru/--gercek", help="Tatbikat: tespit et, yazma (varsayılan)"),
    esik_dk: float = typer.Option(125.0, help="Kalp atışı bu kadar dakikadan eskiyse donma"),
) -> None:
    """Bağımsız gözetmenin tek turu (tatbikat için; bekçi bunu her turda kendisi yapar). Isınma ve tur onayı atlanır."""
    a = ayarlar()
    kur(a)
    _yazdir({d: _gozetmen_kur(a, dugum=d, kuru=kuru, donma_ms=int(esik_dk * 60_000), onay_tur=1, isinma_sn=0).kontrol()
             for d in DUGUMLER})


def gunluk_ozet_zamani(simdi_ms: int, sessiz_bitis_saat: int, veri_dizini) -> Path | None:
    """Bugünün özeti gönderilecekse işaret dosyasının yolu: sessiz saat bittiyse ve bugün henüz yazılmadıysa."""
    from datetime import UTC, datetime

    t = datetime.fromtimestamp(simdi_ms / 1000, UTC)
    yol = Path(veri_dizini) / "rapor" / f"gunluk-{t.date().isoformat()}.txt"
    return None if t.hour < sessiz_bitis_saat or yol.exists() else yol


def _gunluk_ozet(a, bildirici, kayitci, izleyici) -> None:
    """Bekçi: her gün sessiz saat bitince bir kez (Final Doküman §Operasyon: günlük özet). Dosya işareti yeniden
    başlatmada ikinci kez gönderilmesini önler."""
    from tradebot.canli import rapor
    from tradebot.db import motor as db_motor

    simdi = int(time.time() * 1000)
    yol = gunluk_ozet_zamani(simdi, a.sessiz_saat_utc[1], a.veri_dizini)
    if yol is None:
        return
    sorun = {ad: d for ad, d in izleyici.bildirilen.items() if d != "OK"}
    saglik_satiri = "Sağlık: " + (", ".join(f"{k} {v}" for k, v in sorted(sorun.items())) if sorun else "hepsi OK")
    try:
        metin = rapor.gunluk_ozet(db_motor(a), simdi, saglik_satiri)
    except Exception as e:  # noqa: BLE001 — özet hatası bekçiyi durdurmaz
        kayitci.error("gunluk_ozet_hatasi", hata=f"{type(e).__name__}: {e}"[:300])
        return
    yol.parent.mkdir(parents=True, exist_ok=True)
    yol.write_text(metin, encoding="utf-8")
    bildirici.gonder("BILGI", metin)
    kayitci.info("gunluk_ozet", yol=str(yol))


def _haftalik_rapor(a, bildirici, kayitci) -> None:
    """Bekçi: bitmiş son haftanın paper raporu yazılmamışsa üretir (Pazartesi 00:30 UTC sonrası) ve özetini bildirir."""
    from tradebot.canli import rapor
    from tradebot.db import motor as db_motor

    m = db_motor(a)
    h = rapor.bekleyen_hafta(a.veri_dizini, int(time.time() * 1000), rapor.ilk_acilis(m))
    if h is None:
        return
    try:
        r, _, yol = rapor.uret(m, a.veri_dizini, h)
    except Exception as e:  # noqa: BLE001 — rapor hatası bekçiyi durdurmaz
        kayitci.error("paper_rapor_hatasi", hata=f"{type(e).__name__}: {e}"[:300])
        return
    kayitci.info("paper_rapor", hafta=r["hafta"], yol=str(yol))
    bildirici.gonder("BILGI", rapor.telegram_ozeti(r))
    from tradebot.canli import terfi
    from tradebot.canli.kollar import kollar

    try:
        sonuc = terfi.hafta_degerlendir(m, a.veri_dizini, kollar(), h + 7 * 86_400_000)
    except Exception as e:  # noqa: BLE001
        kayitci.error("terfi_hatasi", hata=f"{type(e).__name__}: {e}"[:300])
        return
    for x in sonuc:
        kayitci.info("terfi_degerlendirme", kol=x["kol"], gecti=x.get("gecti"), hata=x.get("hata"))
        if x.get("gecti"):
            bildirici.gonder("BILGI", f"Terfi: {x['kol']} B → A (paper ölçütü geçti; dağıtım gelecek hafta)")


@db_uygulama.command("yukselt")
def db_yukselt() -> None:
    """Alembic göçlerini en son sürüme uygular."""
    from alembic import command
    from alembic.config import Config

    kok = Path(__file__).resolve().parents[2]
    cfg = Config(str(kok / "alembic.ini"))
    cfg.set_main_option("script_location", str(kok / "migrations"))
    command.upgrade(cfg, "head")
    typer.echo("veritabanı güncel")


@db_uygulama.command("denetim-dogrula")
def denetim_dogrula() -> None:
    """Denetim izinin hash zincirini baştan sona doğrular."""
    from tradebot import denetim
    from tradebot.db import motor

    saglam, kirik, n = denetim.dogrula(motor(ayarlar()))
    typer.echo(f"{n} kayıt · {'zincir sağlam' if saglam else f'ZİNCİR KIRIK: kayıt {kirik}'}")
    raise typer.Exit(0 if saglam else 2)


def _veri_baglam():
    from tradebot.db import motor

    a = ayarlar()
    kur(a)
    return a, motor(a)


def _yazdir(sonuc: dict) -> None:
    typer.echo(json.dumps(sonuc, ensure_ascii=False, indent=1, default=str))


@veri_uygulama.command("binance")
def veri_binance(sinir: int = typer.Option(0, help="Yalnız ilk N sembol (deneme); 0 = hepsi")) -> None:
    """Tüm USDT spot sembolleri (saatlik) + seçili dakikalık + funding."""
    from tradebot.veri import is_akisi

    a, m = _veri_baglam()
    _yazdir(is_akisi.binance(a, m, sinir or None))


@veri_uygulama.command("yahoo")
def veri_yahoo(tam: bool = typer.Option(False, help="Tüm geçmişi yeniden indir")) -> None:
    """ABD ETF'leri + BIST (günlük) ve kurumsal işlemler."""
    from tradebot.veri import is_akisi

    a, m = _veri_baglam()
    _yazdir(is_akisi.yahoo(a, m, tam))


@veri_uygulama.command("haber-takvimi")
def veri_haber_takvimi() -> None:
    """FOMC, NFP, CPI yayın anlarını resmi arşivlerden indirir → config/haber_takvimi.yaml (haber filtresi)."""
    from tradebot.veri.depo import HamDepo
    from tradebot.veri.haber_takvimi import indir

    a, m = _veri_baglam()
    _yazdir(indir(HamDepo(a.veri_dizini, m)))


@veri_uygulama.command("dukascopy")
def veri_dukascopy(butce_dk: float = typer.Option(60.0, help="Zaman bütçesi (dakika); kalan sonraki koşuya")) -> None:
    """FX, metal, endeks, emtia (sıkı hız sınırı; kaldığı yerden devam eder)."""
    from tradebot.veri import is_akisi

    a, m = _veri_baglam()
    _yazdir(is_akisi.dukascopy(a, m, butce_dk))


@veri_uygulama.command("vadeli")
def veri_vadeli() -> None:
    """Dalga 3 vadeli serileri: OECD faizini indirir, VADELI:* serilerini katalogdan baştan kurar (veri/vadeli.py)."""
    from tradebot.veri import faiz, vadeli
    from tradebot.veri.depo import BarDepo, HamDepo
    from tradebot.veri.http import NazikIstemci

    a, m = _veri_baglam()
    icerik, yeni = faiz.indir(HamDepo(a.veri_dizini, m), NazikIstemci("oecd", zaman_asimi=120).al)
    _yazdir({"faiz_yeni": yeni} | vadeli.kur(BarDepo(a.veri_dizini), m, icerik))


@veri_uygulama.command("deribit")
def veri_deribit(
    para: str = typer.Option("BTC,ETH", help="Virgüllü"),
    bas: str = typer.Option("2020-06-01"),
    bit: str = typer.Option("", help="Boş: bugün"),
    is_parcacigi: int = typer.Option(4, help="Eşzamanlı pencere (tarihsel sunucu istek başına ~13 sn)"),
) -> None:
    """Dalga 4: haftalık opsiyon oynaklık yüzeyi (her Cuma, bir sonraki Cuma vadesi) + teslim fiyatları →
    data/opsiyon/. Kaldığı yerden devam eder (hesaplanmış haftalar atlanır, indirilmiş sayfalar ham depodan okunur)."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    from datetime import UTC, datetime

    import polars as pl

    from tradebot.veri.depo import HamDepo
    from tradebot.veri.deribit import DeribitGecmis, cumalar
    from tradebot.veri.http import NazikIstemci

    a, m = _veri_baglam()
    kayitci = log("veri.deribit")
    dizin = a.veri_dizini / "opsiyon"
    dizin.mkdir(parents=True, exist_ok=True)
    son = datetime.fromisoformat(bit).replace(tzinfo=UTC) if bit else datetime.now(UTC)
    ham = HamDepo(a.veri_dizini, m)
    ozet = {}
    for p in [x.strip().upper() for x in para.split(",") if x.strip()]:
        dg = DeribitGecmis(ham, NazikIstemci("deribit", deneme=6, zaman_asimi=120).al)
        teslim = dg.teslim_fiyatlari(p)
        (dizin / f"{p}_teslim.json").write_text(json.dumps(teslim), encoding="utf-8")
        yol = dizin / f"{p}_haftalik.parquet"
        eski = pl.read_parquet(yol) if yol.exists() else None
        bitti = set(eski["giris_ms"].to_list()) if eski is not None else set()
        haftalar = [c for c in cumalar(datetime.fromisoformat(bas).replace(tzinfo=UTC), son)
                    if c.timestamp() * 1000 + 5 * 60_000 not in bitti and (son - c).days >= 7]
        satirlar = []

        def is_(c, p=p):
            return DeribitGecmis(ham, NazikIstemci("deribit", deneme=6, zaman_asimi=120).al).haftalik(p, c)

        with ThreadPoolExecutor(is_parcacigi) as h:
            for i, f in enumerate(as_completed([h.submit(is_, c) for c in haftalar])):
                try:
                    satirlar.append(f.result())
                except Exception as e:  # noqa: BLE001 — bir hafta düşerse diğerleri sürer; sonraki koşu yeniden dener
                    kayitci.error("hafta_hatasi", para=p, hata=f"{type(e).__name__}: {e}"[:200])
                if i % 20 == 0:
                    kayitci.info("ilerleme", para=p, bitti=i + 1, toplam=len(haftalar))
                if len(satirlar) >= 20:   # ara kayıt: uzun koşu yarıda kalırsa emek kaybolmasın
                    eski = pl.concat([x for x in (eski, pl.DataFrame(satirlar)) if x is not None], how="diagonal_relaxed")
                    eski.sort("giris_ms").write_parquet(yol)
                    satirlar = []
        if satirlar:
            eski = pl.concat([x for x in (eski, pl.DataFrame(satirlar)) if x is not None], how="diagonal_relaxed")
            eski.sort("giris_ms").write_parquet(yol)
        ozet[p] = {"hafta": 0 if eski is None else len(eski), "teslim_gunu": len(teslim)}
    _yazdir(ozet)


@veri_uygulama.command("kilit")
def veri_kilit() -> None:
    """Dalga 6: DefiLlama kilit açılım takvimi + olaylı token'ların Binance perp günlük mumu ve funding'i → data/kilit/."""
    from tradebot.arastirma.kilit_dalga import hazirla
    from tradebot.veri.depo import HamDepo
    from tradebot.veri.http import NazikIstemci

    a, m = _veri_baglam()
    _yazdir(hazirla(a.veri_dizini, HamDepo(a.veri_dizini, m), NazikIstemci("binancef", aralik_sn=0.25, zaman_asimi=120).al,
                    log("veri.kilit")))


@veri_uygulama.command("listeleme")
def veri_listeleme(bas: str = typer.Option("2020-12-01", help="Bu tarihten sonra listelenen perp'ler")) -> None:
    """Dalga 7: listeleme anı `bas`'tan sonra olan her Binance USDT-M perp'in günlük mumu + funding'i → data/listeleme/."""
    from datetime import UTC, datetime

    from tradebot.arastirma.listeleme import hazirla
    from tradebot.veri.depo import HamDepo
    from tradebot.veri.http import NazikIstemci

    a, m = _veri_baglam()
    bas_ms = int(datetime.fromisoformat(bas).replace(tzinfo=UTC).timestamp() * 1000)
    _yazdir(hazirla(a.veri_dizini, HamDepo(a.veri_dizini, m), NazikIstemci("binancef", aralik_sn=0.25, zaman_asimi=120).al,
                    bas_ms, log("veri.listeleme")))


@veri_uygulama.command("mt5")
def veri_mt5(butce_dk: float = typer.Option(60.0, help="Zaman bütçesi (dakika)")) -> None:
    """NCM MT5 (forex CFD + VİOP) barları köprüden kataloğa (1m, 1h, 1d)."""
    from tradebot.veri import is_akisi

    a, m = _veri_baglam()
    _yazdir(is_akisi.mt5(a, m, butce_dk))


@veri_uygulama.command("kalite")
def veri_kalite() -> None:
    """Tüm enstrümanlar için kalite raporu (veritabanına yazar)."""
    from tradebot.veri import is_akisi

    a, m = _veri_baglam()
    _yazdir(is_akisi.kalite_hepsi(a, m))


@veri_uygulama.command("evren")
def veri_evren() -> None:
    """Tarihsel evren tablolarını kurar (data/evren/*.parquet)."""
    from tradebot.veri import is_akisi

    a, m = _veri_baglam()
    _yazdir(is_akisi.evren_kur(a, m))


@veri_uygulama.command("gece")
def veri_gece(dukascopy_butce_dk: float = typer.Option(240.0)) -> None:
    """Gece işi: Binance → Yahoo → MT5 → kalite → evren → Dukascopy; sonuç denetim izine yazılır."""
    from tradebot.veri import is_akisi

    a, m = _veri_baglam()
    _yazdir(is_akisi.gece(a, m, dukascopy_butce_dk))


@veri_uygulama.command("zamanla")
def veri_zamanla(
    saat: str = typer.Option("01:30", help="Her gün UTC HH:MM"),
    hemen: bool = typer.Option(False, help="Başlarken, son gece işi 20 saatten eskiyse bir kez hemen çalıştır"),
    dukascopy_butce_dk: float = typer.Option(240.0),
) -> None:
    """Gece işini her gün belirtilen UTC saatinde çalıştırır (servis olarak)."""
    from datetime import UTC, datetime

    from tradebot.veri import is_akisi

    a, m = _veri_baglam()
    kayitci = log("veri.zamanla")
    ss, dd = map(int, saat.split(":"))
    if hemen and is_akisi.telafi_gerekli(m, datetime.now(UTC)):   # yalnız son gece işi 20 saatten eskiyse
        is_akisi.gece(a, m, dukascopy_butce_dk)
    while True:
        hedef = is_akisi.sonraki_calisma(datetime.now(UTC), ss, dd)
        kayitci.info("sonraki_gece_isi", zaman=hedef.isoformat())
        time.sleep(max(0.0, (hedef - datetime.now(UTC)).total_seconds()))
        is_akisi.gece(a, m, dukascopy_butce_dk)


@arastirma_uygulama.command("plan")
def arastirma_plan(
    kimlik: str = typer.Option(..., help="Plan kimliği (ör. 2026-09-25-trend-btc)"),
    aile: str = typer.Option(...), hipotez: str = typer.Option(...),
    izgara: str = typer.Option(..., help='JSON, ör. {"hizli":[10,20],"yavas":[50,100]}'),
    piyasalar: str = typer.Option(..., help="Virgülle enstrüman kimlikleri"),
    olcut: str = typer.Option(..., help="Geçme ölçütü (koşudan ÖNCE yazılır)"),
) -> None:
    """Test planı açar (koşudan önce; plansız koşu deftere giremez)."""
    from tradebot.arastirma.defter import Defter

    _, m = _veri_baglam()
    Defter(m).plan_ac(kimlik, aile, hipotez, json.loads(izgara), [x.strip() for x in piyasalar.split(",")], olcut)
    typer.echo(f"plan açıldı: {kimlik}")


@arastirma_uygulama.command("tara")
def arastirma_tara(
    plan: str = typer.Option(...), strateji: str = typer.Option(..., help="sma_kesisim | donchian | tsmom"),
    enstruman: str = typer.Option(..., help="ör. BINANCE:BTCUSDT"), zd: str = typer.Option("1d"),
    izgara: str = typer.Option(...), yon: str = typer.Option("long"), bant: float = typer.Option(0.0),
    hedef_vol: float = typer.Option(0.0, help="Yıllık oynaklık hedefi (0 = boyutlandırma yok)"),
    kaldirac: float = typer.Option(1.0, help="Brüt maruziyet tavanı (≤ 3; ≥ 5 yasak)"),
    frenler: bool = typer.Option(False, help="Günlük/haftalık fren ve acil durdurmayı backtest'te uygula"),
    json_cikti: bool = typer.Option(False, "--json"),
) -> None:
    """Izgara taraması + DSR + plato + walk-forward + yıllık kırılım; her kombinasyon deftere yazılır."""
    from tradebot.arastirma.defter import Defter
    from tradebot.arastirma.tarama import tara
    from tradebot.veri import enstruman as en
    from tradebot.veri.depo import BarDepo

    a, m = _veri_baglam()
    kayit = next((k for k in en.hepsi(m) if k["kimlik"] == enstruman), None)
    if kayit is None:
        raise typer.BadParameter(f"enstrüman kaydı yok: {enstruman}")
    r = tara(Defter(m), BarDepo(a.veri_dizini), plan, strateji, enstruman, kayit["piyasa"], kayit["sinif"], zd,
             json.loads(izgara), yon=yon, bant=bant, hedef_vol=hedef_vol or None, kaldirac=kaldirac, frenler=frenler,
             takvim_adi=kayit["takvim"])
    if json_cikti:
        _yazdir(r)
        return
    typer.echo(f"{r['enstruman']} {r['zd']} · {r['bar']} bar · maliyet {r['maliyet']} · veri {r['veri_hash']}")
    typer.echo(f"boyut: {r['boyut']} · frenler: {'açık' if r['frenler'] else 'kapalı'}")
    typer.echo(f"{'strateji':<42}{'puan%/hf':>9}{'yıllık':>8}{'Sharpe':>7}{'DD':>7}{'kötü hf':>8}{'işlem':>6}{'kapı':>5}")
    for s in r["satirlar"]:
        typer.echo(f"{s['strateji'][:41]:<42}{s['puan'] * 100:>9.3f}{s['yillik_bilesik'] * 100:>7.1f}%{s['sharpe']:>7.2f}"
                   f"{s['en_kotu_dusus'] * 100:>6.0f}%{s['en_kotu_hafta'] * 100:>7.1f}%{s['islem']:>6}"
                   f"{'✓' if s['kapilar_gecti'] else '✗':>5}")
    at = r["al_tut"]
    typer.echo(f"{'al-tut (kıyas)':<42}{at['puan'] * 100:>9.3f}{at['yillik_bilesik'] * 100:>7.1f}%{at['sharpe']:>7.2f}"
               f"{at['en_kotu_dusus'] * 100:>6.0f}%{at['en_kotu_hafta'] * 100:>7.1f}%")
    d, p, w = r["dsr"], r["plato"], r["walk_forward"]
    typer.echo("")
    e = r["en_iyi"]
    typer.echo(f"en iyi: {e['strateji']} · yarım Kelly {e['yarim_kelly']:.2f}x · fren bar {e['fren_bar']}"
               f"{' · ACİL DURDURMA tetiklendi' if e['acil_durdurma'] else ''}")
    typer.echo(f"DSR {d.get('dsr', float('nan')):.3f} (aile deneme {d.get('deneme')}, SR* {d.get('sr_esik', 0):.3f}) · "
               f"plato oranı {p['plato_orani']:.2f} ({'var' if p['plato_var'] else 'YOK'})")
    if w.get("pencere"):
        typer.echo(f"walk-forward: {w['pencere']} pencere, OOS yıllık {w['oos_yillik'] * 100:.1f}%, "
                   f"Sharpe {w['oos_sharpe']:.2f}, DD {w['oos_en_kotu_dusus'] * 100:.0f}%, seçimler {w['secimler']}")
    typer.echo("yıllık: " + "  ".join(f"{y}:{v * 100:+.0f}%" for y, v in r["yillik"].items()))


@arastirma_uygulama.command("opsiyon")
def arastirma_opsiyon(
    dosya: str = typer.Option("config/turnuva/dalga4.yaml", help="Dalga 4 ön kayıt dosyası"),
    trend: str = typer.Option("data/turnuva/dalga2/donchian_ls__kripto_btc_eth__4h.json",
                              help="Korelasyon için trend kolu sonuç dosyası (bilgi)"),
) -> None:
    """Dalga 4 — opsiyon oynaklık primi: ön kayıtlı yapı × para kollarını koşar, deftere ve data/turnuva/'ya yazar."""
    from tradebot.arastirma import opsiyon_dalga
    from tradebot.arastirma.defter import Defter

    a, m = _veri_baglam()
    t = Path(trend)
    if not t.is_absolute():
        t = a.veri_dizini / Path(*t.parts[1:]) if t.parts and t.parts[0] == "data" else t
    for r in opsiyon_dalga.kos(Path(dosya), a.veri_dizini, Defter(m), t):
        k, o = r["tam"], r["kor"]
        typer.echo(f"{r['karar']:<5} {r['kol']:<34} Sharpe {k['sharpe']:.2f}  yıllık {k['yillik_bilesik']:+.1%}  "
                   f"DD {k['en_kotu_dusus']:.0%}  en kötü hf {k['en_kotu_hafta']:+.1%}  DSR {r['dsr']['dsr']:.2f}  "
                   f"kör yıllık {o.get('yillik_bilesik', float('nan')):+.1%}  stres {r['stres_2x']['yillik_bilesik']:+.1%}  "
                   f"trend kor {r['trend_korelasyonu'] if r['trend_korelasyonu'] is None else round(r['trend_korelasyonu'], 2)}")


@arastirma_uygulama.command("kilit")
def arastirma_kilit(dosya: str = typer.Option("config/turnuva/dalga6_kilit.yaml")) -> None:
    """Olay tabanlı perp kısa (BTC ile nötr; dalga 6 kilit, dalga 7 listeleme): ön kayıtlı ızgara → defter, data/turnuva/."""
    from tradebot.arastirma import kilit_dalga
    from tradebot.arastirma.defter import Defter

    a, m = _veri_baglam()
    for r in kilit_dalga.kos(Path(dosya), a.veri_dizini, Defter(m)):
        k, o, ol = r["tam"], r["kor"], r["olay"]
        typer.echo(f"{r['karar']:<5} {r['kol']:<40} Sharpe {k.get('sharpe', 0):.2f}  yıllık {k.get('yillik_bilesik', 0):+.1%}  "
                   f"DD {k.get('en_kotu_dusus', 0):.0%}  DSR {r['dsr']['dsr']:.2f}  "
                   f"kör {o.get('yillik_bilesik', float('nan')):+.1%}  "
                   f"stres {r['stres_2x'].get('yillik_bilesik', 0):+.1%}  olay {ol['kurulan']}/{ol['toplam']}  "
                   f"birim ort {ol['birim_ort'] or 0:+.2%} t {ol['birim_t'] or 0:+.1f} isabet {ol['isabet'] or 0:.0%}")


@arastirma_uygulama.command("turnuva")
def arastirma_turnuva(
    dosya: str = typer.Option("config/turnuva/dalga1.yaml", help="Dalga ön kayıt dosyası"),
    grup: str = typer.Option("", help="Yalnız bu gruplar (virgüllü; boş = hepsi)"),
    strateji: str = typer.Option("", help="Yalnız bu stratejiler (virgüllü)"),
    zd: str = typer.Option("", help="Yalnız bu zaman dilimleri (virgüllü)"),
    tekrar: bool = typer.Option(False, help="Sonucu olan kolu yeniden koş (YENİ deneme sayılır)"),
) -> None:
    """Dalga dosyasındaki kolları koşar: planlar yoksa açılır, her varyant deftere, kol sonucu data/turnuva/'ya."""
    from datetime import UTC, datetime

    from tradebot.arastirma import turnuva as tv
    from tradebot.arastirma.defter import Defter
    from tradebot.veri import enstruman as en
    from tradebot.veri.depo import BarDepo

    a, m = _veri_baglam()
    kayitci = log("turnuva")
    d = tv.dalga_oku(Path(dosya))
    defter = Defter(m)
    for aile, p in d["planlar"].items():
        try:
            defter.plan_ac(p["kimlik"], aile, " ".join(p["hipotez"].split()), {"dosya": str(dosya), "dalga": d["dalga"]},
                           sorted(d["gruplar"]), f"{dosya} → olcut {d['olcut']} (A/B/KALDI, turnuva.karar)")
            kayitci.info("plan_acildi", plan=p["kimlik"])
        except ValueError:
            pass  # plan zaten açık: aynı ön kayıtla devam
    kayit = {k["kimlik"]: k for k in en.hepsi(m)}
    depo = BarDepo(a.veri_dizini)
    bit_ms = int(datetime.fromisoformat(d["veri_bitis"]).replace(tzinfo=UTC).timestamp() * 1000)
    cikti = Path(a.veri_dizini) / "turnuva" / f"dalga{d['dalga']}"
    sec = lambda s: {x.strip() for x in s.split(",") if x.strip()}  # noqa: E731
    gs, ss, zs = sec(grup), sec(strateji), sec(zd)
    hazir: dict = {}
    for k in sorted(tv.kollar(d), key=lambda x: (x["grup"], x["zd"])):  # grup verisi bir kez yüklensin
        if (gs and k["grup"] not in gs) or (ss and k["strateji"] not in ss) or (zs and k["zd"] not in zs):
            continue
        kol = tv.kol_kimligi(k["strateji"], k["grup"], k["zd"]) + ("+jev" if d["_ayar"].jev_veto else "")
        if (cikti / f"{kol.replace('@', '__')}.json").exists() and not tekrar:
            continue
        anahtar = (k["grup"], k["zd"])
        try:
            if anahtar not in hazir:
                hazir.clear()  # bellek: aynı anda tek grup
                vetolar = None
                if d["_ayar"].jev_veto:
                    from tradebot.zeka.olay import tum_vetolar

                    vetolar = tum_vetolar(m)
                hazir[anahtar] = tv.grup_hazirla(depo, kayit, d["gruplar"][k["grup"]], k["zd"], bit_ms=bit_ms, vetolar=vetolar)
            t0 = time.perf_counter()
            r = tv.kol_kos(defter, hazir[anahtar], k["plan"], k["strateji"], k["grup"], k["izgara"], k["yon"], d["_ayar"],
                           veri_etiketi=f"bitis {d['veri_bitis']}", en_fazla=k["en_fazla"])
        except FileNotFoundError as ex:
            kayitci.warning("kol_verisi_yok", kol=kol, hata=str(ex)[:200])
            continue
        tv.sonuc_yaz(r, cikti)
        e, w = r["en_iyi"], r["walk_forward"]
        kayitci.info("kol_bitti", kol=kol, karar=r["karar"], puan=round(e["puan"], 5), sharpe=round(e["sharpe"], 2),
                     dd=round(e["en_kotu_dusus"], 3), dsr=round(r["dsr"].get("dsr", float("nan")), 3),
                     oos_yillik=round(w.get("oos_yillik", float("nan")), 3), sn=round(time.perf_counter() - t0, 1))
        typer.echo(f"{r['karar']:<6}{kol:<44} puan {e['puan'] * 100:+.3f}%/hf  Sharpe {e['sharpe']:.2f}  "
                   f"DD {e['en_kotu_dusus'] * 100:.0f}%  DSR {r['dsr'].get('dsr', float('nan')):.2f}  "
                   f"OOS {w.get('oos_yillik', float('nan')) * 100:+.1f}%/yıl")


@arastirma_uygulama.command("carry")
def arastirma_carry(dosya: str = typer.Option("config/turnuva/dalga1b.yaml")) -> None:
    """Kripto funding carry kolu (dalga 1b)."""
    import hashlib
    from datetime import UTC, datetime

    import polars as pl

    from tradebot.arastirma import turnuva as tv
    from tradebot.arastirma.defter import Defter
    from tradebot.arastirma.maliyet import model

    a, m = _veri_baglam()
    d = tv.dalga_oku(Path(dosya))
    defter = Defter(m)
    p = d["planlar"]["carry"]
    try:
        defter.plan_ac(p["kimlik"], "carry", " ".join(p["hipotez"].split()), d["izgara"],
                       [f"BINANCE-UM:{s}" for s in d["semboller"]], f"{dosya} → olcut {d['olcut']} (en fazla B)")
    except ValueError:
        pass
    kok = Path(a.veri_dizini) / "funding"
    yollar = {s: kok / f"{s}.parquet" for s in d["semboller"] if (kok / f"{s}.parquet").exists()}
    if not yollar:
        raise typer.BadParameter(f"funding verisi yok: {kok}")
    h = hashlib.sha256("|".join(f"{s}:{hashlib.sha256(y.read_bytes()).hexdigest()}" for s, y in yollar.items())
                       .encode()).hexdigest()
    bit_ms = int(datetime.fromisoformat(d["veri_bitis"]).replace(tzinfo=UTC).timestamp() * 1000)
    r = tv.carry_kol_kos(defter, p["kimlik"], {s: pl.read_parquet(y) for s, y in yollar.items()}, d["izgara"], d["_ayar"],
                         model("BINANCE", "kripto").taraf_bps(), h, bit_ms=bit_ms, notional=d["notional"],
                         veri_etiketi=f"bitis {d['veri_bitis']}")
    tv.sonuc_yaz(r, Path(a.veri_dizini) / "turnuva" / f"dalga{d['dalga']}")
    e, w = r["en_iyi"], r["walk_forward"]
    typer.echo(f"{r['karar']:<6}{r['kol']:<44} puan {e['puan'] * 100:+.3f}%/hf  yıllık {e['yillik_bilesik'] * 100:.1f}%  "
               f"Sharpe {e['sharpe']:.2f}  DD {e['en_kotu_dusus'] * 100:.0f}%  DSR {r['dsr'].get('dsr', float('nan')):.2f}  "
               f"OOS {w.get('oos_yillik', float('nan')) * 100:+.1f}%/yıl  ({len(yollar)} coin)")


@arastirma_uygulama.command("sonlandir")
def arastirma_sonlandir(dosya: str = typer.Option("config/turnuva/dalga1.yaml")) -> None:
    """Dalga bitince: her kolun DSR'ını ailenin nihai deneme sayısıyla yeniden hesaplar ve kararı yeniler."""
    from tradebot.arastirma import turnuva as tv
    from tradebot.arastirma.defter import Defter

    a, m = _veri_baglam()
    d = tv.dalga_oku(Path(dosya))
    defter = Defter(m)
    dizin = Path(a.veri_dizini) / "turnuva" / f"dalga{d['dalga']}"
    for p in sorted(dizin.glob("*.json")):
        r = tv.dsr_sonlandir(defter, json.loads(p.read_text(encoding="utf-8")), d["_ayar"].olcut)
        tv.sonuc_yaz(r, dizin)
        typer.echo(f"{r['karar']:<6}{r['kol']:<44} DSR {r['dsr_kosu'].get('dsr', float('nan')):.3f} → "
                   f"{r['dsr'].get('dsr', float('nan')):.3f} (deneme {r['dsr'].get('deneme')})")


@arastirma_uygulama.command("portfoy")
def arastirma_portfoy(
    dalgalar: str = typer.Option("1,1b", help="Virgüllü dalga adları"),
    kararlar: str = typer.Option("A,B", help="Birleştirilecek karar sınıfları"),
    kollar: str = typer.Option("", help="Yalnız bu kollar (virgüllü; kararları ezer)"),
) -> None:
    """Seçilen kolların walk-forward OOS haftalık serilerini eşit riskle birleştirir (Faz 7 dağıtıcı önizlemesi)."""
    from tradebot.arastirma import portfoy as pf

    a = ayarlar()
    secili = {x.strip() for x in kollar.split(",") if x.strip()}
    ks = {x.strip() for x in kararlar.split(",") if x.strip()}
    seriler, maruziyet = {}, {}
    for dl in dalgalar.split(","):
        for p in sorted((Path(a.veri_dizini) / "turnuva" / f"dalga{dl.strip()}").glob("*.json")):
            r = json.loads(p.read_text(encoding="utf-8"))
            if (secili and r["kol"] not in secili) or (not secili and r["karar"] not in ks):
                continue
            if "oos" in r.get("haftalik", {}):
                seriler[r["kol"]] = r["haftalik"]["oos"]
                maruziyet[r["kol"]] = r["en_iyi"]["maruziyet"]
    if not seriler:
        raise typer.BadParameter("seçime uyan (haftalık OOS serisi olan) kol yok")
    _yazdir(pf.birlestir(seriler, maruziyet))


@arastirma_uygulama.command("rapor")
def arastirma_rapor(
    dalga: int = typer.Option(1), md: str = typer.Option("", help="Markdown tablo çıktısı (ör. docs/turnuva/...)"),
) -> None:
    """Dalganın kol sonuçlarından puan tablosu (karar, puan, Sharpe, DD, DSR, OOS, stres)."""
    a = ayarlar()
    dizin = Path(a.veri_dizini) / "turnuva" / f"dalga{dalga}"
    satirlar = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(dizin.glob("*.json"))]
    sira = {"A": 0, "B": 1, "KALDI": 2}
    satirlar.sort(key=lambda r: (sira[r["karar"]], -r["en_iyi"]["puan"]))
    bas = ("| Karar | Kol | En iyi varyant | Puan %/hf | Yıllık | Sharpe | DD | Kötü hf | DSR | Plato | OOS yıllık | "
           "OOS DD | Yıl + | 2x maliyet | Gecikme |")
    out = [bas, "|" + " --- |" * (bas.count("|") - 1)]
    for r in satirlar:
        e, w, s = r["en_iyi"], r["walk_forward"], r["stres"]
        out.append(f"| {r['karar']} | {r['kol']} | {e['varyant'].split('/', 1)[1]} | {e['puan'] * 100:.3f} | "
                   f"{e['yillik_bilesik'] * 100:.1f}% | {e['sharpe']:.2f} | {e['en_kotu_dusus'] * 100:.0f}% | "
                   f"{e['en_kotu_hafta'] * 100:.1f}% | {r['dsr'].get('dsr', float('nan')):.2f} | "
                   f"{'var' if r['plato']['plato_var'] else 'yok'} | {w.get('oos_yillik', float('nan')) * 100:.1f}% | "
                   f"{w.get('oos_en_kotu_dusus', float('nan')) * 100:.0f}% | {r['yil_pozitif_orani'] * 100:.0f}% | "
                   f"{s['maliyet_2x_yillik'] * 100:.1f}% | {s['gecikme_yillik'] * 100:.1f}% |")
    metin = "\n".join(out)
    if md:
        md.parent.mkdir(parents=True, exist_ok=True)
        md.write_text(metin + "\n", encoding="utf-8")
    typer.echo(metin)


@zeka_uygulama.command("tur")
def zeka_tur() -> None:
    """Tek tur: yeni metinleri topla, rolleri çalıştır, olayları yaz."""
    from tradebot.zeka.servis import kur as zeka_kur

    a, m = _veri_baglam()
    _yazdir(zeka_kur(m, a).tur())


@zeka_uygulama.command("geri-doldur")
def zeka_geri_doldur(
    katalog: str = typer.Option("161", help="Virgüllü Binance katalogları (161 delist)"),
    sayfa: int = typer.Option(40, help="Katalog başına en çok sayfa (20 duyuru/sayfa; boş sayfada durur)"),
) -> None:
    """Geçmiş duyuruları toplar ve A1 ile yargılar. Olaylar yayın + 60 sn'de geçerli (point-in-time)."""
    from tradebot.metin.binance_duyuru import BinanceDuyuru
    from tradebot.veri.depo import HamDepo
    from tradebot.zeka.servis import kur as zeka_kur

    a, m = _veri_baglam()
    yeni = BinanceDuyuru(HamDepo(a.veri_dizini, m), m).topla([int(x) for x in katalog.split(",")], sayfa)
    _yazdir({"yeni_metin": len(yeni), "olay": zeka_kur(m, a).isle("binance_duyuru")})


@zeka_uygulama.command("kap-geri-doldur")
def zeka_kap_geri_doldur(
    bas: str = typer.Option(..., help="İlk gün (YYYY-AA-GG, Türkiye takvimi)"),
    bit: str = typer.Option("", help="Son gün (boş: bugün)"),
    yargila: bool = typer.Option(True, help="Toplanan bildirimleri A2 ile yargıla"),
) -> None:
    """Geçmiş KAP bildirimlerini gün gün toplar (kaldığı yerden devam eder) ve A2 ile yargılar."""
    from datetime import date, timedelta

    from tradebot.metin.kap import KapBildirim
    from tradebot.veri.depo import HamDepo
    from tradebot.zeka.servis import kur as zeka_kur

    a, m = _veri_baglam()
    t = KapBildirim(HamDepo(a.veri_dizini, m), m, aralik_sn=3.0, deneme=6)
    g, son = date.fromisoformat(bas), (date.fromisoformat(bit) if bit else date.today())
    kayitci, toplam = log("zeka.kap"), 0
    while g <= son:
        n = len(t.topla([g]))
        toplam += n
        kayitci.info("kap_gun", gun=g.isoformat(), yeni=n)
        g += timedelta(days=1)
    # Onarım: alınamayan bildirimlerin günleri en çok 3 tur yeniden gezilir (bilinenler atlanır, yalnız delikler iner).
    # Bunsuz her başarısız bildirim geçmişte kalıcı delik olurdu (2026-09-27 denetimi: 24 saatte 72).
    for tur in range(3):
        gunler = sorted({x for x, _ in t.alinamayan})
        if not gunler:
            break
        t.alinamayan = []
        for x in gunler:
            toplam += len(t.topla([x]))
        kayitci.info("kap_onarim_turu", tur=tur + 1, gun=len(gunler), kalan=len(t.alinamayan))
    _yazdir({"yeni_metin": toplam, "alinamayan": [f"{x.isoformat()}:{no}" for x, no in t.alinamayan],
             "olay": zeka_kur(m, a).isle("kap") if yargila else 0})


@zeka_uygulama.command("belirsizleri-yukselt")
def zeka_belirsizleri_yukselt() -> None:
    """Yükseltme modeli yokken belirsiz kalan A1 kararlarını yükseltme modeline sorar; yalnız veto ekler."""
    from tradebot.zeka.servis import kur as zeka_kur

    a, m = _veri_baglam()
    _yazdir(zeka_kur(m, a).belirsizleri_yukselt())


@zeka_uygulama.command("veto-kaldir")
def zeka_veto_kaldir(
    veto_id: int = typer.Argument(..., help="Kaldırılacak veto olayının id'si"),
    neden: str = typer.Option(..., help="Gerekçe (ör. etiket: yalnız X/TUSD kaldırıldı)"),
    onay: str = typer.Option(..., help="Onay veren ve tarihi (kural 7: riski artırır)"),
    geriye_donuk: bool = typer.Option(False, help="Vetonun kendi anından kaldır (yanlış yargı; backtest hiç görmez)"),
) -> None:
    """Yanlış bir vetoyu kaldırır (silmez; `kaldir` olayı ekler). Otomatik yol yok, yalnız onayla elle."""
    from sqlalchemy import select

    from tradebot.db import olay as olay_t
    from tradebot.zeka import olay

    _, m = _veri_baglam()
    with m.connect() as b:
        v = b.execute(select(olay_t).where(olay_t.c.id == veto_id)).one()
    an = int(v.gecerli_ms) if geriye_donuk else int(time.time() * 1000)
    typer.echo(f"kaldır id={olay.kaldir(m, veto_id, an, neden, onay)}: {v.enstruman} ({v.neden[:100]})")


@zeka_uygulama.command("calis")
def zeka_calis(dongu: int = typer.Option(0, help="Saniye; 0 ise config/zeka.yaml dongu_sn")) -> None:
    """Servis döngüsü: her turda topla → yargıla → olay yaz. Bir turun hatası servisi durdurmaz."""
    from tradebot.zeka.servis import kur as zeka_kur

    a, m = _veri_baglam()
    z = zeka_kur(m, a)
    kayitci = log("zeka")
    bekle = dongu or int(z.ayar.get("dongu_sn", 60))
    from tradebot.zeka import nabiz

    while True:
        try:
            r = z.tur()
            simdi = int(time.time() * 1000)
            nabiz.yaz(a.veri_dizini, simdi, r.pop("basarili"), *z.jev_son(simdi))   # paper "habere kör" modu okur
            if r["yeni_metin"] or r["olay"]:
                kayitci.info("zeka_turu", **r)
        except Exception as e:  # noqa: BLE001 — servis ayakta kalır, hata log'a (nabız yazılmaz: paper kör olur)
            kayitci.error("zeka_tur_hatasi", hata=f"{type(e).__name__}: {e}"[:300])
        time.sleep(bekle)


@zeka_uygulama.command("vetolar")
def zeka_vetolar() -> None:
    """Şu an geçerli veto listesi ve son olaylar."""
    from sqlalchemy import select

    from tradebot.db import olay as olay_t
    from tradebot.zeka import olay

    _, m = _veri_baglam()
    simdi = int(time.time() * 1000)
    typer.echo("aktif veto: " + ", ".join(sorted(olay.aktif_vetolar(m, simdi))))
    with m.connect() as b:
        for r in b.execute(select(olay_t).order_by(olay_t.c.id.desc()).limit(20)):
            typer.echo(f"{r.id:>5} {r.tur:<6} {r.enstruman:<22} {r.neden[:110]}")


@paper_uygulama.command("calis")
def paper_calis(
    sure_sn: float = typer.Option(0, help="Saniye; 0 = süresiz (servis)"),
    duman: bool = typer.Option(False, help="Duman testi: defter ayrı SQLite dosyasında, canlı bar deposu ayrı dizinde"),
) -> None:
    """Paper düğümü: Binance canlı veri + sandbox yürütme; kararlar, emirler ve dolumlar paper defterine."""
    from tradebot.canli.dugum import calistir

    calistir(sure_sn or None, duman)


@paper_uygulama.command("kilit")
def paper_kilit(
    sure_sn: float = typer.Option(0, help="Saniye; 0 = süresiz (servis)"),
    tek: bool = typer.Option(False, help="Tek tur çalıştır ve sonucu yazdır"),
) -> None:
    """Kilit açılımı kolu düğümü (Dalga 6b): günde bir karar 00:05 UTC, saatte bir işaret (compose `kilit`)."""
    from tradebot.canli import kilit

    if tek:
        import os

        from tradebot.canli.defter import PaperDefter
        from tradebot.veri.depo import HamDepo
        from tradebot.veri.http import NazikIstemci

        a, m = _veri_baglam()
        d = kilit.KilitDugumu(PaperDefter(m, os.environ.get("TRADEBOT_KOD_SURUMU", "yerel")), kilit.ayarlar(),
                              kilit.Borsa(NazikIstemci("kilit", deneme=3, zaman_asimi=60).al, HamDepo(a.veri_dizini, m)))
        d.ac()
        _yazdir(d.tur())
        return
    kilit.calistir(sure_sn or None)


@paper_uygulama.command("doviz")
def paper_doviz(
    sure_sn: float = typer.Option(0, help="Saniye; 0 = süresiz (servis)"),
    tek: bool = typer.Option(False, help="Tek tur çalıştır ve sonucu yazdır"),
) -> None:
    """Döviz taşıma kolu düğümü (Dalga 9 gözlem kolu): NCM forex DEMO hesabında MT5 emri; iş günü 07:00 UTC karar,
    saatte bir işaret + taşıma tahakkuku (compose `doviz`)."""
    from tradebot.canli import doviz

    if tek:
        import os

        from tradebot.canli.defter import PaperDefter
        from tradebot.mt5.istemci import Mt5Istemci
        from tradebot.veri import faiz
        from tradebot.veri.depo import HamDepo
        from tradebot.veri.http import NazikIstemci

        a, m = _veri_baglam()
        http = NazikIstemci("oecd", zaman_asimi=120)
        kaynak = doviz.Kaynak(Mt5Istemci(a.mt5_kopru_forex), lambda: http.al(faiz.URL.format(ulkeler="+".join(faiz.ULKELER))),
                              HamDepo(a.veri_dizini, m))
        d = doviz.DovizDugumu(PaperDefter(m, os.environ.get("TRADEBOT_KOD_SURUMU", "yerel")), doviz.ayarlar(), kaynak)
        d.ac()
        _yazdir(d.tur())
        return
    doviz.calistir(sure_sn or None)


@paper_uygulama.command("dagitim")
def paper_dagitim(hafta: int = typer.Option(0, help="Kaç hafta önce (0 = bu hafta)")) -> None:
    """Portföy kolunun haftalık sermaye dağıtımı (paper_dagitim; yoksa hafta başına kadarki defterle hesaplanıp yazılır)."""
    import time

    from tradebot.canli import dagitici as dg
    from tradebot.canli.defter import PaperDefter
    from tradebot.canli.kollar import PORTFOY, kollar
    from tradebot.db import motor as db_motor

    ks = kollar()
    pf = next(k for k in ks if k.strateji == PORTFOY)
    h = dg.hafta_basi(int(time.time() * 1000)) - hafta * dg.HAFTA_MS
    defter = PaperDefter(db_motor(ayarlar()), "cli")
    _yazdir(defter.dagitim_getir(pf, [k for k in ks if k.ad in pf.parametre["kaynaklar"]], h))


@paper_uygulama.command("acil-kaldir")
def paper_acil_kaldir(
    kol: str = typer.Option(..., help="Kol adı (ör. portfoy@kripto_btc_eth)"),
    onaylayan: str = typer.Option(..., help="Onaylayan kişi (Scryne)"),
    gerekce: str = typer.Option(..., help="Neden yeniden başlatılıyor"),
) -> None:
    """Acil durdurmayı kaldırır (kural 7: yalnız Scryne'ın açık onayıyla; otomatik yol yok). Olay deftere ve denetim
    izine yazılır; çalışan düğüm bir sonraki saat kapanışında uygular."""
    from tradebot import denetim
    from tradebot.canli.defter import PaperDefter
    from tradebot.canli.kollar import kollar
    from tradebot.db import motor as db_motor
    from tradebot.risk.motor import Durum

    if not onaylayan.strip() or not gerekce.strip():
        raise typer.BadParameter("onaylayan ve gerekçe zorunlu")
    k = next((x for x in kollar() if x.ad == kol), None)
    if k is None:
        raise typer.BadParameter(f"kol yok: {kol}")
    m = db_motor(ayarlar())
    defter = PaperDefter(m, "cli")
    d = defter.durum(k)
    if d.izleyici is None or d.izleyici.durum != Durum.ACIL_DURDURMA:
        raise typer.BadParameter(f"{kol} acil durdurmada değil")
    oid = defter.kol_olay_yaz(kol, "acil_kaldir", {"onaylayan": onaylayan, "gerekce": gerekce})
    denetim.kaydet(m, "paper", "acil_durdurma_kaldirildi", {"kol": kol, "onaylayan": onaylayan, "gerekce": gerekce,
                                                           "olay_id": oid})
    typer.echo(f"{kol}: acil durdurma kaldırma olayı yazıldı (olay {oid}); düğüm sonraki kapanışta uygular.")


@paper_uygulama.command("rapor")
def paper_rapor(hafta: int = typer.Option(1, help="Kaç hafta önce (1 = geçen hafta, 0 = bu hafta, yarım)")) -> None:
    """Haftalık paper raporu (defterden): Markdown'ı yazdırır ve data/rapor/ altına kaydeder."""
    import time

    from tradebot.canli import dagitici as dg
    from tradebot.canli import rapor
    from tradebot.db import motor as db_motor

    a = ayarlar()
    h = dg.hafta_basi(int(time.time() * 1000)) - hafta * dg.HAFTA_MS
    _, md, yol = rapor.uret(db_motor(a), a.veri_dizini, h)
    typer.echo(md)
    typer.echo(f"→ {yol}")


telegram_uygulama = typer.Typer(help="Telegram botu (Faz 9, D4): doğal dil sorgu, onaylı durdurma", no_args_is_help=True)
uygulama.add_typer(telegram_uygulama, name="telegram")


@telegram_uygulama.command("calis")
def telegram_calis() -> None:
    """Uzun yoklamayla Telegram botu (compose `telegram`); yalnız TRADEBOT_TELEGRAM_SOHBET'e cevap verir."""
    from tradebot.telegram_bot import calistir

    kur(ayarlar())
    calistir()


pano_uygulama = typer.Typer(help="Web pano (Faz 10): salt okunur, yalnız Tailscale", no_args_is_help=True)
uygulama.add_typer(pano_uygulama, name="pano")


@pano_uygulama.command("calis")
def pano_calis(
    port: int = typer.Option(8080, help="Dinlenecek port"),
    adres: str = typer.Option("0.0.0.0", help="Konteyner içinde tüm arayüzler; compose portu yalnız 127.0.0.1'e açar"),
    arayuz: str = typer.Option("pano/dist", help="Derlenmiş arayüz dizini (vite build)"),
    ornek: bool = typer.Option(False, help="Yerel geliştirme: sentetik SQLite veriyle çalış (canlıya dokunmaz)"),
) -> None:
    """Pano sunucusu (compose `pano`)."""
    import uvicorn

    from tradebot.pano.sunucu import uygulama as pano_app

    a = ayarlar()
    kur(a)
    if ornek:
        import tempfile

        from tradebot.pano.ornek import kur as ornek_kur

        dizin = Path(tempfile.mkdtemp(prefix="pano_ornek_"))
        m = ornek_kur(f"sqlite:///{dizin / 'ornek.db'}", int(time.time() * 1000), veri_dizini=dizin)
        a = a.model_copy(update={"veri_dizini": dizin})

        from tradebot.pano.sunucu import SaglikOnbellek
        from tradebot.saglik import Sonuc

        saglik_ = SaglikOnbellek(a, kontrol=lambda _a: [
            Sonuc("dns", "OK", "en yavaş data.binance.vision 0.42 sn"), Sonuc("saat", "OK", "en büyük kayma +0.017 sn"),
            Sonuc("veritabani", "OK", "PostgreSQL 17 · zincir sağlam"), Sonuc("disk", "OK", "boş 980 GB"),
            Sonuc("sirlar", "OK", "tümü tanımlı"), Sonuc("paper", "OK", "son özkaynak işareti 8 dk önce"),
            Sonuc("gece_isi", "UYARI", "son gece işi kaydı 27 saat önce"), Sonuc("yedek", "OK", "son yedek 9 saat önce"),
            Sonuc("mt5", "OK", "forex bağlı · viop bağlı")])
    else:
        from tradebot.db import motor as db_motor

        m = db_motor(a)
        saglik_ = None
    app = pano_app(m, a, Path(arayuz), saglik_onbellek=saglik_)
    uvicorn.run(app, host=adres, port=port, log_level="warning")
