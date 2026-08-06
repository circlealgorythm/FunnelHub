from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from funnelhub.config import get_settings
from funnelhub.db.session import async_session_maker
from funnelhub.most_telegram_bot import MOST_CHANNEL, load_most_definition
from funnelhub.services.funnel_runner import run_due_funnel_once

logger = logging.getLogger(__name__)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    if not settings.most_telegram_bot_token:
        raise RuntimeError("MOST_TELEGRAM_BOT_TOKEN is required to run the Most funnel worker.")
    definition = load_most_definition(settings)
    bot = Bot(token=settings.most_telegram_bot_token)
    try:
        while True:
            async with async_session_maker() as session:
                stats = await run_due_funnel_once(
                    session=session,
                    definition=definition,
                    bot=bot,
                    telegram_channel=MOST_CHANNEL,
                    settings=settings,
                    limit=settings.funnel_runner_batch_size,
                )
            logger.info(
                "Most funnel runner pass completed",
                extra={
                    "due": stats.due,
                    "sent": stats.sent,
                    "skipped": stats.skipped,
                    "failed": stats.failed,
                },
            )
            await asyncio.sleep(settings.funnel_runner_interval_seconds)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
