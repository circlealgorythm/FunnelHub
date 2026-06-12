from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
from sqlalchemy import delete, select

from funnelhub.db.base import Base
from funnelhub.db.models import Lead, Message, MessengerIdentity
from funnelhub.db.session import async_session_maker, engine
from funnelhub.services.vk_messaging import (
    VK_BUTTON_LABEL_MAX_LENGTH,
    VkTextButton,
    VkUrlButton,
    build_message_metadata,
    build_url_keyboard,
    send_vk_text_message,
    unsubscribe_vk_identity,
)

TEST_GC_ID = 987654800


class FakeVkClient:
    def __init__(self) -> None:
        self.peer_id: str | None = None
        self.message: str | None = None
        self.keyboard: dict[str, object] | None = None

    async def send_message(
        self,
        peer_id: int | str,
        message: str,
        *,
        keyboard: dict[str, object] | None = None,
    ) -> dict[str, int]:
        self.peer_id = str(peer_id)
        self.message = message
        self.keyboard = keyboard
        return {"response": 999}


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


async def create_lead_with_vk_identity(is_subscribed: bool = True) -> uuid.UUID:
    async with async_session_maker() as session:
        lead = Lead(id=uuid.uuid4(), getcourse_user_id=TEST_GC_ID, raw_getcourse_data={})
        session.add(lead)
        await session.flush()
        session.add(
            MessengerIdentity(
                id=uuid.uuid4(),
                lead_id=lead.id,
                channel="vk",
                external_user_id="vk-800",
                is_subscribed=is_subscribed,
                raw_profile={},
            )
        )
        await session.commit()
        return lead.id


def test_build_url_keyboard_and_metadata() -> None:
    buttons = [VkUrlButton(text="Open", url="https://example.com")]

    keyboard = build_url_keyboard(buttons)

    assert keyboard is not None
    assert keyboard["inline"] is True
    assert keyboard["buttons"][0][0]["action"]["type"] == "open_link"
    assert keyboard["buttons"][0][0]["action"]["link"] == "https://example.com"
    assert build_message_metadata(buttons) == {
        "buttons": [{"type": "url", "text": "Open", "url": "https://example.com"}]
    }


def test_build_text_keyboard_uses_primary_color() -> None:
    buttons = [VkTextButton(text="Деньги")]

    keyboard = build_url_keyboard(buttons)

    assert keyboard is not None
    assert keyboard["buttons"][0][0]["action"]["type"] == "text"
    assert keyboard["buttons"][0][0]["action"]["label"] == "Деньги"
    assert keyboard["buttons"][0][0]["color"] == "primary"


def test_build_url_keyboard_truncates_labels_to_vk_limit() -> None:
    long_label = "Очень длинная подпись кнопки для ВКонтакте больше лимита"
    buttons = [VkUrlButton(text=long_label, url="https://example.com")]

    keyboard = build_url_keyboard(buttons)

    assert keyboard is not None
    label = keyboard["buttons"][0][0]["action"]["label"]
    assert len(label) == VK_BUTTON_LABEL_MAX_LENGTH
    assert label == long_label[:VK_BUTTON_LABEL_MAX_LENGTH]
    assert build_message_metadata(buttons)["buttons"][0]["text"] == long_label


async def test_send_vk_text_message_records_outbound_message() -> None:
    lead_id = await create_lead_with_vk_identity()
    fake_client = FakeVkClient()

    async with async_session_maker() as session:
        result = await send_vk_text_message(
            session=session,
            client=fake_client,
            lead_id=lead_id,
            text="Hello",
            url_buttons=[VkUrlButton(text="Open", url="https://example.com")],
        )
        await session.commit()

    assert fake_client.peer_id == "vk-800"
    assert fake_client.message == "Hello"
    assert result.external_message_id == "999"

    async with async_session_maker() as session:
        message = await session.get(Message, result.message_id)
        assert message is not None
        assert message.lead_id == lead_id
        assert message.channel == "vk"
        assert message.direction == "outbound"
        assert message.status == "sent"
        assert message.external_message_id == "999"
        assert message.metadata_["buttons"][0]["url"] == "https://example.com"


async def test_send_vk_text_message_rejects_unsubscribed_identity() -> None:
    lead_id = await create_lead_with_vk_identity(is_subscribed=False)

    async with async_session_maker() as session:
        with pytest.raises(ValueError, match="Lead has no subscribed VK identity."):
            await send_vk_text_message(
                session=session,
                client=FakeVkClient(),
                lead_id=lead_id,
                text="Hello",
            )


async def test_unsubscribe_vk_identity() -> None:
    await create_lead_with_vk_identity()

    async with async_session_maker() as session:
        assert await unsubscribe_vk_identity(session, "vk-800") is True
        await session.commit()

    async with async_session_maker() as session:
        identity = await session.scalar(
            select(MessengerIdentity).where(MessengerIdentity.external_user_id == "vk-800")
        )
        assert identity is not None
        assert identity.is_subscribed is False
        assert identity.unsubscribed_at is not None
