from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from funnelhub.config import get_settings
from funnelhub.db.base import Base
from funnelhub.db.models import Conversation, Lead, Message, MessengerIdentity
from funnelhub.db.session import async_session_maker, engine
from funnelhub.main import app
from funnelhub.services.auth import hash_password
from funnelhub.services.inbox import (
    get_inbox_conversation_detail,
    list_inbox_conversations,
    mark_conversation_auto_handled,
    record_inbound_messenger_message,
    send_inbox_reply,
)

TEST_GC_ID = 987654900


@dataclass(frozen=True)
class FakeSentMessage:
    message_id: int


class FakeTelegramBot:
    async def send_message(
        self,
        chat_id: str,
        text: str,
        *,
        reply_markup: object | None = None,
    ) -> FakeSentMessage:
        return FakeSentMessage(message_id=1001)


@dataclass(frozen=True)
class FakeClients:
    telegram_bot: FakeTelegramBot | None = None
    vk_client: object | None = None


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


async def create_lead_with_identity() -> uuid.UUID:
    async with async_session_maker() as session:
        lead = Lead(
            id=uuid.uuid4(),
            getcourse_user_id=TEST_GC_ID,
            full_name="Inbox Test",
            raw_getcourse_data={},
        )
        session.add(lead)
        await session.flush()
        session.add(
            MessengerIdentity(
                id=uuid.uuid4(),
                lead_id=lead.id,
                channel="telegram",
                external_user_id="telegram-inbox",
                username="inbox_user",
                display_name="Inbox User",
                is_subscribed=True,
                raw_profile={},
            )
        )
        session.add(
            Message(
                id=uuid.uuid4(),
                lead_id=lead.id,
                channel="telegram",
                direction="outbound",
                message_type="text",
                body="Earlier funnel message",
                status="sent",
                metadata_={},
            )
        )
        await session.commit()
        return lead.id


async def test_record_inbound_message_creates_conversation_and_links_history() -> None:
    lead_id = await create_lead_with_identity()

    async with async_session_maker() as session:
        message = await record_inbound_messenger_message(
            session=session,
            channel="telegram",
            external_user_id="telegram-inbox",
            body="Хочу консультацию",
            external_message_id="tg-1",
        )
        await session.commit()

    assert message is not None

    async with async_session_maker() as session:
        conversation = await session.scalar(
            select(Conversation).where(
                Conversation.lead_id == lead_id,
                Conversation.channel == "telegram",
            )
        )
        assert conversation is not None
        assert conversation.status == "needs_reply"

        messages = (
            await session.scalars(
                select(Message)
                .where(Message.conversation_id == conversation.id)
                .order_by(Message.created_at.asc())
            )
        ).all()
        assert [message.direction for message in messages] == ["outbound", "inbound"]
        assert messages[-1].body == "Хочу консультацию"


async def test_mark_conversation_auto_handled_reopens_needs_reply() -> None:
    await create_lead_with_identity()

    async with async_session_maker() as session:
        await record_inbound_messenger_message(
            session=session,
            channel="telegram",
            external_user_id="telegram-inbox",
            body="Деньги",
        )
        await mark_conversation_auto_handled(
            session=session,
            channel="telegram",
            external_user_id="telegram-inbox",
        )
        await session.commit()

    async with async_session_maker() as session:
        conversation = await session.scalar(select(Conversation))
        assert conversation is not None
        assert conversation.status == "open"


async def test_send_inbox_reply_records_outbound_reply_on_conversation() -> None:
    await create_lead_with_identity()

    async with async_session_maker() as session:
        inbound = await record_inbound_messenger_message(
            session=session,
            channel="telegram",
            external_user_id="telegram-inbox",
            body="Нужен ответ",
        )
        assert inbound is not None
        message = await send_inbox_reply(
            session=session,
            conversation_id=inbound.conversation_id,
            text="Отвечаем из inbox",
            clients=FakeClients(telegram_bot=FakeTelegramBot()),
        )
        await session.commit()

    async with async_session_maker() as session:
        conversation = await session.get(Conversation, inbound.conversation_id)
        assert conversation is not None
        assert conversation.status == "replied"

        saved_message = await session.get(Message, message.id)
        assert saved_message is not None
        assert saved_message.conversation_id == conversation.id
        assert saved_message.direction == "outbound"
        assert saved_message.body == "Отвечаем из inbox"


async def test_list_and_detail_inbox_conversations() -> None:
    await create_lead_with_identity()

    async with async_session_maker() as session:
        inbound = await record_inbound_messenger_message(
            session=session,
            channel="telegram",
            external_user_id="telegram-inbox",
            body="Покажите в API",
        )
        await session.commit()

    assert inbound is not None
    async with async_session_maker() as session:
        summaries = await list_inbox_conversations(session)
        assert len(summaries) == 1
        assert summaries[0].lead_name == "Inbox Test"
        assert summaries[0].last_message_body == "Покажите в API"
        assert summaries[0].unread_count == 1

        detail = await get_inbox_conversation_detail(session, inbound.conversation_id)
        assert detail is not None
        assert [message.body for message in detail.messages] == [
            "Earlier funnel message",
            "Покажите в API",
        ]


async def test_inbox_api_lists_and_returns_conversation_detail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_auth(monkeypatch)
    await create_lead_with_identity()

    try:
        async with async_session_maker() as session:
            inbound = await record_inbound_messenger_message(
                session=session,
                channel="telegram",
                external_user_id="telegram-inbox",
                body="API message",
            )
            await session.commit()

        assert inbound is not None
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
        ) as client:
            login_response = await client.post(
                "/api/auth/login",
                json={"username": "aisu", "password": "secret"},
            )
            list_response = await client.get("/api/inbox/conversations")
            detail_response = await client.get(
                f"/api/inbox/conversations/{inbound.conversation_id}"
            )
    finally:
        get_settings.cache_clear()

    assert login_response.status_code == 200
    assert list_response.status_code == 200
    assert list_response.json()[0]["last_message_body"] == "API message"
    assert detail_response.status_code == 200
    assert detail_response.json()["messages"][-1]["body"] == "API message"


def configure_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("INBOX_ADMIN_USERNAME", "aisu")
    monkeypatch.setenv(
        "INBOX_ADMIN_PASSWORD_HASH",
        hash_password("secret", salt=b"1234567890123456"),
    )
    monkeypatch.setenv("INBOX_SESSION_SECRET", "test-session-secret")
    get_settings.cache_clear()
