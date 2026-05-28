from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command, CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import Message, User

from funnelhub.config import get_settings
from funnelhub.db.models import MessengerIdentity
from funnelhub.db.session import async_session_maker
from funnelhub.services.bot_linking import link_messenger_identity
from funnelhub.services.funnel_autostart import start_default_funnel_for_lead
from funnelhub.services.telegram_messaging import (
    get_telegram_identity_by_user_id,
    unsubscribe_telegram_identity,
)

logger = logging.getLogger(__name__)
router = Router()


@router.message(CommandStart())
async def handle_start(message: Message, command: CommandObject) -> None:
    token = normalize_start_token(command.args)
    if token is None:
        await message.answer("Откройте бота по ссылке с сайта, чтобы привязать Telegram.")
        return

    telegram_user = message.from_user
    if telegram_user is None:
        await message.answer("Не удалось определить Telegram-пользователя.")
        return

    try:
        settings = get_settings()
        async with async_session_maker() as session:
            result = await link_messenger_identity(
                session=session,
                token=token,
                channel="telegram",
                external_user_id=str(telegram_user.id),
                username=telegram_user.username,
                display_name=telegram_user.full_name,
                raw_profile=build_raw_profile(telegram_user),
            )
            await start_default_funnel_for_lead(
                session=session,
                settings=settings,
                lead_id=result.lead_id,
            )
            await session.commit()
    except ValueError:
        logger.info("Telegram start rejected for invalid or conflicting token")
        await message.answer("Ссылка недействительна или устарела. Получите новую ссылку.")
        return

    await message.answer("Telegram привязан. Скоро здесь начнется воронка.")


@router.message(Command("status"))
async def handle_status(message: Message) -> None:
    telegram_user = message.from_user
    if telegram_user is None:
        await message.answer("Не удалось определить Telegram-пользователя.")
        return

    async with async_session_maker() as session:
        identity = await get_telegram_identity_by_user_id(session, str(telegram_user.id))

    await message.answer(build_status_text(identity))


@router.message(Command("stop"))
async def handle_stop(message: Message) -> None:
    telegram_user = message.from_user
    if telegram_user is None:
        await message.answer("Не удалось определить Telegram-пользователя.")
        return

    async with async_session_maker() as session:
        unsubscribed = await unsubscribe_telegram_identity(session, str(telegram_user.id))
        await session.commit()

    await message.answer(build_stop_text(unsubscribed))


def normalize_start_token(args: str | None) -> str | None:
    if args is None:
        return None
    token = args.strip()
    return token or None


def build_status_text(identity: MessengerIdentity | None) -> str:
    if identity is None:
        return "Telegram пока не привязан. Откройте бота по ссылке с сайта."
    if identity.is_subscribed:
        return "Telegram привязан. Подписка активна."
    return (
        "Telegram привязан, но подписка остановлена. "
        "Нажмите ссылку с сайта, чтобы включить снова."
    )


def build_stop_text(unsubscribed: bool) -> str:
    if unsubscribed:
        return "Подписка в Telegram остановлена."
    return "Telegram пока не привязан. Отписка не требуется."


def build_raw_profile(user: User) -> dict[str, Any]:
    return {
        "id": user.id,
        "is_bot": user.is_bot,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "username": user.username,
        "language_code": user.language_code,
        "is_premium": user.is_premium,
    }


async def main() -> None:
    logging.basicConfig(level=logging.INFO)
    settings = get_settings()
    if not settings.telegram_bot_token:
        raise RuntimeError("TELEGRAM_BOT_TOKEN is required to run the Telegram bot.")

    bot = Bot(token=settings.telegram_bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    logger.info("Starting Telegram bot polling")
    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
