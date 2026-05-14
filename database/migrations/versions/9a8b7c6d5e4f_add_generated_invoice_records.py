"""add_generated_invoice_records

Revision ID: 9a8b7c6d5e4f
Revises: 0b4f8a6f2c91
Create Date: 2026-05-14 09:45:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "9a8b7c6d5e4f"
down_revision = "0b4f8a6f2c91"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "generated_invoices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("source", sa.String(length=40), nullable=True),
        sa.Column("status", sa.String(length=30), server_default="generated", nullable=False),
        sa.Column("invoice_number", sa.String(length=80), nullable=True),
        sa.Column("invoice_date", sa.DateTime(), nullable=True),
        sa.Column("due_date", sa.DateTime(), nullable=True),
        sa.Column("client_name", sa.String(length=200), nullable=True),
        sa.Column("client_company", sa.String(length=200), nullable=True),
        sa.Column("client_email", sa.String(length=200), nullable=True),
        sa.Column("client_address", sa.Text(), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("subtotal", sa.Float(), nullable=True),
        sa.Column("tax_amount", sa.Float(), nullable=True),
        sa.Column("discount_amount", sa.Float(), nullable=True),
        sa.Column("total_amount", sa.Float(), nullable=True),
        sa.Column("payment_terms", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("storage_bucket", sa.String(length=120), nullable=True),
        sa.Column("document_path", sa.Text(), nullable=True),
        sa.Column("pdf_path", sa.Text(), nullable=True),
        sa.Column("local_document_url", sa.Text(), nullable=True),
        sa.Column("local_pdf_url", sa.Text(), nullable=True),
        sa.Column("raw_data", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_generated_invoices_user_id", "generated_invoices", ["user_id"])
    op.create_index("ix_generated_invoices_status", "generated_invoices", ["status"])
    op.create_index(
        "ix_generated_invoices_invoice_number",
        "generated_invoices",
        ["invoice_number"],
    )
    op.create_index(
        "ix_generated_invoices_client_name",
        "generated_invoices",
        ["client_name"],
    )

    op.create_table(
        "generated_invoice_items",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("generated_invoice_id", sa.Integer(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("quantity", sa.Float(), nullable=True),
        sa.Column("unit_price", sa.Float(), nullable=True),
        sa.Column("total_price", sa.Float(), nullable=True),
        sa.Column("sort_order", sa.Integer(), server_default="0", nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(),
            server_default=sa.text("CURRENT_TIMESTAMP"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["generated_invoice_id"], ["generated_invoices.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_generated_invoice_items_generated_invoice_id",
        "generated_invoice_items",
        ["generated_invoice_id"],
    )


def downgrade():
    op.drop_index(
        "ix_generated_invoice_items_generated_invoice_id",
        table_name="generated_invoice_items",
    )
    op.drop_table("generated_invoice_items")
    op.drop_index("ix_generated_invoices_client_name", table_name="generated_invoices")
    op.drop_index("ix_generated_invoices_invoice_number", table_name="generated_invoices")
    op.drop_index("ix_generated_invoices_status", table_name="generated_invoices")
    op.drop_index("ix_generated_invoices_user_id", table_name="generated_invoices")
    op.drop_table("generated_invoices")
