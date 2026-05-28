from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from funnelhub.config import get_settings
from funnelhub.db.session import async_session_maker
from funnelhub.services.funnel_engine import load_funnel_definition
from funnelhub.services.funnel_runner import run_due_funnel_once

logger = logging.getLogger(__name__)


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to run the funnel worker.")

    definition = load_funnel_definition(settings.default_funnel_path)
    bot = Bot(token=settings.telegram_bot_token)

    try:
        while True:
            async with async_session_maker() as session:
                stats = await run_due_funnel_once(
                    session=session,
                    definition=definition,
                    bot=bot,
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
            await asyncio.sleep(settings.funnel_runner_interval_seconds)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
