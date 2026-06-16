"""drop is_admin column — derived from role property

Revision ID: cfc5e4e75804
Revises: 8df6e2b70264
Create Date: 2026-06-16

"""
from alembic import op

revision = 'cfc5e4e75804'
down_revision = '8df6e2b70264'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column('users', 'is_admin')


def downgrade() -> None:
    import sqlalchemy as sa
    op.add_column('users', sa.Column('is_admin', sa.Boolean(), nullable=False, server_default='false'))
