"""Alembic göçleri boş veritabanında baştan sona çalışır ve koddaki şemayla (db.metadata) aynı tabloları üretir."""
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from tradebot import ayar as ayar_mod
from tradebot.db import metadata

KOK = Path(__file__).resolve().parents[1]


def test_goc_basa_sona_ve_semayla_uyumlu(tmp_path, monkeypatch):
    url = f"sqlite:///{(tmp_path / 'g.db').as_posix()}"
    monkeypatch.setenv("TRADEBOT_VERITABANI_URL", url)
    ayar_mod.ayarlar.cache_clear()  # ayarlar önbellekli: yeni URL okunsun, test sonunda da temizlenir
    try:
        _yukselt_ve_dogrula(url)
    finally:
        ayar_mod.ayarlar.cache_clear()


def _yukselt_ve_dogrula(url: str) -> None:
    cfg = Config(str(KOK / "alembic.ini"))
    cfg.set_main_option("script_location", str(KOK / "migrations"))
    command.upgrade(cfg, "head")
    ins = inspect(create_engine(url))
    tablolar = set(ins.get_table_names()) - {"alembic_version"}
    assert tablolar == set(metadata.tables)
    for ad, t in metadata.tables.items():
        assert {c["name"] for c in ins.get_columns(ad)} == {c.name for c in t.columns}, ad
    command.downgrade(cfg, "0003")
    assert "olay" not in inspect(create_engine(url)).get_table_names()
