"""Initial integer-ID schema with pgvector.

Revision ID: 455b03be74ff
Revises:
Create Date: 2025-04-04 07:58:33.778935
"""

from alembic import op
import sqlalchemy as sa
from pgvector.sqlalchemy import Vector


revision = "455b03be74ff"
down_revision = None
branch_labels = None
depends_on = None


message_role = sa.Enum("USER", "ASSISTANT", "SYSTEM", name="messagerole")
whatsapp_status = sa.Enum(
    "SENT", "DELIVERED", "READ", "FAILED", name="whatsappmessagestatus"
)
file_type = sa.Enum("image", "pdf", "excel", "word", "text", "other", name="filetype")
file_status = sa.Enum("uploaded", "processed", "error", name="filestatus")


def upgrade() -> None:
    dialect_name = op.get_bind().dialect.name
    vector_type = Vector(1536) if dialect_name == "postgresql" else sa.Text()

    if dialect_name == "postgresql":
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("whatsapp_number", sa.String(length=20), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=True),
        sa.Column("email", sa.String(length=100), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
        sa.Column("preferences", sa.Text(), nullable=True),
    )
    op.create_index(op.f("ix_users_whatsapp_number"), "users", ["whatsapp_number"], unique=True)

    op.create_table(
        "invoices",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("invoice_number", sa.String(length=50), nullable=True),
        sa.Column("invoice_date", sa.DateTime(), nullable=True),
        sa.Column("vendor", sa.String(length=100), nullable=True),
        sa.Column("total_amount", sa.Float(), nullable=True),
        sa.Column("tax_amount", sa.Float(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("file_url", sa.Text(), nullable=True),
        sa.Column("file_content_type", sa.String(length=50), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "items",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.id"), nullable=True),
        sa.Column("description", sa.String(length=255), nullable=False),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("unit_price", sa.Float(), nullable=False),
        sa.Column("total_price", sa.Float(), nullable=False),
        sa.Column("item_category", sa.String(length=50), nullable=True),
        sa.Column("item_code", sa.String(length=50), nullable=True),
        sa.Column("description_embedding", vector_type, nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )
    op.create_index(op.f("ix_items_invoice_id"), "items", ["invoice_id"], unique=False)
    op.create_index(op.f("ix_items_item_category"), "items", ["item_category"], unique=False)

    op.create_table(
        "invoice_embeddings",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.id"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("content_text", sa.Text(), nullable=True),
        sa.Column("embedding", vector_type, nullable=True),
        sa.Column("model_name", sa.String(length=100), nullable=True),
        sa.Column("embedding_type", sa.String(length=50), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("invoice_id", "embedding_type", name="uix_invoice_embedding_type"),
    )
    op.create_index(
        op.f("ix_invoice_embeddings_invoice_id"),
        "invoice_embeddings",
        ["invoice_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_invoice_embeddings_user_id"),
        "invoice_embeddings",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "conversations",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=True),
    )

    op.create_table(
        "messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column(
            "conversation_id",
            sa.Integer(),
            sa.ForeignKey("conversations.id"),
            nullable=True,
        ),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("role", message_role, nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "whatsapp_messages",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("message_id", sa.Integer(), sa.ForeignKey("messages.id"), nullable=True),
        sa.Column("whatsapp_message_id", sa.String(length=100), nullable=True),
        sa.Column("status", whatsapp_status, nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.UniqueConstraint("whatsapp_message_id"),
    )

    op.create_table(
        "media",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("invoice_id", sa.Integer(), sa.ForeignKey("invoices.id"), nullable=True),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("original_filename", sa.String(length=255), nullable=True),
        sa.Column("file_path", sa.String(length=512), nullable=False),
        sa.Column("file_url", sa.Text(), nullable=False),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("content_type", sa.String(length=50), nullable=False),
        sa.Column("file_type", file_type, nullable=True),
        sa.Column("status", file_status, nullable=True),
        sa.Column("ocr_text", sa.Text(), nullable=True),
        sa.Column("processing_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
    )

    op.create_table(
        "usage",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("tokens_in", sa.Integer(), nullable=True),
        sa.Column("tokens_out", sa.Integer(), nullable=True),
        sa.Column("cost", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
    )

    if dialect_name == "postgresql":
        op.execute(
            "CREATE INDEX IF NOT EXISTS items_description_embedding_hnsw_idx "
            "ON items USING hnsw (description_embedding vector_cosine_ops)"
        )
        op.execute(
            "CREATE INDEX IF NOT EXISTS invoice_embeddings_embedding_hnsw_idx "
            "ON invoice_embeddings USING hnsw (embedding vector_cosine_ops)"
        )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS invoice_embeddings_embedding_hnsw_idx")
    op.execute("DROP INDEX IF EXISTS items_description_embedding_hnsw_idx")
    op.drop_table("usage")
    op.drop_table("media")
    op.drop_table("whatsapp_messages")
    op.drop_table("messages")
    op.drop_table("conversations")
    op.drop_table("invoice_embeddings")
    op.drop_index(op.f("ix_items_item_category"), table_name="items")
    op.drop_index(op.f("ix_items_invoice_id"), table_name="items")
    op.drop_table("items")
    op.drop_table("invoices")
    op.drop_index(op.f("ix_users_whatsapp_number"), table_name="users")
    op.drop_table("users")
    file_status.drop(op.get_bind(), checkfirst=True)
    file_type.drop(op.get_bind(), checkfirst=True)
    whatsapp_status.drop(op.get_bind(), checkfirst=True)
    message_role.drop(op.get_bind(), checkfirst=True)
