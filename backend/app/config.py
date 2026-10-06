"""Application settings loaded from environment variables."""

from functools import lru_cache
from pathlib import Path

from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration for the KRONOS backend."""

    app_name: str = "KRONOS"
    version: str = "0.1.0"
    log_level: str = "INFO"
    log_file: Path = Path(__file__).resolve().parents[1] / "logs" / "app.log"
    knowledge_base_path: Path = (
        Path(__file__).resolve().parent / "data" / "knowledge_base.json"
    )
    jwt_secret_key: str = "kronos-dev-secret-key-change-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60
    resend_api_key: str | None = Field(
        default=None,
        validation_alias=AliasChoices("RESEND_API_KEY", "KRONOS_RESEND_API_KEY"),
    )
    resend_from_email: str | None = Field(
        default=None,
        validation_alias=AliasChoices("RESEND_FROM_EMAIL", "KRONOS_RESEND_FROM_EMAIL"),
    )

    model_config = SettingsConfigDict(
        env_prefix="KRONOS_",
        env_file=(Path(__file__).resolve().parents[1] / ".env", ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """Return the cached application settings instance."""
    return Settings()