"""Add destroy_reason / destroy_requested_by_user_id to ephemeral_environments (4K-288)."""

import sqlalchemy as sa
from alembic import op

revision = "a7e1d0c4b288"
down_revision = "d3e4f5a6b7c8"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("ephemeral_environments", sa.Column("destroy_reason", sa.String(20), nullable=True))
    op.add_column(
        "ephemeral_environments",
        sa.Column(
            "destroy_requested_by_user_id",
            sa.Integer(),
            sa.ForeignKey("users.id", ondelete="SET NULL", name="fk_ephemeral_env_destroy_requested_by"),
            nullable=True,
        ),
    )


def downgrade():
    op.drop_constraint("fk_ephemeral_env_destroy_requested_by", "ephemeral_environments", type_="foreignkey")
    op.drop_column("ephemeral_environments", "destroy_requested_by_user_id")
    op.drop_column("ephemeral_environments", "destroy_reason")
