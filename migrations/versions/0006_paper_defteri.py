"""paper defteri: paper_kol, paper_karar, paper_emir, paper_emir_olay, paper_ozkaynak (yalnız eklenir)

Revision ID: 0006
Revises: 0005
Create Date: 2026-09-27
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

JSONT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
KIMLIK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")
TABLOLAR = ("paper_kol", "paper_karar", "paper_emir", "paper_emir_olay", "paper_ozkaynak")


def upgrade() -> None:
    op.create_table(
        "paper_kol",
        sa.Column("kol", sa.String(96), primary_key=True),
        sa.Column("acilis", sa.DateTime(timezone=True), nullable=False),
        sa.Column("baslangic_ms", sa.BigInteger, nullable=False),
        sa.Column("baslangic_ozkaynak", sa.Float, nullable=False),
        sa.Column("sinif", sa.String(8), nullable=False),
        sa.Column("tanim", JSONT, nullable=False),
        sa.Column("kod_surumu", sa.String(64), nullable=False),
    )
    op.create_table(
        "paper_karar",
        sa.Column("id", KIMLIK, primary_key=True, autoincrement=True),
        sa.Column("kol", sa.String(96), nullable=False),
        sa.Column("bar_ms", sa.BigInteger, nullable=False),
        sa.Column("karar_ms", sa.BigInteger, nullable=False),
        sa.Column("kod_surumu", sa.String(64), nullable=False),
        sa.Column("veri_hash", sa.String(64), nullable=False),
        sa.Column("durum", sa.String(16), nullable=False),
        sa.Column("ayrinti", JSONT, nullable=False),
        sa.UniqueConstraint("kol", "bar_ms", name="uq_paper_karar"),
    )
    op.create_table(
        "paper_emir",
        sa.Column("id", KIMLIK, primary_key=True, autoincrement=True),
        sa.Column("kol", sa.String(96), nullable=False),
        sa.Column("karar_id", sa.BigInteger),
        sa.Column("istemci_emir_id", sa.String(64), nullable=False, unique=True),
        sa.Column("enstruman", sa.String(64), nullable=False),
        sa.Column("istenen", sa.Float, nullable=False),
        sa.Column("onaylanan", sa.Float, nullable=False),
        sa.Column("karar_fiyati", sa.Float, nullable=False),
        sa.Column("zaman_ms", sa.BigInteger, nullable=False),
        sa.Column("tur", sa.String(16), nullable=False),
        sa.Column("risk", JSONT, nullable=False),
    )
    op.create_table(
        "paper_emir_olay",
        sa.Column("id", KIMLIK, primary_key=True, autoincrement=True),
        sa.Column("emir_id", sa.BigInteger, nullable=False),
        sa.Column("kol", sa.String(96), nullable=False),
        sa.Column("tur", sa.String(16), nullable=False),
        sa.Column("enstruman", sa.String(64), nullable=False),
        sa.Column("miktar", sa.Float, nullable=False),
        sa.Column("fiyat", sa.Float),
        sa.Column("ucret", sa.Float, nullable=False),
        sa.Column("zaman_ms", sa.BigInteger, nullable=False),
        sa.Column("ayrinti", JSONT, nullable=False),
    )
    op.create_index("ix_paper_emir_olay_kol", "paper_emir_olay", ["kol", "zaman_ms"])
    op.create_table(
        "paper_ozkaynak",
        sa.Column("id", KIMLIK, primary_key=True, autoincrement=True),
        sa.Column("kol", sa.String(96), nullable=False),
        sa.Column("zaman_ms", sa.BigInteger, nullable=False),
        sa.Column("ozkaynak", sa.Float, nullable=False),
        sa.Column("nakit", sa.Float, nullable=False),
        sa.Column("pozisyon", JSONT, nullable=False),
        sa.Column("fiyat", JSONT, nullable=False),
    )
    op.create_index("ix_paper_ozkaynak_kol", "paper_ozkaynak", ["kol", "zaman_ms"])
    if op.get_bind().dialect.name == "postgresql":  # yalniz_ekle() fonksiyonu göç 0004'te
        for t in TABLOLAR:
            op.execute(f"CREATE TRIGGER {t}_yalniz_ekle BEFORE UPDATE OR DELETE ON {t} "
                       "FOR EACH ROW EXECUTE FUNCTION yalniz_ekle();")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for t in TABLOLAR:
            op.execute(f"DROP TRIGGER IF EXISTS {t}_yalniz_ekle ON {t}")
    for t in reversed(TABLOLAR):
        op.drop_table(t)
