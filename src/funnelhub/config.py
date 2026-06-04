from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        populate_by_name=True,
    )

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
    vk_group_id: int | None = Field(default=None, validation_alias="VK_GROUP_ID")
    vk_callback_secret: str | None = Field(default=None, validation_alias="VK_CALLBACK_SECRET")
    vk_confirmation_code: str | None = Field(
        default=None, validation_alias="VK_CONFIRMATION_CODE"
    )
    vk_api_version: str = Field(default="5.199", validation_alias="VK_API_VERSION")
    vk_oauth_client_id: str | None = Field(default=None, validation_alias="VK_OAUTH_CLIENT_ID")
    vk_oauth_client_secret: str | None = Field(
        default=None, validation_alias="VK_OAUTH_CLIENT_SECRET"
    )
    vk_oauth_state_secret: str | None = Field(
        default=None, validation_alias="VK_OAUTH_STATE_SECRET"
    )
    default_funnel_path: str = Field(
        default="content/funnels/aisu_consultation.yml", validation_alias="DEFAULT_FUNNEL_PATH"
    )
    default_email_funnel_path: str | None = Field(
        default="content/funnels/aisu_email.yml",
        validation_alias="DEFAULT_EMAIL_FUNNEL_PATH",
    )
    funnel_runner_interval_seconds: int = Field(
        default=60, validation_alias="FUNNEL_RUNNER_INTERVAL_SECONDS"
    )
    funnel_runner_batch_size: int = Field(default=100, validation_alias="FUNNEL_RUNNER_BATCH_SIZE")
    inbox_admin_username: str | None = Field(
        default=None, validation_alias="INBOX_ADMIN_USERNAME"
    )
    inbox_admin_password_hash: str | None = Field(
        default=None, validation_alias="INBOX_ADMIN_PASSWORD_HASH"
    )
    inbox_session_secret: str | None = Field(
        default=None, validation_alias="INBOX_SESSION_SECRET"
    )
    inbox_session_ttl_seconds: int = Field(
        default=604800, validation_alias="INBOX_SESSION_TTL_SECONDS"
    )
    inbox_app_url: str = Field(
        default="http://127.0.0.1:5173", validation_alias="INBOX_APP_URL"
    )
    inbox_notify_telegram_bot_token: str | None = Field(
        default=None, validation_alias="INBOX_NOTIFY_TELEGRAM_BOT_TOKEN"
    )
    inbox_notify_telegram_chat_id: str | None = Field(
        default=None, validation_alias="INBOX_NOTIFY_TELEGRAM_CHAT_ID"
    )
    email_provider: str = Field(default="disabled", validation_alias="EMAIL_PROVIDER")
    email_from_email: str | None = Field(default=None, validation_alias="EMAIL_FROM_EMAIL")
    email_from_name: str = Field(default="FunnelHub", validation_alias="EMAIL_FROM_NAME")
    email_reply_to_email: str | None = Field(default=None, validation_alias="EMAIL_REPLY_TO_EMAIL")
    email_reply_to_name: str | None = Field(default=None, validation_alias="EMAIL_REPLY_TO_NAME")
    email_default_subject: str = Field(
        default="Сообщение от Aisu Kam", validation_alias="EMAIL_DEFAULT_SUBJECT"
    )
    email_signature_image_url: str | None = Field(
        default=None,
        validation_alias="EMAIL_SIGNATURE_IMAGE_URL",
    )
    email_unisender_go_api_key: str | None = Field(
        default=None,
        validation_alias="EMAIL_UNISENDER_GO_API_KEY",
    )
    email_unisender_go_api_url: str = Field(
        default="https://goapi.unisender.ru/ru/transactional/api/v1/email/send.json",
        validation_alias="EMAIL_UNISENDER_GO_API_URL",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
