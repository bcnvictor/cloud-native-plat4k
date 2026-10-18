"""cluster_provider

Revision ID: efcc9ce95cee
Revises: 94488e983456
Create Date: 2026-10-02 12:00:00.000000

"""
from __future__ import annotations

import sqlalchemy as sa
from alembic import op

# revision identifiers, used by Alembic.
revision = 'efcc9ce95cee'
down_revision = '94488e983456'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # String et non Enum SQL : une nouvelle valeur de ClusterProvider ne demande pas de migration.
    op.add_column(
        'cluster_connections',
        sa.Column('provider', sa.String(), nullable=False, server_default='other'),
    )
    # Backfill des clusters existants d'après leur nom (cnp-aks, cnp-gke, cnp-k3s sur la VM Oracle).
    op.execute(
        "UPDATE cluster_connections SET provider = 'azure' "
        "WHERE lower(name) LIKE '%aks%' OR lower(name) LIKE '%azure%'"
    )
    op.execute(
        "UPDATE cluster_connections SET provider = 'gcp' "
        "WHERE lower(name) LIKE '%gke%' OR lower(name) LIKE '%gcp%'"
    )
    op.execute(
        "UPDATE cluster_connections SET provider = 'oracle' "
        "WHERE lower(name) LIKE '%k3s%' OR lower(name) LIKE '%oracle%'"
    )


def downgrade() -> None:
    op.drop_column('cluster_connections', 'provider')
