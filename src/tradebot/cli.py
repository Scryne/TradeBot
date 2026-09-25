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
    """Host/konteyner sağlığı: DNS, saat, veritabanı, disk, sırlar."""
    a = ayarlar()
    kur(a)
    kayitci = log("saglik")
    onceki: dict[str, str] = {}
    while True:
        sonuclar = saglik.hepsi(a)
        if json_cikti:
            typer.echo(json.dumps([s.__dict__ for s in sonuclar], ensure_ascii=False))
        elif not dongu:
            for s in sonuclar:
                typer.echo(f" {_ISARET[s.durum]} {s.ad:<11} {s.durum:<6} {s.ayrinti}")
        for s in sonuclar if dongu else []:  # tek seferlik komutun çıktısı temiz kalsın (--json ile)
            if onceki.get(s.ad) != s.durum:
                yaz = kayitci.info if s.durum == "OK" else kayitci.warning
                yaz("saglik_durumu", kontrol=s.ad, durum=s.durum, ayrinti=s.ayrinti)
                onceki[s.ad] = s.durum
        if not dongu:
            raise typer.Exit(saglik.cikis_kodu(sonuclar))
        time.sleep(dongu)


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


@veri_uygulama.command("dukascopy")
def veri_dukascopy(butce_dk: float = typer.Option(60.0, help="Zaman bütçesi (dakika); kalan sonraki koşuya")) -> None:
    """FX, metal, endeks, emtia (sıkı hız sınırı; kaldığı yerden devam eder)."""
    from tradebot.veri import is_akisi

    a, m = _veri_baglam()
    _yazdir(is_akisi.dukascopy(a, m, butce_dk))


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
    """Gece işi: Binance → Yahoo → Dukascopy → kalite → evren; sonuç denetim izine yazılır."""
    from tradebot.veri import is_akisi

    a, m = _veri_baglam()
    _yazdir(is_akisi.gece(a, m, dukascopy_butce_dk))


@veri_uygulama.command("zamanla")
def veri_zamanla(
    saat: str = typer.Option("01:30", help="Her gün UTC HH:MM"),
    hemen: bool = typer.Option(False, help="Başlarken bir kez hemen çalıştır"),
    dukascopy_butce_dk: float = typer.Option(240.0),
) -> None:
    """Gece işini her gün belirtilen UTC saatinde çalıştırır (servis olarak)."""
    from datetime import UTC, datetime

    from tradebot.veri import is_akisi

    a, m = _veri_baglam()
    kayitci = log("veri.zamanla")
    ss, dd = map(int, saat.split(":"))
    if hemen:
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
    for k in tv.kollar(d):
        if (gs and k["grup"] not in gs) or (ss and k["strateji"] not in ss) or (zs and k["zd"] not in zs):
            continue
        kol = tv.kol_kimligi(k["strateji"], k["grup"], k["zd"])
        if (cikti / f"{kol.replace('@', '__')}.json").exists() and not tekrar:
            continue
        anahtar = (k["grup"], k["zd"])
        try:
            if anahtar not in hazir:
                hazir.clear()  # bellek: aynı anda tek grup
                hazir[anahtar] = tv.grup_hazirla(depo, kayit, d["gruplar"][k["grup"]], k["zd"], bit_ms=bit_ms)
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
