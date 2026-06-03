"""Add unique constraint on applications.repo_url

Revision ID: d4f1c8e2b539
Revises: b3e9f2a1d047
Create Date: 2026-06-03 00:00:00.000000

"""
from alembic import op

revision = 'd4f1c8e2b539'
down_revision = 'b3e9f2a1d047'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint('uq_applications_repo_url', 'applications', ['repo_url'])


def downgrade() -> None:
    op.drop_constraint('uq_applications_repo_url', 'applications', type_='unique')
