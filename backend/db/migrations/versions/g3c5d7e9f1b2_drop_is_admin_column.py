"""drop is_admin column — derived from role property

Revision ID: g3c5d7e9f1b2
Revises: f2b3c4d5e6a1
Create Date: 2026-06-16

"""
from alembic import op

revision = 'g3c5d7e9f1b2'
down_revision = 'a0b1c2d3e4f5'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column('users', 'is_admin')


def downgrade() -> None:
    import sqlalchemy as sa
    op.add_column('users', sa.Column('is_admin', sa.Boolean(), nullable=False, server_default='false'))
