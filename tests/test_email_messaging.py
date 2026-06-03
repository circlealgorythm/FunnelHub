from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from funnelhub.db.base import Base
from funnelhub.db.models import EmailSubscription, Event, Lead, Message
from funnelhub.db.session import async_session_maker, engine
from funnelhub.main import app
from funnelhub.services.email_messaging import (
    EmailProviderSendResult,
    send_email_text_message,
)

TEST_GC_ID = 987654800
TEST_EMAIL = "email-test@example.com"


class FakeEmailClient:
    def __init__(self) -> None:
        self.to_email: str | None = None
        self.subject: str | None = None
        self.text: str | None = None
        self.metadata: dict[str, Any] | None = None

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
        self.metadata = metadata
        return EmailProviderSendResult(
            external_message_id="email-123",
            raw_response={"provider": "fake"},
        )


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
        raise RuntimeError("provider is down")


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


async def create_lead_with_email_subscription(
    *,
    status: str = "subscribed",
    unsubscribe_token: str | None = None,
) -> uuid.UUID:
    async with async_session_maker() as session:
        lead = Lead(id=uuid.uuid4(), getcourse_user_id=TEST_GC_ID, raw_getcourse_data={})
        session.add(lead)
        await session.flush()
        session.add(
            EmailSubscription(
                id=uuid.uuid4(),
                lead_id=lead.id,
                email=TEST_EMAIL,
                normalized_email=TEST_EMAIL,
                status=status,
                unsubscribe_token=unsubscribe_token,
            )
        )
        await session.commit()
        return lead.id


async def test_send_email_text_message_records_outbound_message(
    prepare_database: None,
) -> None:
    lead_id = await create_lead_with_email_subscription()
    client = FakeEmailClient()

    async with async_session_maker() as session:
        result = await send_email_text_message(
            session=session,
            client=client,
            lead_id=lead_id,
            subject="Первое письмо",
            text="Здравствуйте",
            public_base_url="https://bot.aisukam.ru",
            from_email="hello@example.com",
            from_name="Aisu",
        )
        await session.commit()

    assert result.external_message_id == "email-123"
    assert client.to_email == TEST_EMAIL
    assert client.subject == "Первое письмо"
    assert client.text is not None
    assert "https://bot.aisukam.ru/email/unsubscribe/" in client.text

    async with async_session_maker() as session:
        subscription = await session.scalar(
            select(EmailSubscription).where(EmailSubscription.lead_id == lead_id)
        )
        assert subscription is not None
        assert subscription.unsubscribe_token is not None

        message = await session.scalar(
            select(Message).where(
                Message.lead_id == lead_id,
                Message.channel == "email",
                Message.direction == "outbound",
            )
        )
        assert message is not None
        assert message.id == result.message_id
        assert message.status == "sent"
        assert message.external_message_id == "email-123"
        assert message.metadata_["subject"] == "Первое письмо"
        assert message.metadata_["provider_response"]["provider"] == "fake"


async def test_send_email_text_message_rejects_unsubscribed_address(
    prepare_database: None,
) -> None:
    lead_id = await create_lead_with_email_subscription(status="unsubscribed")
    client = FakeEmailClient()

    async with async_session_maker() as session:
        with pytest.raises(ValueError, match="subscribed email subscription"):
            await send_email_text_message(
                session=session,
                client=client,
                lead_id=lead_id,
                subject="No send",
                text="No send",
                public_base_url="https://bot.aisukam.ru",
            )

    assert client.to_email is None


async def test_send_email_text_message_marks_provider_failure(
    prepare_database: None,
) -> None:
    lead_id = await create_lead_with_email_subscription()

    async with async_session_maker() as session:
        with pytest.raises(RuntimeError, match="provider is down"):
            await send_email_text_message(
                session=session,
                client=FailingEmailClient(),
                lead_id=lead_id,
                subject="Retry later",
                text="Retry later",
                public_base_url="https://bot.aisukam.ru",
            )
        await session.commit()

    async with async_session_maker() as session:
        message = await session.scalar(
            select(Message).where(
                Message.lead_id == lead_id,
                Message.channel == "email",
                Message.direction == "outbound",
            )
        )
        assert message is not None
        assert message.status == "failed"
        assert message.metadata_["error"] == "provider is down"


async def test_unsubscribe_endpoint_is_idempotent(
    prepare_database: None,
) -> None:
    token = "email-unsubscribe-token-123"
    lead_id = await create_lead_with_email_subscription(unsubscribe_token=token)

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://127.0.0.1:8000",
    ) as client:
        first_response = await client.get(f"/email/unsubscribe/{token}")
        second_response = await client.get(f"/email/unsubscribe/{token}")

    assert first_response.status_code == 200
    assert "Вы отписаны" in first_response.text
    assert second_response.status_code == 200

    async with async_session_maker() as session:
        subscription = await session.scalar(
            select(EmailSubscription).where(EmailSubscription.lead_id == lead_id)
        )
        assert subscription is not None
        assert subscription.status == "unsubscribed"
        assert subscription.unsubscribed_at is not None

        event_count = await session.scalar(
            select(func.count(Event.id)).where(
                Event.lead_id == lead_id,
                Event.event_type == "email.unsubscribed",
            )
        )
        assert event_count == 1
