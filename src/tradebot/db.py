"""Veritabanı: bağlantı ve şema (SQLAlchemy Core). Göçler Alembic ile (`migrations/`).

Canlıda PostgreSQL, testte SQLite. JSON alanı PostgreSQL'de JSONB'dir.
"""
from __future__ import annotations

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    Integer,
    MetaData,
    String,
    Table,
    create_engine,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.engine import Engine

from tradebot.ayar import Ayarlar

metadata = MetaData()
JSONT = JSON().with_variant(JSONB(), "postgresql")
# SQLite yalnız INTEGER PRIMARY KEY'i otomatik artırır
KIMLIK = BigInteger().with_variant(Integer(), "sqlite")

denetim_izi = Table(
    "denetim_izi",
    metadata,
    Column("id", KIMLIK, primary_key=True, autoincrement=True),
    Column("zaman", DateTime(timezone=True), nullable=False),
    Column("bilesen", String(64), nullable=False),
    Column("olay", String(128), nullable=False),
    Column("veri", JSONT, nullable=False),
    Column("onceki_hash", String(64), nullable=False),
    Column("hash", String(64), nullable=False, unique=True),
)


def motor(a: Ayarlar) -> Engine:
    if a.veritabani_url is None:
        raise RuntimeError("TRADEBOT_VERITABANI_URL tanımlı değil")
    return create_engine(a.veritabani_url.get_secret_value(), pool_pre_ping=True, future=True)
