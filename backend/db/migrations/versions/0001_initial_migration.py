"""Initial migration

Revision ID: 0001
Revises:
Create Date: 2024-05-02 12:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from shared.models import CloudType, ResourceType, ResourceStatus, UserRole

# revision identifiers, used by Alembic.
revision = '0001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create ENUM types for postgres
    userrole_enum = postgresql.ENUM('ADMIN', 'VIEWER', name='userrole')
    userrole_enum.create(op.get_bind())

    cloudtype_enum = postgresql.ENUM('AWS', 'GCP', 'OPENSTACK', name='cloudtype')
    cloudtype_enum.create(op.get_bind())

    resourcetype_enum = postgresql.ENUM('VM', 'STORAGE', 'NETWORK', name='resourcetype')
    resourcetype_enum.create(op.get_bind())

    resourcestatus_enum = postgresql.ENUM('PENDING', 'RUNNING', 'STOPPED', 'TERMINATED', 'ERROR', name='resourcestatus')
    resourcestatus_enum.create(op.get_bind())

    # Create users table
    op.create_table('users',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('email', sa.String(), nullable=False),
    sa.Column('hashed_password', sa.String(), nullable=False),
    sa.Column('role', sa.Enum('ADMIN', 'VIEWER', name='userrole'), nullable=False),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_index(op.f('ix_users_id'), 'users', ['id'], unique=False)

    # Create api_keys table
    op.create_table('api_keys',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('hashed_key', sa.String(), nullable=False),
    sa.Column('label', sa.String(), nullable=False),
    sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('revoked', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('hashed_key')
    )
    op.create_index(op.f('ix_api_keys_id'), 'api_keys', ['id'], unique=False)

    # Create cloud_credentials table
    op.create_table('cloud_credentials',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('cloud', sa.Enum('AWS', 'GCP', 'OPENSTACK', name='cloudtype'), nullable=False),
    sa.Column('encrypted_credentials', sa.String(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_cloud_credentials_id'), 'cloud_credentials', ['id'], unique=False)

    # Create resources table
    op.create_table('resources',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('cloud', sa.Enum('AWS', 'GCP', 'OPENSTACK', name='cloudtype'), nullable=False),
    sa.Column('type', sa.Enum('VM', 'STORAGE', 'NETWORK', name='resourcetype'), nullable=False),
    sa.Column('external_id', sa.String(), nullable=False),
    sa.Column('name', sa.String(), nullable=False),
    sa.Column('status', sa.Enum('PENDING', 'RUNNING', 'STOPPED', 'TERMINATED', 'ERROR', name='resourcestatus'), nullable=False),
    sa.Column('metadata', sa.JSON(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_resources_cloud'), 'resources', ['cloud'], unique=False)
    op.create_index(op.f('ix_resources_external_id'), 'resources', ['external_id'], unique=False)
    op.create_index(op.f('ix_resources_id'), 'resources', ['id'], unique=False)
    op.create_index(op.f('ix_resources_type'), 'resources', ['type'], unique=False)

    # Create audit_logs table
    op.create_table('audit_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=True),
    sa.Column('action', sa.String(), nullable=False),
    sa.Column('resource_id', sa.Integer(), nullable=True),
    sa.Column('cloud', sa.Enum('AWS', 'GCP', 'OPENSTACK', name='cloudtype'), nullable=True),
    sa.Column('timestamp', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
    sa.Column('ip_address', sa.String(), nullable=True),
    sa.ForeignKeyConstraint(['resource_id'], ['resources.id'], ondelete='SET NULL'),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_audit_logs_id'), 'audit_logs', ['id'], unique=False)


def downgrade() -> None:
    op.drop_table('audit_logs')
    op.drop_table('resources')
    op.drop_table('cloud_credentials')
    op.drop_table('api_keys')
    op.drop_table('users')

    # Drop ENUM types
    postgresql.ENUM('ADMIN', 'VIEWER', name='userrole').drop(op.get_bind())
    postgresql.ENUM('AWS', 'GCP', 'OPENSTACK', name='cloudtype').drop(op.get_bind())
    postgresql.ENUM('VM', 'STORAGE', 'NETWORK', name='resourcetype').drop(op.get_bind())
    postgresql.ENUM('PENDING', 'RUNNING', 'STOPPED', 'TERMINATED', 'ERROR', name='resourcestatus').drop(op.get_bind())
