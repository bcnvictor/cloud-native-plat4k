"""Add status and last_seen_at to cluster_connections; add degraded to applicationstatus

Revision ID: e1b2c3d4e5f6
Revises: 00114ca084ff
Create Date: 2026-06-04 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = 'e1b2c3d4e5f6'
down_revision = '00114ca084ff'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nouveau type enum clusterstatus
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'clusterstatus') THEN "
        "CREATE TYPE clusterstatus AS ENUM ('online', 'offline', 'unknown'); "
        "END IF; END $$;"
    )

    # Ajout de la valeur 'degraded' à applicationstatus (idempotent)
    op.execute(
        "ALTER TYPE applicationstatus ADD VALUE IF NOT EXISTS 'degraded';"
    )

    op.add_column(
        'cluster_connections',
        sa.Column(
            'status',
            postgresql.ENUM('online', 'offline', 'unknown', name='clusterstatus', create_type=False),
            nullable=False,
            server_default='unknown',
        ),
    )
    op.add_column(
        'cluster_connections',
        sa.Column('last_seen_at', sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.execute(
        "UPDATE applications SET status = 'ready' WHERE status = 'degraded';"
    )
    op.drop_column('cluster_connections', 'last_seen_at')
    op.drop_column('cluster_connections', 'status')
    postgresql.ENUM('online', 'offline', 'unknown', name='clusterstatus').drop(op.get_bind(), checkfirst=True)
    # Note : on ne supprime pas 'degraded' de applicationstatus car ALTER TYPE ... DROP VALUE n'existe pas en PG < 16
