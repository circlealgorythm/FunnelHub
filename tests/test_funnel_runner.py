from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from sqlalchemy import delete, select

from funnelhub.db.base import Base
from funnelhub.db.models import EmailSubscription, FunnelState, Lead, Message, MessengerIdentity
from funnelhub.db.session import async_session_maker, engine
from funnelhub.services.email_messaging import EmailProviderSendResult
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


class FakeVkClient:
    def __init__(self) -> None:
        self.peer_id: str | None = None
        self.message: str | None = None

    async def send_message(
        self,
        peer_id: int | str,
        message: str,
        *,
        keyboard: dict[str, object] | None = None,
    ) -> dict[str, int]:
        self.peer_id = str(peer_id)
        self.message = message
        return {"response": 889}


class FakeEmailClient:
    def __init__(self) -> None:
        self.to_email: str | None = None
        self.subject: str | None = None
        self.text: str | None = None

    async def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        text: str,
        html: str | None = None,
        from_email: str | None = None,
        from_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EmailProviderSendResult:
        self.to_email = to_email
        self.subject = subject
        self.text = text
        return EmailProviderSendResult(external_message_id="email-889")


class FailingEmailClient(FakeEmailClient):
    async def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        text: str,
        html: str | None = None,
        from_email: str | None = None,
        from_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EmailProviderSendResult:
        raise RuntimeError("email provider failed")


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
            await session.scalars(
                select(Lead.id).where(
                    Lead.getcourse_user_id.is_not(None),
                    Lead.getcourse_user_id >= TEST_GC_ID,
                    Lead.getcourse_user_id < TEST_GC_ID + 100,
                )
            )
        )
        if lead_ids:
            await session.execute(delete(Lead).where(Lead.id.in_(lead_ids)))
        await session.commit()


async def create_lead_with_telegram_identity(
    getcourse_user_id: int = TEST_GC_ID,
    external_user_id: str = "telegram-700",
) -> uuid.UUID:
    async with async_session_maker() as session:
        lead = Lead(id=uuid.uuid4(), getcourse_user_id=getcourse_user_id, raw_getcourse_data={})
        session.add(lead)
        await session.flush()
        session.add(
            MessengerIdentity(
                id=uuid.uuid4(),
                lead_id=lead.id,
                channel="telegram",
                external_user_id=external_user_id,
                is_subscribed=True,
                raw_profile={},
            )
        )
        await session.commit()
        return lead.id


async def create_lead_with_vk_identity() -> uuid.UUID:
    async with async_session_maker() as session:
        lead = Lead(id=uuid.uuid4(), getcourse_user_id=TEST_GC_ID, raw_getcourse_data={})
        session.add(lead)
        await session.flush()
        session.add(
            MessengerIdentity(
                id=uuid.uuid4(),
                lead_id=lead.id,
                channel="vk",
                external_user_id="vk-700",
                is_subscribed=True,
                raw_profile={},
            )
        )
        await session.commit()
        return lead.id


async def create_lead_without_identity(getcourse_user_id: int = TEST_GC_ID) -> uuid.UUID:
    async with async_session_maker() as session:
        lead = Lead(id=uuid.uuid4(), getcourse_user_id=getcourse_user_id, raw_getcourse_data={})
        session.add(lead)
        await session.commit()
        return lead.id


async def create_lead_with_email_subscription() -> uuid.UUID:
    async with async_session_maker() as session:
        lead = Lead(id=uuid.uuid4(), getcourse_user_id=TEST_GC_ID, raw_getcourse_data={})
        session.add(lead)
        await session.flush()
        session.add(
            EmailSubscription(
                id=uuid.uuid4(),
                lead_id=lead.id,
                email="runner-email@example.com",
                normalized_email="runner-email@example.com",
                status="subscribed",
            )
        )
        await session.commit()
        return lead.id


async def create_lead_with_telegram_and_vk_identities() -> uuid.UUID:
    async with async_session_maker() as session:
        lead = Lead(id=uuid.uuid4(), getcourse_user_id=TEST_GC_ID, raw_getcourse_data={})
        session.add(lead)
        await session.flush()
        session.add_all(
            [
                MessengerIdentity(
                    id=uuid.uuid4(),
                    lead_id=lead.id,
                    channel="telegram",
                    external_user_id="telegram-700",
                    is_subscribed=True,
                    raw_profile={},
                ),
                MessengerIdentity(
                    id=uuid.uuid4(),
                    lead_id=lead.id,
                    channel="vk",
                    external_user_id="vk-700",
                    is_subscribed=True,
                    raw_profile={},
                ),
            ]
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


def build_messenger_definition() -> FunnelDefinition:
    return FunnelDefinition.model_validate(
        {
            "key": "runner_test_messenger_funnel",
            "version": 1,
            "steps": [
                {
                    "key": "welcome",
                    "delay": "0m",
                    "channel": "messenger",
                    "text": "Welcome from messenger runner",
                },
            ],
        }
    )


def build_email_definition() -> FunnelDefinition:
    return FunnelDefinition.model_validate(
        {
            "key": "runner_test_email_funnel",
            "version": 1,
            "steps": [
                {
                    "key": "email_welcome",
                    "delay": "0m",
                    "channel": "email",
                    "subject": "Email welcome",
                    "text": "Welcome from email runner",
                    "buttons": [{"text": "Open", "url": "https://example.com/email"}],
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


async def test_run_due_funnel_once_sends_messenger_step_to_vk_identity(
    prepare_database: None,
) -> None:
    lead_id = await create_lead_with_vk_identity()
    definition = build_messenger_definition()
    now = datetime(2026, 5, 28, 12, 0, tzinfo=UTC)
    vk_client = FakeVkClient()

    async with async_session_maker() as session:
        await start_funnel_for_lead(session, lead_id, definition, now=now)
        await session.commit()

    async with async_session_maker() as session:
        stats = await run_due_funnel_once(
            session=session,
            definition=definition,
            vk_client=vk_client,
            now=now,
        )

    assert stats.due == 1
    assert stats.sent == 1
    assert stats.skipped == 0
    assert stats.failed == 0
    assert vk_client.peer_id == "vk-700"
    assert vk_client.message == "Welcome from messenger runner"

    async with async_session_maker() as session:
        message = await session.scalar(
            select(Message).where(
                Message.lead_id == lead_id,
                Message.channel == "vk",
                Message.direction == "outbound",
            )
        )
        assert message is not None
        assert message.status == "sent"
        assert message.external_message_id == "889"


async def test_run_due_funnel_once_uses_preferred_messenger_channel(
    prepare_database: None,
) -> None:
    lead_id = await create_lead_with_telegram_and_vk_identities()
    definition = build_messenger_definition()
    now = datetime(2026, 5, 28, 12, 0, tzinfo=UTC)
    bot = FakeTelegramBot()
    vk_client = FakeVkClient()

    async with async_session_maker() as session:
        state = await start_funnel_for_lead(session, lead_id, definition, now=now)
        state.metadata_ = {**state.metadata_, "messenger_channel": "telegram"}
        await session.commit()

    async with async_session_maker() as session:
        stats = await run_due_funnel_once(
            session=session,
            definition=definition,
            bot=bot,
            vk_client=vk_client,
            now=now,
        )

    assert stats.sent == 1
    assert stats.failed == 0
    assert bot.chat_id == "telegram-700"
    assert bot.text == "Welcome from messenger runner"
    assert vk_client.peer_id is None


async def test_run_due_funnel_once_records_failed_step_without_crashing(
    prepare_database: None,
) -> None:
    lead_id = await create_lead_without_identity()
    definition = build_messenger_definition()
    now = datetime(2026, 5, 28, 12, 0, tzinfo=UTC)

    async with async_session_maker() as session:
        await start_funnel_for_lead(session, lead_id, definition, now=now)
        await session.commit()

    async with async_session_maker() as session:
        stats = await run_due_funnel_once(
            session=session,
            definition=definition,
            bot=FakeTelegramBot(),
            vk_client=FakeVkClient(),
            now=now,
        )

    assert stats.due == 1
    assert stats.sent == 0
    assert stats.skipped == 0
    assert stats.failed == 1


async def test_run_due_funnel_once_continues_after_failed_step_rollback(
    prepare_database: None,
) -> None:
    failing_lead_id = await create_lead_without_identity(TEST_GC_ID)
    working_lead_id = await create_lead_with_telegram_identity(
        TEST_GC_ID + 1,
        "telegram-701",
    )
    definition = build_messenger_definition()
    now = datetime(2026, 5, 28, 12, 0, tzinfo=UTC)
    bot = FakeTelegramBot()

    async with async_session_maker() as session:
        failing_state = await start_funnel_for_lead(session, failing_lead_id, definition, now=now)
        failing_state.next_run_at = now - timedelta(minutes=1)
        await start_funnel_for_lead(session, working_lead_id, definition, now=now)
        await session.commit()

    async with async_session_maker() as session:
        stats = await run_due_funnel_once(
            session=session,
            definition=definition,
            bot=bot,
            vk_client=FakeVkClient(),
            now=now,
        )

    assert stats.due == 2
    assert stats.sent == 1
    assert stats.skipped == 0
    assert stats.failed == 1
    assert bot.chat_id == "telegram-701"
    assert bot.text == "Welcome from messenger runner"


async def test_run_due_funnel_once_sends_email_step(
    prepare_database: None,
) -> None:
    lead_id = await create_lead_with_email_subscription()
    definition = build_email_definition()
    now = datetime(2026, 5, 28, 12, 0, tzinfo=UTC)
    email_client = FakeEmailClient()

    async with async_session_maker() as session:
        await start_funnel_for_lead(session, lead_id, definition, now=now)
        await session.commit()

    async with async_session_maker() as session:
        stats = await run_due_funnel_once(
            session=session,
            definition=definition,
            email_client=email_client,
            public_base_url="https://bot.aisukam.ru",
            email_from_email="hello@example.com",
            email_from_name="Aisu",
            now=now,
        )

    assert stats.due == 1
    assert stats.sent == 1
    assert stats.skipped == 0
    assert stats.failed == 0
    assert email_client.to_email == "runner-email@example.com"
    assert email_client.subject == "Email welcome"
    assert email_client.text is not None
    assert "https://example.com/email" in email_client.text
    assert "https://bot.aisukam.ru/email/unsubscribe/" in email_client.text

    async with async_session_maker() as session:
        message = await session.scalar(
            select(Message).where(
                Message.lead_id == lead_id,
                Message.channel == "email",
                Message.direction == "outbound",
            )
        )
        assert message is not None
        assert message.status == "sent"
        assert message.external_message_id == "email-889"
        assert message.metadata_["subject"] == "Email welcome"
        assert message.metadata_["step_key"] == "email_welcome"

        state = await session.scalar(
            select(FunnelState).where(
                FunnelState.lead_id == lead_id,
                FunnelState.funnel_key == definition.key,
            )
        )
        assert state is not None
        assert state.status == "completed"
        assert state.current_step_key is None


async def test_run_due_funnel_once_retries_failed_email_step(
    prepare_database: None,
) -> None:
    lead_id = await create_lead_with_email_subscription()
    definition = build_email_definition()
    now = datetime(2026, 5, 28, 12, 0, tzinfo=UTC)

    async with async_session_maker() as session:
        await start_funnel_for_lead(session, lead_id, definition, now=now)
        await session.commit()

    async with async_session_maker() as session:
        stats = await run_due_funnel_once(
            session=session,
            definition=definition,
            email_client=FailingEmailClient(),
            public_base_url="https://bot.aisukam.ru",
            now=now,
        )

    assert stats.due == 1
    assert stats.sent == 0
    assert stats.skipped == 0
    assert stats.failed == 1

    async with async_session_maker() as session:
        state = await session.scalar(
            select(FunnelState).where(
                FunnelState.lead_id == lead_id,
                FunnelState.funnel_key == definition.key,
            )
        )
        assert state is not None
        assert state.status == "active"
        assert state.current_step_key == "email_welcome"
        assert state.next_run_at == now
