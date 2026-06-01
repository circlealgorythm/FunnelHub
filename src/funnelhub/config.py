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
    vk_group_screen_name: str | None = Field(default=None, validation_alias="VK_GROUP_SCREEN_NAME")
    vk_group_access_token: str | None = Field(
        default=None, validation_alias="VK_GROUP_ACCESS_TOKEN"
    )
    vk_callback_secret: str | None = Field(default=None, validation_alias="VK_CALLBACK_SECRET")
    vk_confirmation_code: str | None = Field(
        default=None, validation_alias="VK_CONFIRMATION_CODE"
    )
    vk_api_version: str = Field(default="5.199", validation_alias="VK_API_VERSION")
    default_funnel_path: str = Field(
        default="content/funnels/aisu_consultation.yml", validation_alias="DEFAULT_FUNNEL_PATH"
    )
    funnel_runner_interval_seconds: int = Field(
        default=60, validation_alias="FUNNEL_RUNNER_INTERVAL_SECONDS"
    )
    funnel_runner_batch_size: int = Field(default=100, validation_alias="FUNNEL_RUNNER_BATCH_SIZE")


@lru_cache
def get_settings() -> Settings:
    return Settings()
