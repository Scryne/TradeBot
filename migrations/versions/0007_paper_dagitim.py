"""paper_dagitim: haftalık sermaye dağıtımı (yalnız eklenir)

Revision ID: 0007
Revises: 0006
Create Date: 2026-09-27
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

JSONT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
KIMLIK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "paper_dagitim",
        sa.Column("id", KIMLIK, primary_key=True, autoincrement=True),
        sa.Column("portfoy", sa.String(96), nullable=False),
        sa.Column("hafta_ms", sa.BigInteger, nullable=False),
        sa.Column("hesap_ms", sa.BigInteger, nullable=False),
        sa.Column("kod_surumu", sa.String(64), nullable=False),
        sa.Column("kaldirac", sa.Float, nullable=False),
        sa.Column("ayrinti", JSONT, nullable=False),
        sa.UniqueConstraint("portfoy", "hafta_ms", name="uq_paper_dagitim"),
    )
    if op.get_bind().dialect.name == "postgresql":  # yalniz_ekle() fonksiyonu göç 0004'te
        op.execute("CREATE TRIGGER paper_dagitim_yalniz_ekle BEFORE UPDATE OR DELETE ON paper_dagitim "
                   "FOR EACH ROW EXECUTE FUNCTION yalniz_ekle();")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS paper_dagitim_yalniz_ekle ON paper_dagitim")
    op.drop_table("paper_dagitim")
