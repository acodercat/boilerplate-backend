"""Application settings, read once from the environment and ``.env``.

Every tunable lives here so a deploy changes behaviour by configuration,
never by editing code. Fields without a default are mandatory: a missing
one fails loudly at import time rather than on the first request that
needs it.
"""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # Application
    app_name: str = "Boilerplate API"
    root_path: str = Field(default="/api/v1", description="Prefix the reverse proxy strips")
    # Explicit allowlist. Never ``["*"]``: responses carry
    # ``allow_credentials=True`` and browsers reject that pair.
    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])

    # Logging
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"
    log_dir: str = "logs"

    # Database
    db_uri: str = Field(description="postgresql+psycopg://user:pass@host:port/db")
    db_pool_size: int = 10
    db_max_overflow: int = 10
    db_pool_recycle_seconds: int = 300
    db_pool_timeout_seconds: int = 30
    db_echo: bool = False

    # Startup dependency probe — exponential backoff so a few-second
    # dependency race at boot (compose / k8s start things in parallel)
    # does not crash-loop the process, while a real outage still surfaces.
    startup_probe_attempts: int = 5
    startup_probe_base_delay_seconds: float = 0.5
    startup_probe_max_delay_seconds: float = 8.0

    # Auth. 32+ characters: PyJWT warns below that for HMAC-SHA256.
    secret_key: str = Field(min_length=32, description="JWT signing key")
    # HMAC only: ``secret_key`` is a shared secret, not a key pair.
    jwt_algorithm: Literal["HS256", "HS384", "HS512"] = "HS256"
    access_token_expire_minutes: int = 60 * 24 * 7
    bcrypt_rounds: int = Field(default=12, ge=4, le=31)


settings = Settings()
