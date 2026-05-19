"""add_rate_limits_and_async_jobs

Revision ID: e3f4a5b6c7d8
Revises: d2e3f4a5b6c7
Create Date: 2026-05-19 06:30:00.000000

"""
from alembic import op
import sqlalchemy as sa


revision = "e3f4a5b6c7d8"
down_revision = "d2e3f4a5b6c7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "usage", sa.Column("operation_type", sa.String(length=80), nullable=True)
    )
    op.add_column("usage", sa.Column("request_id", sa.String(length=80), nullable=True))
    op.add_column("usage", sa.Column("usage_metadata", sa.JSON(), nullable=True))
    op.create_index("ix_usage_operation_type", "usage", ["operation_type"])
    op.create_index("ix_usage_request_id", "usage", ["request_id"])

    op.create_table(
        "rate_limit_events",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("scope", sa.String(length=80), nullable=False),
        sa.Column("request_id", sa.String(length=80), nullable=True),
        sa.Column("units", sa.Integer(), nullable=False, server_default="1"),
        sa.Column(
            "status", sa.String(length=30), nullable=False, server_default="allowed"
        ),
        sa.Column("event_metadata", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_rate_limit_events_created_at", "rate_limit_events", ["created_at"]
    )
    op.create_index(
        "ix_rate_limit_events_request_id", "rate_limit_events", ["request_id"]
    )
    op.create_index("ix_rate_limit_events_scope", "rate_limit_events", ["scope"])
    op.create_index("ix_rate_limit_events_status", "rate_limit_events", ["status"])
    op.create_index("ix_rate_limit_events_user_id", "rate_limit_events", ["user_id"])

    op.create_table(
        "async_jobs",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("job_type", sa.String(length=80), nullable=False),
        sa.Column("idempotency_key", sa.String(length=160), nullable=True),
        sa.Column(
            "status", sa.String(length=30), nullable=False, server_default="queued"
        ),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("attempts", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("max_attempts", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("available_at", sa.DateTime(), nullable=True),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=True),
        sa.Column("updated_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_async_jobs_available_at", "async_jobs", ["available_at"])
    op.create_index("ix_async_jobs_idempotency_key", "async_jobs", ["idempotency_key"])
    op.create_index("ix_async_jobs_job_type", "async_jobs", ["job_type"])
    op.create_index("ix_async_jobs_status", "async_jobs", ["status"])
    op.create_index("ix_async_jobs_user_id", "async_jobs", ["user_id"])


def downgrade():
    op.drop_index("ix_async_jobs_user_id", table_name="async_jobs")
    op.drop_index("ix_async_jobs_status", table_name="async_jobs")
    op.drop_index("ix_async_jobs_job_type", table_name="async_jobs")
    op.drop_index("ix_async_jobs_idempotency_key", table_name="async_jobs")
    op.drop_index("ix_async_jobs_available_at", table_name="async_jobs")
    op.drop_table("async_jobs")

    op.drop_index("ix_rate_limit_events_user_id", table_name="rate_limit_events")
    op.drop_index("ix_rate_limit_events_status", table_name="rate_limit_events")
    op.drop_index("ix_rate_limit_events_scope", table_name="rate_limit_events")
    op.drop_index("ix_rate_limit_events_request_id", table_name="rate_limit_events")
    op.drop_index("ix_rate_limit_events_created_at", table_name="rate_limit_events")
    op.drop_table("rate_limit_events")

    op.drop_index("ix_usage_request_id", table_name="usage")
    op.drop_index("ix_usage_operation_type", table_name="usage")
    op.drop_column("usage", "usage_metadata")
    op.drop_column("usage", "request_id")
    op.drop_column("usage", "operation_type")
