"""zekâ katmanı: metin, jev_yargi, olay

Revision ID: 0004
Revises: 0003
Create Date: 2026-09-26
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

JSONT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")
KIMLIK = sa.BigInteger().with_variant(sa.Integer(), "sqlite")


def upgrade() -> None:
    op.create_table(
        "metin",
        sa.Column("id", KIMLIK, primary_key=True, autoincrement=True),
        sa.Column("kaynak", sa.String(32), nullable=False),
        sa.Column("dis_kimlik", sa.String(128), nullable=False),
        sa.Column("katalog", sa.String(64)),
        sa.Column("baslik", sa.String(1000), nullable=False),
        sa.Column("govde", sa.Text, nullable=False),
        sa.Column("yayin_ms", sa.BigInteger, nullable=False),
        sa.Column("ilk_gorulme_ms", sa.BigInteger, nullable=False),
        sa.Column("ham_sha", sa.String(64), nullable=False),
        sa.UniqueConstraint("kaynak", "dis_kimlik", name="uq_metin"),
    )
    op.create_index("ix_metin_yayin", "metin", ["yayin_ms"])
    op.create_table(
        "jev_yargi",
        sa.Column("id", KIMLIK, primary_key=True, autoincrement=True),
        sa.Column("zaman", sa.DateTime(timezone=True), nullable=False),
        sa.Column("rol", sa.String(32), nullable=False),
        sa.Column("saglayici", sa.String(16), nullable=False),
        sa.Column("model_istenen", sa.String(128), nullable=False),
        sa.Column("model_cozulen", sa.String(128)),
        sa.Column("soru_sha", sa.String(64), nullable=False),
        sa.Column("girdi_sha", sa.String(64), nullable=False),
        sa.Column("hedef", sa.String(256), nullable=False),
        sa.Column("cevap", JSONT),
        sa.Column("gecikme_ms", sa.Float),
        sa.Column("girdi_token", sa.Integer),
        sa.Column("hata", sa.String(500)),
    )
    op.create_index("ix_jev_yargi_anahtar", "jev_yargi", ["soru_sha", "girdi_sha"])
    op.create_table(
        "olay",
        sa.Column("id", KIMLIK, primary_key=True, autoincrement=True),
        sa.Column("zaman", sa.DateTime(timezone=True), nullable=False),
        sa.Column("tur", sa.String(16), nullable=False),
        sa.Column("enstruman", sa.String(64), nullable=False),
        sa.Column("gecerli_ms", sa.BigInteger, nullable=False),
        sa.Column("bitis_ms", sa.BigInteger),
        sa.Column("neden", sa.String(500), nullable=False),
        sa.Column("rol", sa.String(32), nullable=False),
        sa.Column("metin_id", sa.BigInteger),
        sa.Column("yargi_id", sa.BigInteger),
        sa.Column("ayrinti", JSONT, nullable=False),
    )
    op.create_index("ix_olay_enstruman", "olay", ["enstruman", "gecerli_ms"])
    if op.get_bind().dialect.name == "postgresql":
        # Yargılar ve olaylar yalnız eklenir (dondurma: backtest aynı kaydı okur; sonradan düzeltme yeni kayıttır)
        op.execute("""
            CREATE OR REPLACE FUNCTION yalniz_ekle() RETURNS trigger AS $$
            BEGIN RAISE EXCEPTION '% yalnız eklenebilir (%)', TG_TABLE_NAME, TG_OP; END; $$ LANGUAGE plpgsql;
        """)
        for t in ("jev_yargi", "olay"):
            op.execute(f"CREATE TRIGGER {t}_yalniz_ekle BEFORE UPDATE OR DELETE ON {t} "
                       "FOR EACH ROW EXECUTE FUNCTION yalniz_ekle();")


def downgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        for t in ("jev_yargi", "olay"):
            op.execute(f"DROP TRIGGER IF EXISTS {t}_yalniz_ekle ON {t}")
        op.execute("DROP FUNCTION IF EXISTS yalniz_ekle()")
    op.drop_table("olay")
    op.drop_table("jev_yargi")
    op.drop_table("metin")
