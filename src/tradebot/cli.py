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
