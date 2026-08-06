from __future__ import annotations

import asyncio
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, cast

from aiogram import Bot, Dispatcher, Router
from aiogram.filters import Command, CommandStart
from aiogram.filters.command import CommandObject
from aiogram.types import CallbackQuery, Message, User
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.config import Settings, get_settings
from funnelhub.db.models import FunnelState
from funnelhub.db.session import async_session_maker
from funnelhub.services.bot_linking import link_messenger_identity
from funnelhub.services.funnel_autostart import restart_funnel_for_lead
from funnelhub.services.funnel_engine import (
    FunnelButton,
    FunnelDefinition,
    build_state_metadata,
    load_funnel_definition,
    run_due_funnel_step,
)
from funnelhub.services.funnel_runner import MessengerFunnelStepSender
from funnelhub.services.inbox import (
    mark_conversation_auto_handled,
    record_inbound_messenger_message,
)
from funnelhub.services.inbox_notifications import notify_admin_about_inbound_message
from funnelhub.services.lead_post_submit_tasks import enqueue_lead_tag_notification
from funnelhub.services.lead_tags import assign_lead_tag
from funnelhub.services.telegram_messaging import (
    get_telegram_identity_by_user_id,
    parse_text_callback_data,
    unsubscribe_telegram_identity,
)

logger = logging.getLogger(__name__)
router = Router()
MOST_CHANNEL = "telegram_most"
MOST_FUNNEL_KEY = "most_tsennostey_telegram"


@dataclass(frozen=True)
class QuizOption:
    text: str
    scores: dict[str, int]


@dataclass(frozen=True)
class QuizQuestion:
    text: str
    options: tuple[QuizOption, ...]


QUIZ: tuple[QuizQuestion, ...] = (
    QuizQuestion(
        "Вопрос 1. Что сильнее всего выбивает вас из равновесия?",
        (
            QuizOption("Задержка денег или нестабильность", {"внешняя безопасность": 1}),
            QuizOption("Молчание или холод близкого человека", {"принятие и самоценность": 1}),
            QuizOption("Критика и неодобрение", {"принятие и самоценность": 1}),
            QuizOption("Потеря контроля", {"контроль и результат": 1}),
            QuizOption("Ощущение, что меня не ценят", {"принятие и самоценность": 1}),
        ),
    ),
    QuizQuestion(
        "Вопрос 2. Что вы обычно делаете, когда ситуация идёт не по плану?",
        (
            QuizOption("Начинаю всё контролировать", {"контроль и результат": 1}),
            QuizOption("Пытаюсь всем угодить", {"принятие и самоценность": 1}),
            QuizOption("Замыкаюсь и молчу", {"принятие и самоценность": 1}),
            QuizOption("Начинаю спорить и доказывать", {"принятие и самоценность": 1}),
            QuizOption(
                "Начинаю тревожно анализировать",
                {"внешняя безопасность": 1, "контроль и результат": 1},
            ),
        ),
    ),
    QuizQuestion(
        "Вопрос 3. Чего вам труднее всего не делать?",
        (
            QuizOption("Постоянно проверять сообщения и новости", {"контроль и результат": 1}),
            QuizOption("Пытаться понравиться", {"принятие и самоценность": 1}),
            QuizOption("Доказывать свою правоту", {"принятие и самоценность": 1}),
            QuizOption("Думать о худшем сценарии", {"внешняя безопасность": 1}),
            QuizOption("Вмешиваться в жизнь других", {"контроль и результат": 1}),
        ),
    ),
    QuizQuestion(
        "Вопрос 4. Что вы ожидаете получить от желаемого результата?",
        (
            QuizOption("Безопасность", {"внешняя безопасность": 1}),
            QuizOption("Любовь и принятие", {"принятие и самоценность": 1}),
            QuizOption("Уважение", {"принятие и самоценность": 1}),
            QuizOption("Свободу", {"контроль и результат": 1}),
            QuizOption("Уверенность в себе", {"принятие и самоценность": 1}),
        ),
    ),
    QuizQuestion(
        "Вопрос 5. Как вы реагируете, если результат не приходит быстро?",
        (
            QuizOption("Начинаю давить и ускорять события", {"контроль и результат": 1}),
            QuizOption("Решаю, что со мной что-то не так", {"принятие и самоценность": 1}),
            QuizOption("Теряю мотивацию", {"принятие и самоценность": 1}),
            QuizOption("Злюсь на людей и обстоятельства", {"контроль и результат": 1}),
            QuizOption("Пытаюсь заменить одну цель другой", {"внешняя безопасность": 1}),
        ),
    ),
)

RESULT_TEXTS = {
    "внешняя безопасность": (
        "Ваш ведущий сценарий сейчас — поиск безопасности во внешних обстоятельствах.\n\n"
        "Когда деньги, стабильность, отношения или гарантии становятся единственным источником "
        "опоры, их нестабильность ощущается как угроза всему состоянию. На мини-уроке вы "
        "увидите, как возвращать себе устойчивость без отрицания реальных задач."
    ),
    "принятие и самоценность": (
        "Ваш ведущий сценарий сейчас — поиск принятия и подтверждения собственной ценности "
        "во внешней реакции людей.\n\nЗдоровая опора начинается там, где можно уважать себя "
        "и свои ценности, не требуя, чтобы другие обязательно подтвердили их согласием, "
        "вниманием или выбором."
    ),
    "контроль и результат": (
        "Ваш ведущий сценарий сейчас — стремление вернуть устойчивость через контроль и "
        "быстрый результат.\n\nРезультат не всегда находится под вашим контролем. Но качество "
        "действий, честность, бережность к себе и следующий посильный шаг — находятся."
    ),
    "несколько внутренних опор": (
        "Сейчас у вас могут одновременно включаться несколько способов искать опору снаружи. "
        "Это не диагноз и не недостаток характера: так психика пытается справиться с "
        "неопределённостью привычными способами."
    ),
}

BUTTON_REPLIES: dict[str, tuple[str | None, str, list[FunnelButton]]] = {
    "Я завишу от реакции людей": (
        "зависимость от реакции людей",
        "Похоже, вам особенно важно подтверждение: что вас видят, принимают и ценят. "
        "Следующий шаг — увидеть личную цепочку этой реакции через письменную практику. "
        "Не пропустите её завтра!",
        [],
    ),
    "Я зацикливаюсь на деньгах": (
        "зацикленность на деньгах",
        "Деньги связаны со свободой, возможностями и безопасностью. Важно заметить момент, "
        "когда без конкретной суммы становится невозможно чувствовать опору. Завтра практика "
        "поможет увидеть эту цепочку.",
        [],
    ),
    "Мне сложно отпускать контроль": (
        "сложно отпускать контроль",
        "Контроль часто появляется как попытка защитить себя от неопределённости. Завтра через "
        "письменную практику вы увидите момент, где автоматический контроль уже включился, но "
        "ещё можно вернуть себе выбор.",
        [],
    ),
    "Я хочу разобрать свою ситуацию глубже": (
        "хочет разобрать ситуацию глубже",
        "Тогда следующим шагом будет небольшая письменная практика. Возьмите одну недавнюю "
        "ситуацию — не нужно искать идеальный или правильный ответ.",
        [],
    ),
    "Я заполнил(а) практику": (
        "практика заполнена",
        "Спасибо. Теперь ответьте себе: что я пытался(ась) получить внутри, что пытался(ась) "
        "контролировать и как выглядел бы мой ответ из достаточности?\n\nЗавершите фразу: «В "
        "следующий раз я замечу ______ и перед действием сделаю ______». ",
        [],
    ),
    "Показать пример": (
        None,
        "Пример: клиент не отвечал два дня. Объект — получить оплату и подтверждение заказа. "
        "Появились тревога и желание постоянно проверять телефон. Импульс — написать ещё "
        "несколько раз; краткий эффект — ощущение контроля; цена — тревога вернулась, а клиент "
        "мог почувствовать давление.",
        [FunnelButton(text="Вернуться к практике")],
    ),
    "Мне сложно выбрать ситуацию": (
        None,
        "Возьмите не самую тяжёлую историю жизни, а обычный эпизод средней силы: сообщение, "
        "покупку, разговор, рабочее решение или небольшую ссору. Важно увидеть знакомый "
        "автоматизм, а не найти идеальную проблему.",
        [FunnelButton(text="Вернуться к практике")],
    ),
    "Вернуться к практике": (None, "Вернитесь к девяти пунктам практики «Моя цепочка».", []),
    "Оставить заявку": ("заявка", "Спасибо! Мы скоро с вами свяжемся!", []),
    "Занять место": ("заявка", "Спасибо! Мы скоро с вами свяжемся!", []),
    "Не сейчас": (
        "не сейчас",
        "Хорошо. Я не буду отправлять вам частые рекламные сообщения. Вы можете выбрать, "
        "какие материалы получать дальше.",
        [FunnelButton(text="Получать материалы"), FunnelButton(text="Узнать о будущих программах")],
    ),
    "Получать материалы": (
        "получать материалы",
        "Спасибо за внимание и доверие. Буду присылать интересные материалы по теме духовного "
        "развития, тонкоплановых практик и саморазвития.",
        [],
    ),
    "Узнать о будущих программах": (
        "будущие программы",
        "Спасибо за внимание и доверие. Сообщу, когда будут интересные тренинги, курсы или "
        "мероприятия.",
        [],
    ),
    "doubt_help": (
        "сомнение: поможет ли",
        "Это разумное сомнение. Тренинг не обещает мгновенного решения всех проблем. Его задача — "
        "помочь увидеть конкретный сценарий и выбрать другое действие.",
        [FunnelButton(text="Оставить заявку")],
    ),
    "group_fear": (
        "сомнение: группа",
        "На тренинге не нужно рассказывать то, чем вы не готовы делиться. Можно пропустить "
        "вопрос, выбрать письменную работу или говорить только на безопасном для вас уровне.",
        [FunnelButton(text="Оставить заявку")],
    ),
    "not_moscow": (
        "не в москве",
        "Тренинг проходит в Москве. Если приехать не получится, можно оставить заявку на будущий "
        "онлайн- или выездной формат.",
        [FunnelButton(text="Оставить заявку на онлайн-формат")],
    ),
    "no_time": (
        "сомнение: нет времени",
        "Это не лекция, которую можно слушать фоном: в программе есть письменные практики, "
        "работа с группой и собственным запросом. Лучше приходить, когда вы сможете присутствовать "
        "полностью.",
        [FunnelButton(text="Оставить заявку")],
    ),
    "price": (
        "сомнение: дорого",
        "Решение об участии не должно приниматься из давления. Можно обсудить внутреннюю рассрочку "
        "или сервисы Долями и Яндекс Сплит на 6–12 месяцев.",
        [FunnelButton(text="Оставить заявку")],
    ),
    "format": (
        "сомнение: подходит ли формат",
        "Формат подходит тем, кто повторяет сценарии в отношениях или работе, зависит от чужого "
        "мнения и готов не только слушать, но и выполнять практики. Он не заменяет медицинское "
        "лечение или психотерапию.",
        [FunnelButton(text="Оставить заявку")],
    ),
    "Оставить заявку на онлайн-формат": (
        "онлайн-формат",
        "Спасибо! Мы свяжемся с вами, когда будет онлайн-формат.",
        [],
    ),
}


@router.message(CommandStart())
async def handle_start(message: Message, command: CommandObject) -> None:
    token = normalize_start_token(command.args)
    if token is None:
        await message.answer(
            "Чтобы получить материалы, нажмите кнопку Telegram на странице после заявки."
        )
        return
    telegram_user = message.from_user
    bot = message.bot
    if telegram_user is None or bot is None:
        await message.answer("Не удалось определить Telegram-пользователя.")
        return
    settings = get_settings()
    definition = load_most_definition(settings)
    try:
        async with async_session_maker() as session:
            result = await link_messenger_identity(
                session=session,
                token=token,
                channel=MOST_CHANNEL,
                external_user_id=str(telegram_user.id),
                username=telegram_user.username,
                display_name=telegram_user.full_name,
                raw_profile=build_raw_profile(telegram_user),
                allow_relink=True,
            )
            state = await restart_funnel_for_lead(
                session=session,
                lead_id=result.lead_id,
                definition=definition,
                messenger_channel=MOST_CHANNEL,
            )
            sender = build_sender(session, bot)
            await run_due_funnel_step(
                session=session, state=state, definition=definition, sender=sender
            )
            await session.commit()
    except ValueError:
        logger.info("Most tsennostey Telegram start rejected")
        await message.answer("Не удалось открыть материалы. Вернитесь на страницу после заявки.")


@router.message(Command("status"))
async def handle_status(message: Message) -> None:
    if message.from_user is None:
        return
    async with async_session_maker() as session:
        identity = await get_telegram_identity_by_user_id(
            session, str(message.from_user.id), channel=MOST_CHANNEL
        )
    await message.answer(
        "Подписка активна." if identity and identity.is_subscribed else "Telegram пока не привязан."
    )


@router.message(Command("stop"))
async def handle_stop(message: Message) -> None:
    if message.from_user is None:
        return
    async with async_session_maker() as session:
        stopped = await unsubscribe_telegram_identity(
            session, str(message.from_user.id), channel=MOST_CHANNEL
        )
        await session.commit()
    await message.answer("Подписка остановлена." if stopped else "Подписка не была активна.")


@router.callback_query()
async def handle_callback(callback: CallbackQuery) -> None:
    bot = callback.bot
    if callback.from_user is None or callback.data is None or bot is None:
        return
    value = parse_text_callback_data(callback.data)
    if value is None:
        return
    settings = get_settings()
    async with async_session_maker() as session:
        sender = build_sender(session, bot)
        inbound = await record_inbound_messenger_message(
            session=session,
            channel=MOST_CHANNEL,
            external_user_id=str(callback.from_user.id),
            body=value,
            external_message_id=str(callback.message.message_id) if callback.message else None,
            metadata={"source": "most_telegram_callback", "callback_data": callback.data},
        )
        handled = await handle_button(
            session=session,
            settings=settings,
            user_id=str(callback.from_user.id),
            value=value,
            sender=sender,
        )
        if handled:
            await mark_conversation_auto_handled(
                session=session, channel=MOST_CHANNEL, external_user_id=str(callback.from_user.id)
            )
        elif inbound is not None:
            await notify_admin_about_inbound_message(
                session=session, settings=settings, message=inbound
            )
        await session.commit()
    await callback.answer("Принято" if handled else None)


@router.message()
async def handle_message(message: Message) -> None:
    if message.from_user is None or message.text is None:
        return
    settings = get_settings()
    async with async_session_maker() as session:
        inbound = await record_inbound_messenger_message(
            session=session,
            channel=MOST_CHANNEL,
            external_user_id=str(message.from_user.id),
            body=message.text,
            external_message_id=str(message.message_id),
            metadata={"source": "most_telegram_message"},
        )
        if inbound is not None:
            await notify_admin_about_inbound_message(
                session=session, settings=settings, message=inbound
            )
            await session.commit()


async def handle_button(
    *,
    session: AsyncSession,
    settings: Settings,
    user_id: str,
    value: str,
    sender: MessengerFunnelStepSender,
) -> bool:
    identity = await get_telegram_identity_by_user_id(session, user_id, channel=MOST_CHANNEL)
    if identity is None:
        return False
    definition = load_most_definition(settings)
    state = await get_active_state(session, identity.lead_id)
    if state is None:
        return False
    metadata = dict(state.metadata_ or {})
    if value == "Пройти тест":
        metadata["most_quiz_index"] = 0
        metadata["most_quiz_scores"] = {}
        state.metadata_ = metadata
        await send_quiz_question(sender, identity.lead_id, 0)
        return True
    quiz_index = metadata.get("most_quiz_index")
    if isinstance(quiz_index, int) and value.startswith("q"):
        return await handle_quiz_answer(
            session=session,
            settings=settings,
            state=state,
            definition=definition,
            sender=sender,
            value=value,
            quiz_index=quiz_index,
        )
    reply = BUTTON_REPLIES.get(value)
    if reply is None:
        return False
    tag, text, buttons = reply
    if tag is not None:
        assigned = await assign_lead_tag(session, lead_id=identity.lead_id, tag=tag)
        if assigned:
            await enqueue_lead_tag_notification(
                session=session,
                settings=settings,
                lead_id=identity.lead_id,
                tag=tag,
            )
    await sender.send_text(
        lead_id=identity.lead_id, channel=MOST_CHANNEL, text=text, buttons=buttons
    )
    return True


async def handle_quiz_answer(
    *,
    session: AsyncSession,
    settings: Settings,
    state: FunnelState,
    definition: FunnelDefinition,
    sender: MessengerFunnelStepSender,
    value: str,
    quiz_index: int,
) -> bool:
    try:
        question_index, option_index = (int(part) for part in value[1:].split("-", maxsplit=1))
    except ValueError:
        return False
    if question_index != quiz_index or not 0 <= option_index < len(QUIZ[quiz_index].options):
        return False
    metadata = dict(state.metadata_ or {})
    scores = dict(metadata.get("most_quiz_scores") or {})
    for category, points in QUIZ[quiz_index].options[option_index].scores.items():
        scores[category] = int(scores.get(category, 0)) + points
    next_index = quiz_index + 1
    metadata["most_quiz_scores"] = scores
    if next_index < len(QUIZ):
        metadata["most_quiz_index"] = next_index
        state.metadata_ = metadata
        await send_quiz_question(sender, state.lead_id, next_index)
        return True
    result = quiz_result(scores)
    metadata.pop("most_quiz_index", None)
    metadata["most_quiz_result"] = result
    state.metadata_ = build_state_metadata(
        definition=definition,
        step_index=definition.step_index("lesson"),
        existing_metadata=metadata,
    )
    state.current_step_key = "lesson"
    state.next_run_at = datetime.now(UTC) + timedelta(minutes=1)
    assigned = await assign_lead_tag(
        session, lead_id=state.lead_id, tag=f"результат теста: {result}"
    )
    if assigned:
        await enqueue_lead_tag_notification(
            session=session,
            settings=settings,
            lead_id=state.lead_id,
            tag=f"результат теста: {result}",
        )
    await sender.send_text(lead_id=state.lead_id, channel=MOST_CHANNEL, text=RESULT_TEXTS[result])
    return True


async def send_quiz_question(
    sender: MessengerFunnelStepSender,
    lead_id: uuid.UUID,
    question_index: int,
) -> None:
    question = QUIZ[question_index]
    buttons = [
        FunnelButton(text=option.text, callback_data=f"q{question_index}-{option_index}")
        for option_index, option in enumerate(question.options)
    ]
    await sender.send_text(
        lead_id=lead_id, channel=MOST_CHANNEL, text=question.text, buttons=buttons
    )


def quiz_result(scores: dict[str, int]) -> str:
    ranking = sorted(scores.values(), reverse=True)
    if not ranking:
        return "несколько внутренних опор"
    leaders = [category for category, score in scores.items() if score == ranking[0]]
    if len(leaders) > 1 or (len(ranking) > 1 and ranking[0] - ranking[1] <= 1):
        return "несколько внутренних опор"
    return leaders[0]


async def get_active_state(session: AsyncSession, lead_id: uuid.UUID) -> FunnelState | None:
    return cast(
        FunnelState | None,
        await session.scalar(
            select(FunnelState).where(
                FunnelState.lead_id == lead_id,
                FunnelState.funnel_key == MOST_FUNNEL_KEY,
                FunnelState.channel == MOST_CHANNEL,
                FunnelState.status == "active",
            )
        ),
    )


def load_most_definition(settings: Settings) -> FunnelDefinition:
    definition = load_funnel_definition(settings.most_telegram_funnel_path)
    if definition.key != MOST_FUNNEL_KEY:
        raise ValueError("Most Telegram funnel has an unexpected key.")
    return definition


def build_sender(session: AsyncSession, bot: Bot) -> MessengerFunnelStepSender:
    return MessengerFunnelStepSender(
        session=session,
        telegram_bot=bot,
        vk_client=None,
        telegram_channel=MOST_CHANNEL,
    )


def normalize_start_token(args: str | None) -> str | None:
    return args.strip() or None if args is not None else None


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
    if not settings.most_telegram_bot_token:
        raise RuntimeError("MOST_TELEGRAM_BOT_TOKEN is required to run the Most Telegram bot.")
    bot = Bot(token=settings.most_telegram_bot_token)
    dispatcher = Dispatcher()
    dispatcher.include_router(router)
    try:
        logger.info("Starting Most tsennostey Telegram bot polling")
        await dispatcher.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
