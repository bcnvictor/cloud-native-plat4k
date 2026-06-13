"""Add IDP entities: Application, ClusterConnection, Deployment

Revision ID: 0003
Revises: 0002
Create Date: 2026-05-13 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = '0003'
down_revision = '0002'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'applicationstatus') THEN "
        "CREATE TYPE applicationstatus AS ENUM ('onboarding', 'ready', 'deployed'); "
        "END IF; END $$;"
    )
    op.execute(
        "DO $$ BEGIN "
        "IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'deploymentstatus') THEN "
        "CREATE TYPE deploymentstatus AS ENUM ('pending', 'running', 'succeeded', 'failed'); "
        "END IF; END $$;"
    )

    op.create_table(
        'applications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('repo_url', sa.String(), nullable=True),
        sa.Column('owner', sa.String(), nullable=False),
        sa.Column(
            'status',
            postgresql.ENUM('onboarding', 'ready', 'deployed', name='applicationstatus', create_type=False),
            nullable=False,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_applications_id'), 'applications', ['id'], unique=False)

    op.create_table(
        'cluster_connections',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('endpoint', sa.String(), nullable=False),
        sa.Column('kubeconfig_secret_ref', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('name'),
    )
    op.create_index(op.f('ix_cluster_connections_id'), 'cluster_connections', ['id'], unique=False)

    op.create_table(
        'deployments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('application_id', sa.Integer(), nullable=False),
        sa.Column('cluster_id', sa.Integer(), nullable=False),
        sa.Column('version', sa.String(), nullable=False),
        sa.Column(
            'status',
            postgresql.ENUM('pending', 'running', 'succeeded', 'failed', name='deploymentstatus', create_type=False),
            nullable=False,
        ),
        sa.Column('deployed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.ForeignKeyConstraint(['application_id'], ['applications.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['cluster_id'], ['cluster_connections.id'], ondelete='RESTRICT'),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_deployments_id'), 'deployments', ['id'], unique=False)
    op.create_index(op.f('ix_deployments_application_id'), 'deployments', ['application_id'], unique=False)
    op.create_index(op.f('ix_deployments_cluster_id'), 'deployments', ['cluster_id'], unique=False)
    op.create_index(op.f('ix_deployments_status'), 'deployments', ['status'], unique=False)


def downgrade() -> None:
    op.drop_table('deployments')
    op.drop_table('cluster_connections')
    op.drop_table('applications')

    postgresql.ENUM('onboarding', 'ready', 'deployed', name='applicationstatus').drop(op.get_bind())
    postgresql.ENUM('pending', 'running', 'succeeded', 'failed', name='deploymentstatus').drop(op.get_bind())
