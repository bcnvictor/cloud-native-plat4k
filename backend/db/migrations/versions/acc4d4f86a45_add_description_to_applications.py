"""add_description_to_applications

Revision ID: acc4d4f86a45
Revises: cfc5e4e75804
Create Date: 2026-06-20 22:36:30.786477

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'acc4d4f86a45'
down_revision = 'cfc5e4e75804'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('applications', sa.Column('description', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('applications', 'description')
