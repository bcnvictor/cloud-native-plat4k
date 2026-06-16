"""GitLab membership mirror (4K-65)

Revision ID: c5ead64c0fef
Revises: fa5e6a11f864
Create Date: 2026-06-15 00:00:00.000000

"""
import sqlalchemy as sa
from alembic import op

revision = 'c5ead64c0fef'
down_revision = 'fa5e6a11f864'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # users: gitlab_user_id
    op.add_column('users', sa.Column('gitlab_user_id', sa.BigInteger(), nullable=True))
    op.create_unique_constraint('uq_users_gitlab_user_id', 'users', ['gitlab_user_id'])
    op.create_index('ix_users_gitlab_user_id', 'users', ['gitlab_user_id'])

    # applications: gitlab_project_id, owning_gitlab_group_id
    op.add_column('applications', sa.Column('gitlab_project_id', sa.BigInteger(), nullable=True))
    op.add_column('applications', sa.Column('owning_gitlab_group_id', sa.BigInteger(), nullable=True))

    # gitlab_groups
    op.create_table(
        'gitlab_groups',
        sa.Column('gitlab_group_id', sa.BigInteger(), primary_key=True),
        sa.Column('name', sa.String(), nullable=False),
        sa.Column('full_path', sa.String(), nullable=False),
        sa.Column('synced_at', sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint('full_path', name='uq_gitlab_groups_full_path'),
    )

    # gitlab_group_members
    op.create_table(
        'gitlab_group_members',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('gitlab_group_id', sa.BigInteger(), sa.ForeignKey('gitlab_groups.gitlab_group_id', ondelete='CASCADE'), nullable=False),
        sa.Column('gitlab_user_id', sa.BigInteger(), nullable=True),
        sa.Column('access_level', sa.Integer(), nullable=False),
        sa.Column('cnp_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('status', sa.Enum('active', 'pending_invite', 'left', name='memberstatus'), nullable=False, server_default='active'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.UniqueConstraint('gitlab_group_id', 'gitlab_user_id', name='uq_group_member_gitlab_user'),
    )
    op.create_index('ix_gitlab_group_members_gitlab_group_id', 'gitlab_group_members', ['gitlab_group_id'])
    op.create_index('ix_gitlab_group_members_cnp_user_id', 'gitlab_group_members', ['cnp_user_id'])

    # app_members
    op.create_table(
        'app_members',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('gitlab_project_id', sa.BigInteger(), nullable=False),
        sa.Column('gitlab_user_id', sa.BigInteger(), nullable=True),
        sa.Column('email', sa.String(), nullable=True),
        sa.Column('access_level', sa.Integer(), nullable=False),
        sa.Column('cnp_user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('status', sa.Enum('active', 'pending_invite', 'left', name='memberstatus', create_type=False), nullable=False, server_default='active'),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=True),
        sa.UniqueConstraint('gitlab_project_id', 'gitlab_user_id', name='uq_app_member_gitlab_user'),
        sa.UniqueConstraint('gitlab_project_id', 'email', name='uq_app_member_email'),
    )
    op.create_index('ix_app_members_gitlab_project_id', 'app_members', ['gitlab_project_id'])
    op.create_index('ix_app_members_cnp_user_id', 'app_members', ['cnp_user_id'])


def downgrade() -> None:
    op.drop_index('ix_app_members_cnp_user_id', table_name='app_members')
    op.drop_index('ix_app_members_gitlab_project_id', table_name='app_members')
    op.drop_table('app_members')

    op.drop_index('ix_gitlab_group_members_cnp_user_id', table_name='gitlab_group_members')
    op.drop_index('ix_gitlab_group_members_gitlab_group_id', table_name='gitlab_group_members')
    op.drop_table('gitlab_group_members')

    op.drop_table('gitlab_groups')

    sa.Enum(name='memberstatus').drop(op.get_bind())

    op.drop_column('applications', 'owning_gitlab_group_id')
    op.drop_column('applications', 'gitlab_project_id')

    op.drop_index('ix_users_gitlab_user_id', table_name='users')
    op.drop_constraint('uq_users_gitlab_user_id', 'users', type_='unique')
    op.drop_column('users', 'gitlab_user_id')
