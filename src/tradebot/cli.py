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
