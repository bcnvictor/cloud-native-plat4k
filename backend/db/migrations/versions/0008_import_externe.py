"""Import externe : rename origin imported->onboarded, add source_url

Revision ID: 0008
Revises: f2a8c4e1b703
Create Date: 2026-06-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = '0008'
down_revision = 'f2a8c4e1b703'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('applications', sa.Column('source_url', sa.String(), nullable=True))
    op.execute("UPDATE applications SET origin = 'onboarded' WHERE origin = 'imported'")


def downgrade() -> None:
    op.execute("UPDATE applications SET origin = 'imported' WHERE origin = 'onboarded'")
    op.drop_column('applications', 'source_url')
