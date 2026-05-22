from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="FunnelHub", validation_alias="APP_NAME")
    app_env: str = Field(default="local", validation_alias="APP_ENV")
    app_debug: bool = Field(default=False, validation_alias="APP_DEBUG")
    database_url: str = Field(
        default="postgresql+asyncpg://funnelhub:funnelhub@localhost:5432/funnelhub",
        validation_alias="DATABASE_URL",
    )
    redis_url: str = Field(default="redis://localhost:6379/0", validation_alias="REDIS_URL")
    public_base_url: str = Field(
        default="http://localhost:8000", validation_alias="PUBLIC_BASE_URL"
    )
    telegram_bot_username: str | None = Field(
        default=None, validation_alias="TELEGRAM_BOT_USERNAME"
    )
    telegram_bot_token: str | None = Field(default=None, validation_alias="TELEGRAM_BOT_TOKEN")


@lru_cache
def get_settings() -> Settings:
    return Settings()
