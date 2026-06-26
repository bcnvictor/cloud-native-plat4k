"""rename_application_status_to_last_known_status

Revision ID: 1bc3ec804c83
Revises: fa168394d30a
Create Date: 2026-06-24 22:13:17.857592

"""
from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = '1bc3ec804c83'
down_revision = 'fa168394d30a'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column('applications', 'status', new_column_name='last_known_status')


def downgrade() -> None:
    op.alter_column('applications', 'last_known_status', new_column_name='status')
