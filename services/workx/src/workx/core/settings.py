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
    # Object storage for file versions: "file:<dir>" (development, single node) or "s3://bucket?endpoint=…".
    object_store_url: str = "file:.local/objects"
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
    broker_url: str = "http://127.0.0.1:8220"
    broker_token: SecretStr = SecretStr("workx-dev-broker-token")
    # SSE streams re-check session and membership this often (B-02 requires revocation within 60 s).
    sse_revalidate_seconds: float = 30.0
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


class TrustedSettings(BaseWorkxSettings):
    """Shared by the broker and the gateways: the only processes that may decrypt secrets."""

    # Connect as workx_broker (secret tables). Never configure the API, worker or orchestrator with this role.
    broker_database_url: str = "postgresql+psycopg://workx_broker:workx_broker_dev@127.0.0.1:54329/workx"
    # "local" (development; key from WORKX_LOCAL_MASTER_KEY), "openbao:<https url>?mount=transit" or "awskms:<key arn>".
    key_provider: str = "local"
    local_master_key: SecretStr = SecretStr("")
    openbao_token: SecretStr = SecretStr("")
    # Shared secret for internal calls from the API to the broker (mTLS in production deployments).
    broker_token: SecretStr = SecretStr("workx-dev-broker-token")

    @model_validator(mode="after")
    def _guard_keys(self) -> TrustedSettings:
        if self.is_production and self.key_provider == "local" and len(self.local_master_key) < 32:
            raise ValueError(
                "Set WORKX_KEY_PROVIDER (openbao/awskms) or a 32+ character WORKX_LOCAL_MASTER_KEY in production"
            )
        return self


class ModelGatewaySettings(BaseWorkxSettings):
    """Only this process holds the Anthropic key (decision 7: no raw model key in the sandbox)."""

    anthropic_base_url: str = "https://api.anthropic.com"
    anthropic_api_key: SecretStr = SecretStr("")
    upstream_timeout_seconds: float = 600.0


class ToolGatewaySettings(TrustedSettings):
    crm_base_url: str = "http://127.0.0.1:8300"
    approval_ttl_minutes: int = 10
    max_result_chars: int = 50_000
    web_fetch_max_bytes: int = 2_000_000


class OrchestratorSettings(BaseWorkxSettings):
    # Tier → model ID for this deployment (decision D-01). Configuration, never code: WORKX_MODEL_TIERS='{"auto": …}'.
    model_tiers: dict[str, str] = Field(default_factory=dict)
    sandbox_provider: str = "local_process"
    e2b_api_key: SecretStr = SecretStr("")
    e2b_template: str = "workx-runtime"
    runner_engine: str = "claude-agent-sdk"
    model_gateway_url: str = "http://127.0.0.1:8200"
    tool_gateway_url: str = "http://127.0.0.1:8210"
    max_turns: int = 40
    wall_seconds: int = 1800
    lease_seconds: int = 60
    heartbeat_seconds: float = 15.0
    max_concurrent_attempts_per_tenant: int = 2
    release_id: str = "dev"
