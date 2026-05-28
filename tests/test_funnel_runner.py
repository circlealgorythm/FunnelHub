from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select

from funnelhub.db.base import Base
from funnelhub.db.models import FunnelState, Lead, Message, MessengerIdentity
from funnelhub.db.session import async_session_maker, engine
from funnelhub.services.funnel_engine import FunnelDefinition, start_funnel_for_lead
from funnelhub.services.funnel_runner import run_due_funnel_once

TEST_GC_ID = 987654700


@dataclass(frozen=True)
class FakeSentMessage:
    message_id: int


class FakeTelegramBot:
    def __init__(self) -> None:
        self.chat_id: str | None = None
        self.text: str | None = None

    async def send_message(
        self,
        chat_id: str,
        text: str,
        reply_markup: object | None = None,
    ) -> FakeSentMessage:
        self.chat_id = chat_id
        self.text = text
        return FakeSentMessage(message_id=888)


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


async def create_lead_with_telegram_identity() -> uuid.UUID:
    async with async_session_maker() as session:
        lead = Lead(id=uuid.uuid4(), getcourse_user_id=TEST_GC_ID, raw_getcourse_data={})
        session.add(lead)
        await session.flush()
        session.add(
            MessengerIdentity(
                id=uuid.uuid4(),
                lead_id=lead.id,
                channel="telegram",
                external_user_id="telegram-700",
                is_subscribed=True,
                raw_profile={},
            )
        )
        await session.commit()
        return lead.id


def build_definition() -> FunnelDefinition:
    return FunnelDefinition.model_validate(
        {
            "key": "runner_test_funnel",
            "version": 1,
            "steps": [
                {
                    "key": "welcome",
                    "delay": "0m",
                    "channel": "telegram",
                    "text": "Welcome from runner",
                    "buttons": [{"text": "Open", "url": "https://example.com"}],
                },
                {
                    "key": "follow_up",
                    "delay": "1d",
                    "channel": "telegram",
                    "text": "Follow up",
                },
            ],
        }
    )


async def test_run_due_funnel_once_sends_telegram_step_and_advances_state(
    prepare_database: None,
) -> None:
    lead_id = await create_lead_with_telegram_identity()
    definition = build_definition()
    now = datetime(2026, 5, 28, 12, 0, tzinfo=UTC)
    bot = FakeTelegramBot()

    async with async_session_maker() as session:
        await start_funnel_for_lead(session, lead_id, definition, now=now)
        await session.commit()

    async with async_session_maker() as session:
        stats = await run_due_funnel_once(
            session=session,
            definition=definition,
            bot=bot,
            now=now,
        )

    assert stats.due == 1
    assert stats.sent == 1
    assert stats.skipped == 0
    assert stats.failed == 0
    assert bot.chat_id == "telegram-700"
    assert bot.text == "Welcome from runner"

    async with async_session_maker() as session:
        message = await session.scalar(
            select(Message).where(
                Message.lead_id == lead_id,
                Message.channel == "telegram",
                Message.direction == "outbound",
            )
        )
        assert message is not None
        assert message.status == "sent"
        assert message.external_message_id == "888"
        assert message.metadata_["buttons"][0]["url"] == "https://example.com"

        state = await session.scalar(
            select(FunnelState).where(
                FunnelState.lead_id == lead_id,
                FunnelState.funnel_key == definition.key,
            )
        )
        assert state is not None
        assert state.status == "active"
        assert state.current_step_key == "follow_up"
        assert state.next_run_at is not None
        assert state.next_run_at > now
