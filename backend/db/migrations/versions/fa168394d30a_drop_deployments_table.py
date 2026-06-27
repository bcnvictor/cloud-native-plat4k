"""drop_deployments_table

Revision ID: fa168394d30a
Revises: 4f49148a68c3
Create Date: 2026-06-24 22:02:15.710187

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'fa168394d30a'
down_revision = '4f49148a68c3'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_table('deployments')


def downgrade() -> None:
    op.create_table(
        'deployments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('cluster_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.String(), nullable=False),
        sa.Column('status', sa.Enum('pending', 'running', 'succeeded', 'failed', name='deploymentstatus'), nullable=False),
        sa.Column('deployed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['cluster_id'], ['cluster_connections.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_deployments_id'), 'deployments', ['id'])
    op.create_index(op.f('ix_deployments_application_id'), 'deployments', ['application_id'])
    op.create_index(op.f('ix_deployments_cluster_id'), 'deployments', ['cluster_id'])
