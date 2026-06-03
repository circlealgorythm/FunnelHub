from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import delete, select

from funnelhub.db.base import Base
from funnelhub.db.models import FunnelState, Lead, MessengerIdentity
from funnelhub.db.session import async_session_maker, engine
from funnelhub.services.funnel_answers import (
    handle_funnel_text_reply,
    send_pending_question_reminder,
)
from funnelhub.services.funnel_engine import FunnelButton, FunnelDefinition

TEST_GC_ID = 987654900


@dataclass
class SentText:
    lead_id: uuid.UUID
    channel: str
    text: str
    buttons: list[FunnelButton]


@dataclass
class FakeFunnelTextSender:
    sent: list[SentText] = field(default_factory=list)

    async def send_text(
        self,
        lead_id: uuid.UUID,
        channel: str,
        text: str,
        buttons: list[FunnelButton] | None = None,
    ) -> None:
        self.sent.append(
            SentText(
                lead_id=lead_id,
                channel=channel,
                text=text,
                buttons=buttons or [],
            )
        )


@pytest.fixture
async def prepare_database() -> AsyncGenerator[None]:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    await cleanup_test_leads()
    yield
    await cleanup_test_leads()
    await engine.dispose()


async def cleanup_test_leads() -> None:
    async with async_session_maker() as session:
        lead_ids = set(
            await session.scalars(select(Lead.id).where(Lead.getcourse_user_id == TEST_GC_ID))
        )
        if lead_ids:
            await session.execute(delete(Lead).where(Lead.id.in_(lead_ids)))
        await session.commit()


def build_definition() -> FunnelDefinition:
    return FunnelDefinition.model_validate(
        {
            "key": "answer_test_funnel",
            "version": 1,
            "questionnaire": {
                "questions": {
                    "topic": {
                        "key": "topic",
                        "text": "Что актуальнее?",
                        "options": [{"key": "money", "text": "Деньги"}],
                    },
                    "experience": {
                        "key": "experience",
                        "text": "Был опыт?",
                        "options": [{"key": "newbie", "text": "Нет, я новичок"}],
                    },
                },
                "personalized_responses": {
                    "money": {"newbie": "Персональный ответ для новичка про деньги"}
                },
            },
            "steps": [
                {
                    "key": "welcome",
                    "delay": "0m",
                    "channel": "messenger",
                    "text": "Welcome",
                }
            ],
        }
    )


async def create_lead_identity_and_state(
    metadata: dict[str, object],
    current_step_key: str = "welcome",
    next_run_at: datetime | None = None,
    include_vk_identity: bool = False,
) -> uuid.UUID:
    async with async_session_maker() as session:
        lead = Lead(id=uuid.uuid4(), getcourse_user_id=TEST_GC_ID, raw_getcourse_data={})
        session.add(lead)
        await session.flush()
        session.add(
            MessengerIdentity(
                id=uuid.uuid4(),
                lead_id=lead.id,
                channel="telegram",
                external_user_id="telegram-900",
                is_subscribed=True,
                raw_profile={},
            )
        )
        if include_vk_identity:
            session.add(
                MessengerIdentity(
                    id=uuid.uuid4(),
                    lead_id=lead.id,
                    channel="vk",
                    external_user_id="vk-900",
                    is_subscribed=True,
                    raw_profile={},
                )
            )
        session.add(
            FunnelState(
                id=uuid.uuid4(),
                lead_id=lead.id,
                funnel_key="answer_test_funnel",
                status="active",
                current_step_key=current_step_key,
                next_run_at=next_run_at,
                metadata_=metadata,
            )
        )
        await session.commit()
        return lead.id


async def test_handle_funnel_text_reply_asks_second_question_after_topic_answer(
    prepare_database: None,
) -> None:
    now = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
    lead_id = await create_lead_identity_and_state(
        metadata={"questionnaire_waiting_for_step_key": "step_01"},
        current_step_key="step_01",
        next_run_at=now + timedelta(minutes=3),
    )
    definition = build_definition()
    sender = FakeFunnelTextSender()

    async with async_session_maker() as session:
        handled = await handle_funnel_text_reply(
            session=session,
            definition=definition,
            channel="telegram",
            external_user_id="telegram-900",
            text="Деньги",
            sender=sender,
            now=now,
        )
        await session.commit()

    assert handled is True
    assert sender.sent == [
        SentText(
            lead_id=lead_id,
            channel="telegram",
            text="Был опыт?",
            buttons=[FunnelButton(text="Нет, я новичок")],
        )
    ]

    async with async_session_maker() as session:
        state = await session.scalar(select(FunnelState).where(FunnelState.lead_id == lead_id))
        assert state is not None
        assert state.metadata_["answers"] == {"topic": "money"}
        assert state.metadata_["pending_question_key"] == "experience"
        assert state.next_run_at == now + timedelta(minutes=5)


async def test_handle_funnel_text_reply_sends_personalized_response_after_second_answer(
    prepare_database: None,
) -> None:
    now = datetime(2026, 6, 1, 10, 0, tzinfo=UTC)
    lead_id = await create_lead_identity_and_state(
        metadata={
            "answers": {"topic": "money"},
            "pending_question_key": "experience",
            "questionnaire_waiting_for_step_key": "step_01",
        },
        current_step_key="step_01",
        next_run_at=now + timedelta(minutes=3),
    )
    definition = build_definition()
    sender = FakeFunnelTextSender()

    async with async_session_maker() as session:
        handled = await handle_funnel_text_reply(
            session=session,
            definition=definition,
            channel="telegram",
            external_user_id="telegram-900",
            text="Нет, я новичок",
            sender=sender,
            now=now,
        )
        await session.commit()

    assert handled is True
    assert sender.sent == [
        SentText(
            lead_id=lead_id,
            channel="telegram",
            text="Персональный ответ для новичка про деньги",
            buttons=[],
        )
    ]

    async with async_session_maker() as session:
        state = await session.scalar(select(FunnelState).where(FunnelState.lead_id == lead_id))
        assert state is not None
        assert state.metadata_["answers"] == {"topic": "money", "experience": "newbie"}
        assert "pending_question_key" not in state.metadata_
        assert "questionnaire_waiting_for_step_key" not in state.metadata_
        assert state.next_run_at == now


async def test_send_pending_question_reminder_respects_reminder_delay(
    prepare_database: None,
) -> None:
    lead_id = await create_lead_identity_and_state(
        metadata={
            "pending_question_key": "topic",
            "last_question_sent_at": datetime(2026, 6, 1, 10, 0, tzinfo=UTC).isoformat(),
        }
    )
    definition = build_definition()
    sender = FakeFunnelTextSender()

    async with async_session_maker() as session:
        state = await session.scalar(select(FunnelState).where(FunnelState.lead_id == lead_id))
        assert state is not None
        too_early = await send_pending_question_reminder(
            session=session,
            state=state,
            definition=definition,
            sender=sender,
            now=datetime(2026, 6, 1, 10, 4, tzinfo=UTC),
        )
        later = await send_pending_question_reminder(
            session=session,
            state=state,
            definition=definition,
            sender=sender,
            now=datetime(2026, 6, 1, 10, 5, tzinfo=UTC),
        )
        await session.commit()

    assert too_early is False
    assert later is True
    assert sender.sent[0].text == "Что актуальнее?"
    assert sender.sent[0].buttons == [FunnelButton(text="Деньги")]


async def test_send_pending_question_reminder_prefers_state_messenger_channel(
    prepare_database: None,
) -> None:
    lead_id = await create_lead_identity_and_state(
        metadata={
            "messenger_channel": "telegram",
            "pending_question_key": "topic",
            "last_question_sent_at": datetime(2026, 6, 1, 10, 0, tzinfo=UTC).isoformat(),
        },
        include_vk_identity=True,
    )
    definition = build_definition()
    sender = FakeFunnelTextSender()

    async with async_session_maker() as session:
        state = await session.scalar(select(FunnelState).where(FunnelState.lead_id == lead_id))
        assert state is not None
        sent = await send_pending_question_reminder(
            session=session,
            state=state,
            definition=definition,
            sender=sender,
            now=datetime(2026, 6, 1, 10, 5, tzinfo=UTC),
        )
        await session.commit()

    assert sent is True
    assert sender.sent == [
        SentText(
            lead_id=lead_id,
            channel="telegram",
            text="Что актуальнее?",
            buttons=[FunnelButton(text="Деньги")],
        )
    ]
