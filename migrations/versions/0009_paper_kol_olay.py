"""paper_kol_olay: kol durum olayları (durdur, acil_kaldir, terfi; yalnız eklenir)

Revision ID: 0009
Revises: 0008
Create Date: 2026-09-27
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

JSONT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
KIMLIK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "paper_kol_olay",
        sa.Column("id", KIMLIK, primary_key=True, autoincrement=True),
        sa.Column("kol", sa.String(96), nullable=False),
        sa.Column("zaman_ms", sa.BigInteger, nullable=False),
        sa.Column("tur", sa.String(16), nullable=False),
        sa.Column("kod_surumu", sa.String(64), nullable=False),
        sa.Column("ayrinti", JSONT, nullable=False),
    )
    op.create_index("ix_paper_kol_olay_kol", "paper_kol_olay", ["kol", "zaman_ms"])
    if op.get_bind().dialect.name == "postgresql":  # yalniz_ekle() fonksiyonu göç 0004'te
        op.execute("CREATE TRIGGER paper_kol_olay_yalniz_ekle BEFORE UPDATE OR DELETE ON paper_kol_olay "
                   "FOR EACH ROW EXECUTE FUNCTION yalniz_ekle();")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS paper_kol_olay_yalniz_ekle ON paper_kol_olay")
    op.drop_index("ix_paper_kol_olay_kol", "paper_kol_olay")
    op.drop_table("paper_kol_olay")
