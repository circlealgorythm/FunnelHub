from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import delete, select

from funnelhub.config import Settings
from funnelhub.db.base import Base
from funnelhub.db.models import Conversation, Lead, LeadContact, Message, MessengerIdentity
from funnelhub.db.session import async_session_maker, engine
from funnelhub.services.inbox_notifications import (
    build_admin_notification_text,
    build_inbox_link,
    notify_admin_about_inbound_message,
)

TEST_GC_ID = 987655100


class FakeNotificationClient:
    def __init__(self) -> None:
        self.chat_id: int | str | None = None
        self.text: str | None = None

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        *,
        disable_web_page_preview: bool | None = None,
    ) -> None:
        self.chat_id = chat_id
        self.text = text


@pytest.fixture(autouse=True)
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


async def create_inbound_message() -> uuid.UUID:
    async with async_session_maker() as session:
        lead = Lead(
            id=uuid.uuid4(),
            getcourse_user_id=TEST_GC_ID,
            full_name="Aisu Inbox Lead",
            raw_getcourse_data={},
        )
        session.add(lead)
        await session.flush()
        conversation = Conversation(
            id=uuid.uuid4(),
            lead_id=lead.id,
            channel="telegram",
            status="needs_reply",
        )
        session.add(conversation)
        session.add(
            MessengerIdentity(
                id=uuid.uuid4(),
                lead_id=lead.id,
                channel="telegram",
                external_user_id="tg-100",
                username="lead_user",
                display_name="Lead User",
                is_subscribed=True,
                raw_profile={},
            )
        )
        session.add(
            LeadContact(
                id=uuid.uuid4(),
                lead_id=lead.id,
                contact_type="email",
                value="lead@example.com",
                normalized_value="lead@example.com",
                is_primary=True,
            )
        )
        message = Message(
            id=uuid.uuid4(),
            lead_id=lead.id,
            conversation_id=conversation.id,
            channel="telegram",
            direction="inbound",
            message_type="text",
            body="Здравствуйте, хочу личную консультацию",
            status="received",
            metadata_={},
        )
        session.add(message)
        await session.commit()
        return message.id


async def test_build_admin_notification_text() -> None:
    message_id = await create_inbound_message()
    settings = notification_settings()

    async with async_session_maker() as session:
        message = await session.get(Message, message_id)
        assert message is not None
        text = await build_admin_notification_text(session, settings=settings, message=message)

    assert "Новое сообщение в Inbox" in text
    assert "Канал: Telegram" in text
    assert "Лид: Aisu Inbox Lead" in text
    assert "lead@example.com" in text
    assert "Здравствуйте, хочу личную консультацию" in text
    assert "http://inbox.local?conversation=" in text


async def test_notify_admin_about_inbound_message_sends_when_configured() -> None:
    message_id = await create_inbound_message()
    settings = notification_settings()
    client = FakeNotificationClient()

    async with async_session_maker() as session:
        message = await session.get(Message, message_id)
        assert message is not None
        sent = await notify_admin_about_inbound_message(
            session,
            settings=settings,
            message=message,
            client=client,
        )

    assert sent is True
    assert client.chat_id == "12345"
    assert client.text is not None
    assert "Aisu Inbox Lead" in client.text


async def test_notify_admin_about_inbound_message_skips_without_config() -> None:
    message_id = await create_inbound_message()
    settings = Settings(
        inbox_notify_telegram_bot_token=None,
        inbox_notify_telegram_chat_id=None,
    )
    client = FakeNotificationClient()

    async with async_session_maker() as session:
        message = await session.get(Message, message_id)
        assert message is not None
        sent = await notify_admin_about_inbound_message(
            session,
            settings=settings,
            message=message,
            client=client,
        )

    assert sent is False
    assert client.text is None


def test_build_inbox_link() -> None:
    conversation_id = uuid.uuid4()
    settings = notification_settings()

    assert build_inbox_link(settings, conversation_id) == (
        f"http://inbox.local?conversation={conversation_id}"
    )


def notification_settings() -> Settings:
    return Settings(
        inbox_app_url="http://inbox.local",
        inbox_notify_telegram_bot_token="notify-token",
        inbox_notify_telegram_chat_id="12345",
    )
