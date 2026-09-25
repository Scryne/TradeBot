"""Veritabanı: bağlantı ve şema (SQLAlchemy Core). Göçler Alembic ile (`migrations/`).

Canlıda PostgreSQL, testte SQLite. JSON alanı PostgreSQL'de JSONB'dir.
"""
from __future__ import annotations

from sqlalchemy import (
    JSON,
    BigInteger,
    Column,
    DateTime,
    Float,
    Index,
    Integer,
    MetaData,
    String,
    Table,
    UniqueConstraint,
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

# --- Faz 2: veri platformu ---
ham_dosya = Table(
    "ham_dosya",
    metadata,
    Column("id", KIMLIK, primary_key=True, autoincrement=True),
    Column("kaynak", String(32), nullable=False),
    Column("anahtar", String(256), nullable=False),  # kaynağa özgü mantıksal ad (ör. spot/1h/BTCUSDT/2024-01)
    Column("yol", String(512), nullable=False),
    Column("sha256", String(64), nullable=False, unique=True),
    Column("boyut", BigInteger, nullable=False),
    Column("indirildi", DateTime(timezone=True), nullable=False),
    Index("ix_ham_dosya_kaynak_anahtar", "kaynak", "anahtar"),
)

enstruman = Table(
    "enstruman",
    metadata,
    Column("kimlik", String(64), primary_key=True),  # "<PIYASA>:<SEMBOL>"
    Column("piyasa", String(32), nullable=False),
    Column("sembol", String(32), nullable=False),
    Column("sinif", String(16), nullable=False),  # kripto | fx | metal | endeks | emtia | etf | hisse
    Column("takvim", String(16), nullable=False),
    Column("para_birimi", String(8), nullable=False),
    Column("kaynak", String(32), nullable=False),
    Column("ilk_bar_ms", BigInteger),  # tarihsel evren: veride görülen ilk ve son bar (delist/listeleme)
    Column("son_bar_ms", BigInteger),
    Column("durum", String(16), nullable=False, default="aktif"),  # aktif | islem_disi
    Column("meta", JSONT, nullable=False, default=dict),  # fiyat adımı, lot, kaynak sembolü …
    Column("guncellendi", DateTime(timezone=True), nullable=False),
)

kurumsal_islem = Table(
    "kurumsal_islem",
    metadata,
    Column("id", KIMLIK, primary_key=True, autoincrement=True),
    Column("kimlik", String(64), nullable=False),
    Column("tarih_ms", BigInteger, nullable=False),  # hak kullanım (ex) günü 00:00 UTC
    Column("tur", String(16), nullable=False),  # temettu | bolunme
    Column("deger", Float, nullable=False),  # temettü: pay başına tutar; bölünme: yeni/eski pay oranı
    Column("kaynak", String(32), nullable=False),
    Column("ham_sha", String(64), nullable=False),
    UniqueConstraint("kimlik", "tarih_ms", "tur", "kaynak", name="uq_kurumsal_islem"),
)

kalite_raporu = Table(
    "kalite_raporu",
    metadata,
    Column("id", KIMLIK, primary_key=True, autoincrement=True),
    Column("zaman", DateTime(timezone=True), nullable=False),
    Column("kimlik", String(64), nullable=False),
    Column("zaman_dilimi", String(8), nullable=False),
    Column("durum", String(8), nullable=False),  # OK | UYARI | HATA
    Column("ozet", JSONT, nullable=False),
    Index("ix_kalite_raporu_kimlik", "kimlik", "zaman_dilimi"),
)


def motor(a: Ayarlar) -> Engine:
    if a.veritabani_url is None:
        raise RuntimeError("TRADEBOT_VERITABANI_URL tanımlı değil")
    return create_engine(a.veritabani_url.get_secret_value(), pool_pre_ping=True, future=True)
