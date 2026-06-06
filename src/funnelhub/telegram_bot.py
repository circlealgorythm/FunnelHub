from __future__ import annotations

import asyncio
import logging
from typing import Any

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command, CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import CallbackQuery, Message, User

from funnelhub.config import get_settings
from funnelhub.db.models import MessengerIdentity
from funnelhub.db.session import async_session_maker
from funnelhub.services.bot_linking import link_messenger_identity
from funnelhub.services.funnel_answers import handle_funnel_text_reply
from funnelhub.services.funnel_autostart import restart_default_funnel_for_lead
from funnelhub.services.funnel_engine import load_funnel_definition, run_due_funnel_step
from funnelhub.services.funnel_runner import MessengerFunnelStepSender
from funnelhub.services.inbox import (
    mark_conversation_auto_handled,
    record_inbound_messenger_message,
)
from funnelhub.services.inbox_notifications import notify_admin_about_inbound_message
from funnelhub.services.telegram_messaging import (
    get_telegram_identity_by_user_id,
    parse_text_callback_data,
    unsubscribe_telegram_identity,
)

logger = logging.getLogger(__name__)
router = Router()


@router.message(CommandStart())
async def handle_start(message: Message, command: CommandObject) -> None:
    token = normalize_start_token(command.args)
    if token is None:
        await message.answer(
            "Чтобы получить материалы, нажмите кнопку Telegram на странице после заявки."
        )
        return

    telegram_user = message.from_user
    if telegram_user is None:
        await message.answer("Не удалось определить Telegram-пользователя.")
        return

    try:
        settings = get_settings()
        definition = load_funnel_definition(settings.default_funnel_path)
        async with async_session_maker() as session:
            result = await link_messenger_identity(
                session=session,
                token=token,
                channel="telegram",
                external_user_id=str(telegram_user.id),
                username=telegram_user.username,
                display_name=telegram_user.full_name,
                raw_profile=build_raw_profile(telegram_user),
                allow_relink=True,
            )
            state = await restart_default_funnel_for_lead(
                session=session,
                settings=settings,
                lead_id=result.lead_id,
                messenger_channel="telegram",
            )
            sender = MessengerFunnelStepSender(
                session=session,
                telegram_bot=message.bot,
                vk_client=None,
            )
            await run_due_funnel_step(
                session=session,
                state=state,
                definition=definition,
                sender=sender,
            )
            await session.commit()
    except ValueError:
        logger.info("Telegram start rejected for invalid or conflicting token")
        await message.answer(
            "Не удалось открыть материалы. Вернитесь на страницу после заявки "
            "и нажмите кнопку Telegram еще раз."
        )
        return


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


@router.message()
async def handle_text_answer(message: Message) -> None:
    telegram_user = message.from_user
    if telegram_user is None or message.text is None:
        return

    settings = get_settings()
    definition = load_funnel_definition(settings.default_funnel_path)
    async with async_session_maker() as session:
        sender = MessengerFunnelStepSender(
            session=session,
            telegram_bot=message.bot,
            vk_client=None,
        )
        inbound_message = await record_inbound_messenger_message(
            session=session,
            channel="telegram",
            external_user_id=str(telegram_user.id),
            body=message.text,
            external_message_id=str(message.message_id),
            metadata={"source": "telegram_message"},
        )
        handled = await handle_funnel_text_reply(
            session=session,
            definition=definition,
            channel="telegram",
            external_user_id=str(telegram_user.id),
            text=message.text,
            sender=sender,
        )
        if handled:
            await mark_conversation_auto_handled(
                session=session,
                channel="telegram",
                external_user_id=str(telegram_user.id),
            )
        elif inbound_message is not None:
            await notify_admin_about_inbound_message(
                session=session,
                settings=settings,
                message=inbound_message,
            )
        if inbound_message is not None or handled:
            await session.commit()


@router.callback_query()
async def handle_inline_answer(callback: CallbackQuery) -> None:
    telegram_user = callback.from_user
    if telegram_user is None or callback.data is None:
        return

    text = parse_text_callback_data(callback.data)
    if text is None:
        return

    settings = get_settings()
    definition = load_funnel_definition(settings.default_funnel_path)
    async with async_session_maker() as session:
        sender = MessengerFunnelStepSender(
            session=session,
            telegram_bot=callback.bot,
            vk_client=None,
        )
        inbound_message = await record_inbound_messenger_message(
            session=session,
            channel="telegram",
            external_user_id=str(telegram_user.id),
            body=text,
            external_message_id=str(callback.message.message_id)
            if callback.message is not None
            else None,
            metadata={
                "source": "telegram_callback",
                "callback_data": callback.data,
            },
        )
        handled = await handle_funnel_text_reply(
            session=session,
            definition=definition,
            channel="telegram",
            external_user_id=str(telegram_user.id),
            text=text,
            sender=sender,
        )
        if handled:
            await mark_conversation_auto_handled(
                session=session,
                channel="telegram",
                external_user_id=str(telegram_user.id),
            )
            await session.commit()
            await callback.answer("Принято")
            return
        if inbound_message is not None:
            await notify_admin_about_inbound_message(
                session=session,
                settings=settings,
                message=inbound_message,
            )
            await session.commit()

    await callback.answer()


def normalize_start_token(args: str | None) -> str | None:
    if args is None:
        return None
    token = args.strip()
    return token or None


def build_status_text(identity: MessengerIdentity | None) -> str:
    if identity is None:
        return "Telegram пока не привязан. Нажмите кнопку Telegram на странице после заявки."
    if identity.is_subscribed:
        return "Telegram привязан. Подписка активна."
    return (
        "Telegram привязан, но подписка остановлена. "
        "Нажмите кнопку Telegram на странице после заявки, чтобы включить снова."
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
