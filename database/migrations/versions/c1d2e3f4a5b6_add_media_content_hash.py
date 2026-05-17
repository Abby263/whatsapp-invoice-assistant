"""add_media_content_hash

Revision ID: c1d2e3f4a5b6
Revises: 9a8b7c6d5e4f
Create Date: 2026-05-17 00:55:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "c1d2e3f4a5b6"
down_revision = "9a8b7c6d5e4f"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("media", sa.Column("content_hash", sa.String(length=64), nullable=True))
    op.create_index("ix_media_content_hash", "media", ["content_hash"])

    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute(
            """
            CREATE UNIQUE INDEX IF NOT EXISTS uix_media_user_content_hash
            ON media (user_id, content_hash)
            WHERE content_hash IS NOT NULL
            """
        )


def downgrade():
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        op.execute("DROP INDEX IF EXISTS uix_media_user_content_hash")
    op.drop_index("ix_media_content_hash", table_name="media")
    op.drop_column("media", "content_hash")
