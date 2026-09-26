"""metin.meta: kaynağa özgü üst bilgi (KAP: hisse kodları, konu, bildirim sınıfı)

Revision ID: 0005
Revises: 0004
Create Date: 2026-09-26
"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None

JSONT = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.add_column("metin", sa.Column("meta", JSONT))


def downgrade() -> None:
    op.drop_column("metin", "meta")
