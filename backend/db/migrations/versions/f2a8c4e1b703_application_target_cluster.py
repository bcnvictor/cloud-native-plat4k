"""Add target_cluster_id to applications

Revision ID: f2a8c4e1b703
Revises: d4f1c8e2b539
Create Date: 2026-06-03 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = 'f2a8c4e1b703'
down_revision = 'd4f1c8e2b539'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        'applications',
        sa.Column('target_cluster_id', sa.Integer(), nullable=True)
    )
    op.create_foreign_key(
        'fk_applications_target_cluster',
        'applications', 'cluster_connections',
        ['target_cluster_id'], ['id'],
        ondelete='SET NULL',
    )


def downgrade() -> None:
    op.drop_constraint('fk_applications_target_cluster', 'applications', type_='foreignkey')
    op.drop_column('applications', 'target_cluster_id')
