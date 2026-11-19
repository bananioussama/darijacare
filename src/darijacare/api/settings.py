"""API settings, read from the environment and from the repository ``.env`` file.

Secrets (database password, JWT key) only come from the environment or ``.env``,
never from the code. ``DATABASE_URL`` wins when set; otherwise the PostgreSQL URL is
built from the ``POSTGRES_*`` variables that docker-compose already uses, so the
password is written in a single place.
"""

from __future__ import annotations

from urllib.parse import quote

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from darijacare.config import get_paths

MIN_JWT_SECRET_CHARS = 32


class Settings(BaseSettings):
    """All runtime options of the API (environment variables, case-insensitive)."""

    model_config = SettingsConfigDict(
        env_file=str(get_paths().root / ".env"), env_file_encoding="utf-8", extra="ignore"
    )

    # --- database ---------------------------------------------------------------------
    database_url: str | None = None
    postgres_user: str = "darijacare"
    postgres_password: SecretStr | None = None
    postgres_db: str = "darijacare"
    postgres_host: str = "127.0.0.1"
    postgres_port: int = 5432

    # --- models and vector store -------------------------------------------------------
    qdrant_url: str | None = None
    """Qdrant server (docker-compose). Empty: local embedded store, one process only."""
    nlu_model: str = "v5"
    device: str | None = None
    load_models: bool = True
    """``False`` only in tests, where a fake assistant is injected."""

    # --- security ----------------------------------------------------------------------
    jwt_secret: SecretStr | None = None
    jwt_ttl_minutes: int = 15
    """Staff access tokens (cahier des charges, Table 32: 15 minutes)."""
    session_ttl_hours: int = 24
    """Anonymous customer sessions: the token only opens one conversation."""
    cors_origins: list[str] = ["http://localhost:5173", "http://127.0.0.1:5173"]
    rate_limit_chat_per_minute: int = 30
    rate_limit_login_per_minute: int = 5
    rate_limit_register_per_minute: int = 3
    max_pending_registrations: int = 20
    """Beyond this many requests awaiting an administrator, new registrations are refused."""

    def sqlalchemy_url(self) -> str:
        """SQLAlchemy URL of the database (``psycopg`` driver for PostgreSQL)."""
        if self.database_url:
            return self.database_url
        if self.postgres_password is None:
            raise RuntimeError(
                "Base de données non configurée : définir DATABASE_URL ou POSTGRES_PASSWORD "
                "(fichier .env)."
            )
        password = quote(self.postgres_password.get_secret_value(), safe="")
        return (
            f"postgresql+psycopg://{self.postgres_user}:{password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    def jwt_key(self) -> str:
        """Signing key of the tokens; refuses a missing or short secret."""
        secret = self.jwt_secret.get_secret_value() if self.jwt_secret else ""
        if len(secret) < MIN_JWT_SECRET_CHARS:
            raise RuntimeError(
                f"JWT_SECRET absent ou trop court ({MIN_JWT_SECRET_CHARS} caractères minimum, "
                "fichier .env)."
            )
        return secret
