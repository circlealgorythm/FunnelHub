from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from typing import Protocol, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.db.models import FunnelState, MessengerIdentity
from funnelhub.services.funnel_engine import (
    FunnelButton,
    FunnelDefinition,
    FunnelQuestion,
    normalize_datetime,
)

PERSONALIZED_RESPONSE_TO_FIRST_VIDEO_DELAY = timedelta(minutes=1)


class FunnelTextSender(Protocol):
    async def send_text(
        self,
        lead_id: uuid.UUID,
        channel: str,
        text: str,
        buttons: list[FunnelButton] | None = None,
    ) -> None: ...


async def handle_funnel_text_reply(
    session: AsyncSession,
    definition: FunnelDefinition,
    channel: str,
    external_user_id: str,
    text: str,
    sender: FunnelTextSender,
    now: datetime | None = None,
) -> bool:
    if definition.questionnaire is None:
        return False

    identity = await get_identity(session, channel, external_user_id)
    if identity is None:
        return False

    state = await get_active_funnel_state(session, identity.lead_id, definition.key)
    if state is None:
        return False

    current_time = normalize_datetime(now)
    metadata = dict(state.metadata_ or {})
    answers = dict(metadata.get("answers") or {})

    topic_question = definition.questionnaire.questions.get("topic")
    experience_question = definition.questionnaire.questions.get("experience")
    if topic_question is None or experience_question is None:
        return False

    if "topic" not in answers:
        topic_answer = match_question_option(topic_question, text)
        if topic_answer is None:
            return False

        answers["topic"] = topic_answer
        metadata["answers"] = answers
        metadata["pending_question_key"] = "experience"
        metadata["last_question_sent_at"] = current_time.isoformat()
        state.metadata_ = metadata
        await sender.send_text(
            lead_id=identity.lead_id,
            channel=channel,
            text=experience_question.text,
            buttons=question_buttons(experience_question),
        )
        await session.flush()
        return True

    if "experience" not in answers:
        experience_answer = match_question_option(experience_question, text)
        if experience_answer is None:
            return False

        answers["experience"] = experience_answer
        metadata["answers"] = answers
        metadata.pop("pending_question_key", None)
        metadata["personalized_sent_at"] = current_time.isoformat()
        waiting_step_key = metadata.pop("questionnaire_waiting_for_step_key", None)
        state.metadata_ = metadata
        if state.current_step_key == waiting_step_key:
            state.next_run_at = current_time + PERSONALIZED_RESPONSE_TO_FIRST_VIDEO_DELAY
        response_text = get_personalized_response(definition, answers["topic"], experience_answer)
        if response_text is not None:
            await sender.send_text(
                lead_id=identity.lead_id,
                channel=channel,
                text=response_text,
            )
        await session.flush()
        return True

    return False


async def send_pending_question_reminder(
    session: AsyncSession,
    state: FunnelState,
    definition: FunnelDefinition,
    sender: FunnelTextSender,
    now: datetime | None = None,
) -> bool:
    if definition.questionnaire is None:
        return False

    metadata = dict(state.metadata_ or {})
    question_key = metadata.get("pending_question_key")
    if not isinstance(question_key, str):
        return False

    question = definition.questionnaire.questions.get(question_key)
    if question is None:
        return False

    current_time = normalize_datetime(now)
    preferred_channel = metadata.get("messenger_channel")
    identity = await get_subscribed_identity(
        session,
        state.lead_id,
        preferred_channel if isinstance(preferred_channel, str) else None,
    )
    if identity is None:
        return False

    await sender.send_text(
        lead_id=state.lead_id,
        channel=identity.channel,
        text=question.text,
        buttons=question_buttons(question),
    )
    metadata["last_question_sent_at"] = current_time.isoformat()
    state.metadata_ = metadata
    await session.flush()
    return True


async def get_identity(
    session: AsyncSession,
    channel: str,
    external_user_id: str,
) -> MessengerIdentity | None:
    return cast(
        MessengerIdentity | None,
        await session.scalar(
        select(MessengerIdentity).where(
            MessengerIdentity.channel == channel,
            MessengerIdentity.external_user_id == external_user_id,
        )
        ),
    )


async def get_subscribed_identity(
    session: AsyncSession,
    lead_id: uuid.UUID,
    preferred_channel: str | None = None,
) -> MessengerIdentity | None:
    if preferred_channel is not None:
        return cast(
            MessengerIdentity | None,
            await session.scalar(
                select(MessengerIdentity).where(
                    MessengerIdentity.lead_id == lead_id,
                    MessengerIdentity.is_subscribed.is_(True),
                    MessengerIdentity.channel == preferred_channel,
                )
            ),
        )

    return cast(
        MessengerIdentity | None,
        await session.scalar(
        select(MessengerIdentity)
        .where(
            MessengerIdentity.lead_id == lead_id,
            MessengerIdentity.is_subscribed.is_(True),
            MessengerIdentity.channel.in_(["telegram", "vk"]),
        )
        .order_by(MessengerIdentity.created_at.desc())
        ),
    )


async def get_active_funnel_state(
    session: AsyncSession,
    lead_id: uuid.UUID,
    funnel_key: str,
) -> FunnelState | None:
    return cast(
        FunnelState | None,
        await session.scalar(
        select(FunnelState).where(
            FunnelState.lead_id == lead_id,
            FunnelState.funnel_key == funnel_key,
            FunnelState.status == "active",
        )
        ),
    )


def question_buttons(question: FunnelQuestion) -> list[FunnelButton]:
    return [FunnelButton(text=option.text) for option in question.options]


def match_question_option(question: FunnelQuestion, text: str) -> str | None:
    normalized_text = normalize_answer_text(text)
    for option in question.options:
        if normalized_text in {
            normalize_answer_text(option.key),
            normalize_answer_text(option.text),
        }:
            return option.key
    return None


def get_personalized_response(
    definition: FunnelDefinition,
    topic_key: str,
    experience_key: str,
) -> str | None:
    if definition.questionnaire is None:
        return None
    return definition.questionnaire.personalized_responses.get(topic_key, {}).get(experience_key)


def normalize_answer_text(text: str) -> str:
    return " ".join(text.strip().lower().replace("ё", "е").split())

