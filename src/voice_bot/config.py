"""Application configuration loaded from environment variables and .env file."""

from functools import lru_cache
from typing import Annotated, Self

from pydantic import field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables and .env file.

    Fields map to environment variables by name (case-insensitive).
    Extra environment variables are silently ignored.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    telegram_bot_token: str
    openai_api_key: str
    allowed_user_ids: Annotated[list[int], NoDecode]
    webhook_secret: str | None = None
    webhook_url: str | None = None
    webhook_path: str = "/webhook"
    use_webhook: bool = False
    log_level: str = "INFO"
    port: int = 8080
    support_email: str = "hello@zpoint.app"

    @field_validator("allowed_user_ids", mode="before")
    @classmethod
    def parse_allowed_user_ids(cls, v: str | list[int]) -> list[int]:
        """Parse comma-separated user IDs from environment variable into list of ints."""
        if isinstance(v, str):
            return [int(uid.strip()) for uid in v.split(",") if uid.strip()]
        return list(v)

    @model_validator(mode="after")
    def validate_webhook_config(self) -> Self:
        """Ensure webhook_url and webhook_secret are set when use_webhook is True."""
        if self.use_webhook:
            missing: list[str] = []
            if not self.webhook_url:
                missing.append("webhook_url")
            if not self.webhook_secret:
                missing.append("webhook_secret")
            if missing:
                raise ValueError(
                    "use_webhook=True but required fields are not set: "
                    + ", ".join(missing)
                )
        return self


@lru_cache
def get_settings() -> Settings:
    """Return the singleton Settings instance, cached after first call."""
    return Settings()


settings = get_settings()
