from __future__ import annotations

import asyncio
import logging
import re
from typing import Any

from aiogram import Bot, Dispatcher, F, Router
from aiogram.filters import Command, CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import (
    CallbackQuery,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    ReplyKeyboardRemove,
    User,
)
from sqlalchemy import select

from funnelhub.config import get_settings
from funnelhub.db.models import Lead, LeadContact, MessengerIdentity
from funnelhub.db.session import async_session_maker
from funnelhub.services.bot_linking import (
    create_or_get_active_bot_link_token,
    extract_bot_link_token,
    link_messenger_identity,
)
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
    create_telegram_bot,
    get_telegram_identity_by_user_id,
    parse_text_callback_data,
    unsubscribe_telegram_identity,
)

logger = logging.getLogger(__name__)
router = Router()


async def start_telegram_lead_with_token(
    bot: Bot,
    telegram_user: User,
    token: str,
) -> bool:
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
                telegram_bot=bot,
                vk_client=None,
            )
            await run_due_funnel_step(
                session=session,
                state=state,
                definition=definition,
                sender=sender,
            )
            await session.commit()
            return True
    except ValueError:
        logger.info(
            "Telegram start rejected for invalid or conflicting token: %s",
            token,
            extra={"telegram_user_id": telegram_user.id},
        )
        return False


async def link_telegram_lead_by_phone(
    bot: Bot,
    telegram_user: User,
    phone: str,
) -> bool:
    digits = re.sub(r"\D", "", phone)
    if len(digits) < 10:
        return False

    variations = [digits]
    if len(digits) == 11 and digits.startswith(("7", "8")):
        core = digits[1:]
        variations.extend([core, "7" + core, "8" + core])
    elif len(digits) == 10:
        variations.extend(["7" + digits, "8" + digits])

    settings = get_settings()
    definition = load_funnel_definition(settings.default_funnel_path)
    async with async_session_maker() as session:
        contact = await session.scalar(
            select(LeadContact)
            .where(
                LeadContact.contact_type == "phone",
                LeadContact.normalized_value.in_(variations),
            )
            .order_by(LeadContact.created_at.desc())
        )
        if contact is None:
            return False

        lead = await session.get(Lead, contact.lead_id)
        if lead is None:
            return False

        bot_link_token = await create_or_get_active_bot_link_token(session, lead)
        result = await link_messenger_identity(
            session=session,
            token=bot_link_token.token,
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
            telegram_bot=bot,
            vk_client=None,
        )
        await run_due_funnel_step(
            session=session,
            state=state,
            definition=definition,
            sender=sender,
        )
        await session.commit()
        return True


@router.message(CommandStart())
async def handle_start(message: Message, command: CommandObject) -> None:
    telegram_user = message.from_user
    bot = message.bot
    if telegram_user is None or bot is None:
        await message.answer("Не удалось определить Telegram-пользователя.")
        return

    token = normalize_start_token(command.args)
    if token is not None:
        ok = await start_telegram_lead_with_token(bot, telegram_user, token)
        if ok:
            return
        await message.answer(
            "Не удалось открыть материалы по этой ссылке (возможно, срок её действия истёк). "
            "Отправьте ваш номер телефона, и мы найдем вашу заявку."
        )
        return

    async with async_session_maker() as session:
        existing = await get_telegram_identity_by_user_id(session, str(telegram_user.id))
    if existing is not None and existing.is_subscribed:
        await message.answer("Вы уже подключены к материалам Школы Сатья Юга!")
        return

    keyboard = ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📱 Подтвердить заявку по номеру телефона", request_contact=True)]
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )
    await message.answer(
        "Чтобы получить материалы, откройте бота по персональной ссылке после заявки "
        "или нажмите кнопку ниже, чтобы подтвердить заявку по номеру телефона:",
        reply_markup=keyboard,
    )


@router.message(F.contact)
async def handle_contact(message: Message) -> None:
    telegram_user = message.from_user
    contact = message.contact
    bot = message.bot
    if telegram_user is None or contact is None or bot is None:
        return

    ok = await link_telegram_lead_by_phone(bot, telegram_user, contact.phone_number)
    if ok:
        await message.answer(
            "Заявка подтверждена! Материалы отправлены выше.",
            reply_markup=ReplyKeyboardRemove(),
        )
    else:
        await message.answer(
            "Заявка с таким номером телефона не найдена. "
            "Пожалуйста, отправьте ссылку на страницу после заявки в этот чат.",
            reply_markup=ReplyKeyboardRemove(),
        )


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
    bot = message.bot
    if telegram_user is None or message.text is None or bot is None:
        return

    # 1. Check if message contains token or link
    token = extract_bot_link_token(message.text)
    if token is not None:
        ok = await start_telegram_lead_with_token(bot, telegram_user, token)
        if ok:
            return

    # 2. Check if unlinked user typed a phone number as text
    clean_text = message.text.strip()
    digits = re.sub(r"\D", "", clean_text)
    if len(digits) in (10, 11) and re.fullmatch(r"^\+?[0-9\s\-\(\)]{10,20}$", clean_text):
        async with async_session_maker() as session:
            existing = await get_telegram_identity_by_user_id(session, str(telegram_user.id))
        if existing is None or not existing.is_subscribed:
            ok = await link_telegram_lead_by_phone(bot, telegram_user, clean_text)
            if ok:
                await message.answer(
                    "Заявка подтверждена! Материалы отправлены выше.",
                    reply_markup=ReplyKeyboardRemove(),
                )
                return

    settings = get_settings()
    definition = load_funnel_definition(settings.default_funnel_path)
    async with async_session_maker() as session:
        sender = MessengerFunnelStepSender(
            session=session,
            telegram_bot=bot,
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

        # Уведомление оператору — в том числе об авто-обработанных ответах
        # кнопок: оператор отслеживает выбор лидов в @leadsaisubot.
        if inbound_message is not None:
            await notify_admin_about_inbound_message(
                session=session,
                settings=settings,
                message=inbound_message,
            )

        await session.commit()
        await callback.answer("Принято" if handled else None)


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

    bot = create_telegram_bot(settings.telegram_bot_token, settings)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    logger.info("Starting Telegram bot polling")
    await dispatcher.start_polling(bot, polling_timeout=settings.telegram_polling_timeout)


if __name__ == "__main__":
    asyncio.run(main())
