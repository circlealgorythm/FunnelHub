from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from funnelhub.api.inbox import ApiInboxSendClients
from funnelhub.config import get_settings
from funnelhub.db.session import async_session_maker
from funnelhub.services.autopost_runner import AutopostClients, run_due_autoposts_once
from funnelhub.services.broadcast_runner import run_due_broadcasts_once
from funnelhub.services.email_messaging import build_email_provider_client
from funnelhub.services.funnel_engine import load_funnel_definition
from funnelhub.services.funnel_runner import run_due_funnel_once
from funnelhub.services.vk_messaging import HttpVkMessageClient

logger = logging.getLogger(__name__)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    email_client = build_email_provider_client(settings)
    if not settings.telegram_bot_token and not settings.vk_group_access_token and not email_client:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN, VK_GROUP_ACCESS_TOKEN, or EMAIL_PROVIDER is required "
            "to run the funnel worker."
        )

    definitions = [load_funnel_definition(settings.default_funnel_path)]
    if settings.default_email_funnel_path and email_client is not None:
        email_definition = load_funnel_definition(settings.default_email_funnel_path)
        if email_definition.key != definitions[0].key:
            definitions.append(email_definition)
    bot = Bot(token=settings.telegram_bot_token) if settings.telegram_bot_token else None
    vk_client = (
        HttpVkMessageClient(
            access_token=settings.vk_group_access_token,
            api_version=settings.vk_api_version,
        )
        if settings.vk_group_access_token
        else None
    )

    try:
        while True:
            for definition in definitions:
                async with async_session_maker() as session:
                    stats = await run_due_funnel_once(
                        session=session,
                        definition=definition,
                        bot=bot,
                        vk_client=vk_client,
                        email_client=email_client,
                        public_base_url=settings.public_base_url,
                        email_from_email=settings.email_from_email,
                        email_from_name=settings.email_from_name,
                        email_signature_image_url=settings.email_signature_image_url,
                        email_default_subject=settings.email_default_subject,
                        settings=settings,
                        limit=settings.funnel_runner_batch_size,
                    )

                logger.info(
                    "Funnel runner pass completed",
                    extra={
                        "funnel_key": definition.key,
                        "due": stats.due,
                        "sent": stats.sent,
                        "skipped": stats.skipped,
                        "failed": stats.failed,
                    },
                )
            async with async_session_maker() as session:
                clients = ApiInboxSendClients(
                    telegram_bot=bot,
                    vk_client=vk_client,
                    email_client=email_client,
                    email_subject=settings.email_default_subject,
                    public_base_url=settings.public_base_url,
                    email_from_email=settings.email_from_email,
                    email_from_name=settings.email_from_name,
                    email_signature_image_url=settings.email_signature_image_url,
                )
                await run_due_broadcasts_once(
                    session=session,
                    clients=clients,
                    limit=settings.funnel_runner_batch_size,
                )

            async with async_session_maker() as session:
                autopost_stats = await run_due_autoposts_once(
                    session=session,
                    clients=AutopostClients(telegram_bot=bot, vk_client=vk_client),
                    settings=settings,
                    limit=settings.funnel_runner_batch_size,
                )
                if autopost_stats.due:
                    logger.info(
                        "Autopost runner pass completed",
                        extra={
                            "due": autopost_stats.due,
                            "published": autopost_stats.published,
                            "partial_failed": autopost_stats.partial_failed,
                            "failed": autopost_stats.failed,
                        },
                    )
            await asyncio.sleep(settings.funnel_runner_interval_seconds)
    finally:
        if bot is not None:
            await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
