"""denetim_izi tablosu (hash zincirli, yalnız eklenen)

Revision ID: 0001
Revises:
Create Date: 2026-09-25
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "denetim_izi",
        sa.Column("id", sa.BigInteger().with_variant(sa.Integer(), "sqlite"), primary_key=True, autoincrement=True),
        sa.Column("zaman", sa.DateTime(timezone=True), nullable=False),
        sa.Column("bilesen", sa.String(64), nullable=False),
        sa.Column("olay", sa.String(128), nullable=False),
        sa.Column("veri", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False),
        sa.Column("onceki_hash", sa.String(64), nullable=False),
        sa.Column("hash", sa.String(64), nullable=False, unique=True),
    )
    op.create_index("ix_denetim_izi_zaman", "denetim_izi", ["zaman"])
    if op.get_bind().dialect.name == "postgresql":
        # Yalnız ekleme: güncelleme ve silme veritabanı düzeyinde reddedilir.
        op.execute("""
            CREATE OR REPLACE FUNCTION denetim_izi_degismez() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'denetim_izi yalnız eklenebilir (%)', TG_OP; END; $$ LANGUAGE plpgsql;
        """)
        op.execute("""
            CREATE TRIGGER denetim_izi_degismez BEFORE UPDATE OR DELETE ON denetim_izi
            FOR EACH ROW EXECUTE FUNCTION denetim_izi_degismez();
        """)


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS denetim_izi_degismez ON denetim_izi")
        op.execute("DROP FUNCTION IF EXISTS denetim_izi_degismez()")
    op.drop_index("ix_denetim_izi_zaman", table_name="denetim_izi")
    op.drop_table("denetim_izi")
