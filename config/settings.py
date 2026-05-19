"""Typed runtime settings for the hosted production application."""

from __future__ import annotations

from typing import Optional

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AppSettings(BaseSettings):
    """Environment-backed settings with conservative production defaults."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_mode: str = Field(default="", alias="APP_MODE")
    vercel: Optional[str] = Field(default=None, alias="VERCEL")

    database_url: Optional[str] = Field(default=None, alias="DATABASE_URL")
    supabase_database_url: Optional[str] = Field(
        default=None, alias="SUPABASE_DATABASE_URL"
    )
    direct_url: Optional[str] = Field(default=None, alias="DIRECT_URL")
    supabase_direct_url: Optional[str] = Field(
        default=None, alias="SUPABASE_DIRECT_URL"
    )
    supabase_url: Optional[str] = Field(default=None, alias="SUPABASE_URL")
    next_public_supabase_url: Optional[str] = Field(
        default=None, alias="NEXT_PUBLIC_SUPABASE_URL"
    )
    supabase_project_id: Optional[str] = Field(
        default=None, alias="SUPABASE_PROJECT_ID"
    )
    supabase_db_password: Optional[str] = Field(
        default=None, alias="SUPABASE_DB_PASSWORD"
    )
    supabase_secret_key: Optional[str] = Field(
        default=None, alias="SUPABASE_SECRET_KEY"
    )
    supabase_service_role_key: Optional[str] = Field(
        default=None, alias="SUPABASE_SERVICE_ROLE_KEY"
    )
    supabase_storage_bucket: str = Field(
        default="receipts", alias="SUPABASE_STORAGE_BUCKET"
    )

    openai_api_key: Optional[str] = Field(default=None, alias="OPENAI_API_KEY")
    openai_api_model: str = Field(default="gpt-5.4-mini", alias="OPENAI_API_MODEL")

    twilio_account_sid: Optional[str] = Field(default=None, alias="TWILIO_ACCOUNT_SID")
    twilio_auth_token: Optional[str] = Field(default=None, alias="TWILIO_AUTH_TOKEN")
    twilio_phone_number: Optional[str] = Field(
        default=None, alias="TWILIO_PHONE_NUMBER"
    )
    twilio_validate_requests: Optional[str] = Field(
        default=None, alias="TWILIO_VALIDATE_REQUESTS"
    )
    twilio_media_final_reply_enabled: bool = Field(
        default=True, alias="TWILIO_MEDIA_FINAL_REPLY_ENABLED"
    )
    twilio_text_ack_enabled: bool = Field(default=True, alias="TWILIO_TEXT_ACK_ENABLED")
    twilio_text_final_reply_enabled: bool = Field(
        default=True, alias="TWILIO_TEXT_FINAL_REPLY_ENABLED"
    )
    twilio_text_router_timeout_seconds: float = Field(
        default=1.5, alias="TWILIO_TEXT_ROUTER_TIMEOUT_SECONDS"
    )

    clerk_publishable_key: Optional[str] = Field(
        default=None, alias="CLERK_PUBLISHABLE_KEY"
    )
    next_public_clerk_publishable_key: Optional[str] = Field(
        default=None, alias="NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY"
    )
    clerk_secret_key: Optional[str] = Field(default=None, alias="CLERK_SECRET_KEY")
    clerk_require_auth: Optional[bool] = Field(default=None, alias="CLERK_REQUIRE_AUTH")
    clerk_require_verified_phone: Optional[bool] = Field(
        default=None, alias="CLERK_REQUIRE_VERIFIED_PHONE"
    )
    clerk_jwt_issuer: Optional[str] = Field(default=None, alias="CLERK_JWT_ISSUER")
    clerk_jwks_url: Optional[str] = Field(default=None, alias="CLERK_JWKS_URL")
    clerk_authorized_parties: str = Field(default="", alias="CLERK_AUTHORIZED_PARTIES")
    clerk_api_url: str = Field(
        default="https://api.clerk.com/v1", alias="CLERK_API_URL"
    )
    clerk_step_up_max_age_seconds: int = Field(
        default=300, alias="CLERK_STEP_UP_MAX_AGE_SECONDS"
    )

    auto_create_database_schema: bool = Field(
        default=True, alias="AUTO_CREATE_DATABASE_SCHEMA"
    )

    rate_limits_enabled: bool = Field(default=True, alias="RATE_LIMITS_ENABLED")
    rate_limit_window_seconds: int = Field(
        default=86400, alias="RATE_LIMIT_WINDOW_SECONDS"
    )
    rate_limit_text_turns_per_window: int = Field(
        default=500, alias="RATE_LIMIT_TEXT_TURNS_PER_WINDOW"
    )
    rate_limit_media_uploads_per_window: int = Field(
        default=100, alias="RATE_LIMIT_MEDIA_UPLOADS_PER_WINDOW"
    )
    rate_limit_approvals_per_window: int = Field(
        default=200, alias="RATE_LIMIT_APPROVALS_PER_WINDOW"
    )
    rate_limit_embeddings_per_window: int = Field(
        default=1000, alias="RATE_LIMIT_EMBEDDINGS_PER_WINDOW"
    )

    async_work_queue_enabled: bool = Field(
        default=False, alias="ASYNC_WORK_QUEUE_ENABLED"
    )
    async_text_queue_enabled: bool = Field(
        default=True, alias="ASYNC_TEXT_QUEUE_ENABLED"
    )
    async_inline_media_limit: int = Field(default=3, alias="ASYNC_INLINE_MEDIA_LIMIT")
    async_job_secret: Optional[str] = Field(default=None, alias="ASYNC_JOB_SECRET")
    cron_secret: Optional[str] = Field(default=None, alias="CRON_SECRET")

    deployment_smoke_base_url: str = Field(
        default="http://localhost:5001",
        alias="DEPLOYMENT_SMOKE_BASE_URL",
    )
    deployment_smoke_timeout_seconds: float = Field(
        default=10.0, alias="DEPLOYMENT_SMOKE_TIMEOUT_SECONDS"
    )

    @field_validator(
        "rate_limit_window_seconds",
        "rate_limit_text_turns_per_window",
        "rate_limit_media_uploads_per_window",
        "rate_limit_approvals_per_window",
        "rate_limit_embeddings_per_window",
        "clerk_step_up_max_age_seconds",
        "async_inline_media_limit",
    )
    @classmethod
    def _non_negative_int(cls, value: int) -> int:
        return max(0, int(value))

    @property
    def effective_supabase_url(self) -> Optional[str]:
        return self.next_public_supabase_url or self.supabase_url

    @property
    def effective_supabase_secret_key(self) -> Optional[str]:
        return self.supabase_secret_key or self.supabase_service_role_key

    @property
    def effective_clerk_publishable_key(self) -> Optional[str]:
        return self.clerk_publishable_key or self.next_public_clerk_publishable_key

    @property
    def app_forces_demo_mode(self) -> bool:
        return self.app_mode.strip().lower() in {"demo", "ui-demo"}


def get_settings() -> AppSettings:
    return AppSettings()


def reload_settings() -> AppSettings:
    """Clear the settings cache and return a fresh settings object."""

    return get_settings()
