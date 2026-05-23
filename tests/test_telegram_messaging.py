from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass

import pytest
from sqlalchemy import delete, select

from funnelhub.db.base import Base
from funnelhub.db.models import Lead, Message, MessengerIdentity
from funnelhub.db.session import async_session_maker, engine
from funnelhub.services.telegram_messaging import (
    TelegramUrlButton,
    build_message_metadata,
    build_url_keyboard,
    send_telegram_text_message,
    unsubscribe_telegram_identity,
)

TEST_GC_ID = 987654500


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
        return FakeSentMessage(message_id=777)


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


async def create_lead_with_telegram_identity(is_subscribed: bool = True) -> uuid.UUID:
    async with async_session_maker() as session:
        lead = Lead(id=uuid.uuid4(), getcourse_user_id=TEST_GC_ID, raw_getcourse_data={})
        session.add(lead)
        await session.flush()
        session.add(
            MessengerIdentity(
                id=uuid.uuid4(),
                lead_id=lead.id,
                channel="telegram",
                external_user_id="telegram-500",
                is_subscribed=is_subscribed,
                raw_profile={},
            )
        )
        await session.commit()
        return lead.id


def test_build_url_keyboard_and_metadata() -> None:
    buttons = [TelegramUrlButton(text="Open", url="https://example.com")]

    keyboard = build_url_keyboard(buttons)

    assert keyboard is not None
    assert keyboard.inline_keyboard[0][0].text == "Open"
    assert keyboard.inline_keyboard[0][0].url == "https://example.com"
    assert build_message_metadata(buttons) == {
        "buttons": [{"type": "url", "text": "Open", "url": "https://example.com"}]
    }


async def test_send_telegram_text_message_records_outbound_message() -> None:
    lead_id = await create_lead_with_telegram_identity()
    fake_bot = FakeTelegramBot()

    async with async_session_maker() as session:
        result = await send_telegram_text_message(
            session=session,
            bot=fake_bot,
            lead_id=lead_id,
            text="Hello",
            url_buttons=[TelegramUrlButton(text="Open", url="https://example.com")],
        )
        await session.commit()

    assert fake_bot.chat_id == "telegram-500"
    assert fake_bot.text == "Hello"
    assert result.external_message_id == "777"

    async with async_session_maker() as session:
        message = await session.get(Message, result.message_id)
        assert message is not None
        assert message.lead_id == lead_id
        assert message.channel == "telegram"
        assert message.direction == "outbound"
        assert message.status == "sent"
        assert message.external_message_id == "777"
        assert message.metadata_["buttons"][0]["url"] == "https://example.com"


async def test_send_telegram_text_message_rejects_unsubscribed_identity() -> None:
    lead_id = await create_lead_with_telegram_identity(is_subscribed=False)

    async with async_session_maker() as session:
        with pytest.raises(ValueError, match="Lead has no subscribed Telegram identity."):
            await send_telegram_text_message(
                session=session,
                bot=FakeTelegramBot(),
                lead_id=lead_id,
                text="Hello",
            )


async def test_unsubscribe_telegram_identity() -> None:
    await create_lead_with_telegram_identity()

    async with async_session_maker() as session:
        assert await unsubscribe_telegram_identity(session, "telegram-500") is True
        await session.commit()

    async with async_session_maker() as session:
        identity = await session.scalar(
            select(MessengerIdentity).where(MessengerIdentity.external_user_id == "telegram-500")
        )
        assert identity is not None
        assert identity.is_subscribed is False
        assert identity.unsubscribed_at is not None
