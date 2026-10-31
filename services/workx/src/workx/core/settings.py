"""Typed settings (Part 12 §5). Each entrypoint loads only the settings class it needs, so, for example,
the API process never receives key-provider or sandbox credentials."""

from __future__ import annotations

from enum import StrEnum

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Environment(StrEnum):
    DEVELOPMENT = "development"
    TEST = "test"
    STAGING = "staging"
    PRODUCTION = "production"


DEV_SECRET_KEY = "workx-dev-secret-key-not-for-production"  # noqa: S105 (refused outside dev/test)


class BaseWorkxSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="WORKX_", env_file=".env.local", extra="ignore")

    environment: Environment = Environment.DEVELOPMENT
    # HMAC key for derived tokens (CSRF, invitation links, IP hashes). Must be set outside dev/test.
    secret_key: SecretStr = SecretStr(DEV_SECRET_KEY)
    database_url: str = "postgresql+psycopg://workx_app:workx_app_dev@127.0.0.1:54329/workx"
    log_level: str = "INFO"

    @property
    def is_production(self) -> bool:
        return self.environment in (Environment.STAGING, Environment.PRODUCTION)

    @model_validator(mode="after")
    def _guard_secret(self) -> BaseWorkxSettings:
        if self.is_production and (self.secret_key.get_secret_value() == DEV_SECRET_KEY or len(self.secret_key) < 32):
            raise ValueError("WORKX_SECRET_KEY must be set to at least 32 random characters in staging or production")
        return self


class MigrationSettings(BaseWorkxSettings):
    migration_database_url: str = "postgresql+psycopg://workx_owner:workx_owner_dev@127.0.0.1:54329/workx"


class OidcSettings(BaseSettings):
    """OpenID Connect relying party (Keycloak in production, any compliant issuer works)."""

    model_config = SettingsConfigDict(env_prefix="WORKX_OIDC_", env_file=".env.local", extra="ignore")

    issuer: str = ""
    client_id: str = "workx-web"
    client_secret: SecretStr = SecretStr("")
    scopes: str = "openid email profile"
    # Allow http issuers only for local development and tests.
    allow_insecure_issuer: bool = False


class ApiSettings(BaseWorkxSettings):
    public_base_url: str = "http://127.0.0.1:5173"
    api_base_url: str = "http://127.0.0.1:8000"
    session_cookie_name: str = "workx_session"
    session_cookie_secure: bool = True
    invitation_ttl_days: int = 7
    mail_from: str = "WorkX <no-reply@workx.example>"
    # "file:<dir>" writes .eml files (development, tests); "smtp://user:pass@host:port" sends; "log" logs only.
    mail_url: str = "log"
    # Recent sign-in required for sensitive actions such as ownership transfer (Part 10 §3).
    reauth_window_minutes: int = 10
    session_sliding_days: int = 7
    session_absolute_days: int = 30
    cors_origins: list[str] = Field(default_factory=list)
    enable_test_seed: bool = False
    oidc: OidcSettings = Field(default_factory=OidcSettings)

    @model_validator(mode="after")
    def _guard_production(self) -> ApiSettings:
        if self.is_production and self.enable_test_seed:
            raise ValueError("WORKX_ENABLE_TEST_SEED must not be set in staging or production")
        if self.is_production and not self.session_cookie_secure:
            raise ValueError("Session cookies must be Secure in staging or production")
        return self
