"""veri platformu: ham_dosya, enstruman, kurumsal_islem, kalite_raporu

Revision ID: 0002
Revises: 0001
Create Date: 2026-09-25
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None

JSONT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
KIMLIK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "ham_dosya",
        sa.Column("id", KIMLIK, primary_key=True, autoincrement=True),
        sa.Column("kaynak", sa.String(32), nullable=False),
        sa.Column("anahtar", sa.String(256), nullable=False),
        sa.Column("yol", sa.String(512), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False, unique=True),
        sa.Column("boyut", sa.BigInteger, nullable=False),
        sa.Column("indirildi", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ham_dosya_kaynak_anahtar", "ham_dosya", ["kaynak", "anahtar"])
    op.create_table(
        "enstruman",
        sa.Column("kimlik", sa.String(64), primary_key=True),
        sa.Column("piyasa", sa.String(32), nullable=False),
        sa.Column("sembol", sa.String(32), nullable=False),
        sa.Column("sinif", sa.String(16), nullable=False),
        sa.Column("takvim", sa.String(16), nullable=False),
        sa.Column("para_birimi", sa.String(8), nullable=False),
        sa.Column("kaynak", sa.String(32), nullable=False),
        sa.Column("ilk_bar_ms", sa.BigInteger),
        sa.Column("son_bar_ms", sa.BigInteger),
        sa.Column("durum", sa.String(16), nullable=False),
        sa.Column("meta", JSONT, nullable=False),
        sa.Column("guncellendi", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "kurumsal_islem",
        sa.Column("id", KIMLIK, primary_key=True, autoincrement=True),
        sa.Column("kimlik", sa.String(64), nullable=False),
        sa.Column("tarih_ms", sa.BigInteger, nullable=False),
        sa.Column("tur", sa.String(16), nullable=False),
        sa.Column("deger", sa.Float, nullable=False),
        sa.Column("kaynak", sa.String(32), nullable=False),
        sa.Column("ham_sha", sa.String(64), nullable=False),
        sa.UniqueConstraint("kimlik", "tarih_ms", "tur", "kaynak", name="uq_kurumsal_islem"),
    )
    op.create_table(
        "kalite_raporu",
        sa.Column("id", KIMLIK, primary_key=True, autoincrement=True),
        sa.Column("zaman", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kimlik", sa.String(64), nullable=False),
        sa.Column("zaman_dilimi", sa.String(8), nullable=False),
        sa.Column("durum", sa.String(8), nullable=False),
        sa.Column("ozet", JSONT, nullable=False),
    )
    op.create_index("ix_kalite_raporu_kimlik", "kalite_raporu", ["kimlik", "zaman_dilimi"])


def downgrade() -> None:
    op.drop_index("ix_kalite_raporu_kimlik", table_name="kalite_raporu")
    op.drop_table("kalite_raporu")
    op.drop_table("kurumsal_islem")
    op.drop_table("enstruman")
    op.drop_index("ix_ham_dosya_kaynak_anahtar", table_name="ham_dosya")
    op.drop_table("ham_dosya")
