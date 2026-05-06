"""add_clerk_user_identity

Revision ID: 0b4f8a6f2c91
Revises: fa19ae6d8e97
Create Date: 2026-05-06 07:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "0b4f8a6f2c91"
down_revision = "fa19ae6d8e97"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "users",
        sa.Column("clerk_user_id", sa.String(length=128), nullable=True),
    )
    op.create_index(
        "ix_users_clerk_user_id",
        "users",
        ["clerk_user_id"],
        unique=True,
    )


def downgrade():
    op.drop_index("ix_users_clerk_user_id", table_name="users")
    op.drop_column("users", "clerk_user_id")
