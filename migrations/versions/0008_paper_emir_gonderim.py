"""paper_emir.gonderim_fiyati: emir giderken canlı orta fiyat (yürütme maliyeti ↔ gecikme kayması ayrımı)

Revision ID: 0008
Revises: 0007
Create Date: 2026-09-27
"""
import sqlalchemy as sa
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("paper_emir", sa.Column("gonderim_fiyati", sa.Float, nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("paper_emir") as b:
        b.drop_column("gonderim_fiyati")
