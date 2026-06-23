"""cluster_monitoring_urls

Revision ID: 4f49148a68c3
Revises: 2b2a5bb9d2f7
Create Date: 2026-06-23 03:17:23.635743

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = '4f49148a68c3'
down_revision = '2b2a5bb9d2f7'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('cluster_connections', sa.Column('prometheus_url', sa.String(), nullable=True))
    op.add_column('cluster_connections', sa.Column('loki_url', sa.String(), nullable=True))
    op.add_column('cluster_connections', sa.Column('argocd_url', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('cluster_connections', 'argocd_url')
    op.drop_column('cluster_connections', 'loki_url')
    op.drop_column('cluster_connections', 'prometheus_url')
