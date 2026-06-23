"""add_username_to_gitlab_group_members

Revision ID: 2b2a5bb9d2f7
Revises: acc4d4f86a45
Create Date: 2026-06-20 23:34:18.666851

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '2b2a5bb9d2f7'
down_revision = 'acc4d4f86a45'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('gitlab_group_members', sa.Column('username', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('gitlab_group_members', 'username')
