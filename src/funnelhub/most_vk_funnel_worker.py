from __future__ import annotations

import asyncio
import logging

from funnelhub.config import get_settings
from funnelhub.db.session import async_session_maker
from funnelhub.most_telegram_bot import load_most_vk_definition
from funnelhub.most_vk_bot import MOST_VK_CHANNEL
from funnelhub.services.funnel_runner import run_due_funnel_once
from funnelhub.services.vk_messaging import HttpVkMessageClient

logger = logging.getLogger(__name__)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    if not settings.most_vk_group_access_token:
        raise RuntimeError("MOST_VK_GROUP_ACCESS_TOKEN is required to run the Most VK worker.")
    definition = load_most_vk_definition(settings)
    vk_client = HttpVkMessageClient(
        access_token=settings.most_vk_group_access_token,
        api_version=settings.vk_api_version,
    )
    while True:
        async with async_session_maker() as session:
            stats = await run_due_funnel_once(
                session=session,
                definition=definition,
                vk_client=vk_client,
                vk_channel=MOST_VK_CHANNEL,
                settings=settings,
                limit=settings.funnel_runner_batch_size,
            )
        logger.info(
            "Most VK funnel runner pass completed",
            extra={
                "due": stats.due,
                "sent": stats.sent,
                "skipped": stats.skipped,
                "failed": stats.failed,
            },
        )
        await asyncio.sleep(settings.funnel_runner_interval_seconds)


if __name__ == "__main__":
    asyncio.run(main())
