"""deneme defteri: test_plani, deneme

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-25
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

JSONT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
KIMLIK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "test_plani",
        sa.Column("kimlik", sa.String(128), primary_key=True),
        sa.Column("zaman", sa.DateTime(timezone=True), nullable=False),
        sa.Column("aile", sa.String(64), nullable=False),
        sa.Column("hipotez", sa.String(2000), nullable=False),
        sa.Column("izgara", JSONT, nullable=False),
        sa.Column("piyasalar", JSONT, nullable=False),
        sa.Column("olcut", sa.String(2000), nullable=False),
        sa.Column("kod_surumu", sa.String(64), nullable=False),
        sa.Column("durum", sa.String(16), nullable=False),
        sa.Column("sonuc", sa.String(4000)),
    )
    op.create_table(
        "deneme",
        sa.Column("id", KIMLIK, primary_key=True, autoincrement=True),
        sa.Column("zaman", sa.DateTime(timezone=True), nullable=False),
        sa.Column("plan", sa.String(128), nullable=False),
        sa.Column("tur", sa.String(16), nullable=False),
        sa.Column("strateji", sa.String(256), nullable=False),
        sa.Column("aile", sa.String(64), nullable=False),
        sa.Column("parametreler", JSONT, nullable=False),
        sa.Column("enstruman", sa.String(64), nullable=False),
        sa.Column("zaman_dilimi", sa.String(8), nullable=False),
        sa.Column("veri_hash", sa.String(64), nullable=False),
        sa.Column("kod_surumu", sa.String(64), nullable=False),
        sa.Column("metrik", JSONT, nullable=False),
        sa.Column("sure_sn", sa.Float, nullable=False),
    )
    op.create_index("ix_deneme_aile_tur", "deneme", ["aile", "tur"])
    op.create_index("ix_deneme_plan", "deneme", ["plan"])
    if op.get_bind().dialect.name == "postgresql":
        # Deneme defteri yalnız eklenir: sonuca bakıp kaydı değiştirmek/silmek veritabanı düzeyinde reddedilir.
        op.execute("""
            CREATE OR REPLACE FUNCTION deneme_degismez() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION 'deneme defteri yalnız eklenebilir (%)', TG_OP; END; $$ LANGUAGE plpgsql;
        """)
        op.execute("""CREATE TRIGGER deneme_degismez BEFORE UPDATE OR DELETE ON deneme
                      FOR EACH ROW EXECUTE FUNCTION deneme_degismez();""")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        op.execute("DROP TRIGGER IF EXISTS deneme_degismez ON deneme")
        op.execute("DROP FUNCTION IF EXISTS deneme_degismez()")
    op.drop_index("ix_deneme_plan", table_name="deneme")
    op.drop_index("ix_deneme_aile_tur", table_name="deneme")
    op.drop_table("deneme")
    op.drop_table("test_plani")
