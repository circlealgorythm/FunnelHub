from __future__ import annotations

import json
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import httpx
import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from funnelhub.config import Settings
from funnelhub.db.base import Base
from funnelhub.db.models import EmailSubscription, Event, Lead, Message
from funnelhub.db.session import async_session_maker, engine
from funnelhub.main import app
from funnelhub.services.email_messaging import (
    DebugEmailProviderClient,
    EmailProviderSendResult,
    UnisenderGoEmailProviderClient,
    build_email_provider_client,
    send_email_text_message,
)

TEST_GC_ID = 987654800
TEST_EMAIL = "email-test@example.com"


class FakeEmailClient:
    def __init__(self) -> None:
        self.to_email: str | None = None
        self.subject: str | None = None
        self.text: str | None = None
        self.html: str | None = None
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
        self.html = html
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
def anyio_backend() -> str:
    return "asyncio"


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
            signature_image_url="https://bot.aisukam.ru/assets/email/aisu-kam.jpg",
            metadata={
                "buttons": [
                    {"text": "Перейти к курсу", "url": "https://aisukam.ru/courses"}
                ]
            },
        )
        await session.commit()

    assert result.external_message_id == "email-123"
    assert client.to_email == TEST_EMAIL
    assert client.subject == "Первое письмо"
    assert client.text is not None
    assert "Перейти к курсу: https://aisukam.ru/courses" in client.text
    assert "https://bot.aisukam.ru/email/unsubscribe/" in client.text
    assert client.html is not None
    assert 'href="https://aisukam.ru/courses"' in client.html
    assert "Перейти к курсу" in client.html
    assert 'src="https://bot.aisukam.ru/assets/email/aisu-kam.jpg"' in client.html
    assert "С любовью, Айсу Кам." in client.html
    assert "Сатья-Юга" in client.html

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


async def test_unisender_go_client_posts_expected_payload() -> None:
    captured_requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(200, json={"job_id": "unisender-job-123"})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = UnisenderGoEmailProviderClient(
        api_key="test-api-key",
        api_url="https://goapi.unisender.ru/ru/transactional/api/v1/email/send.json",
        default_from_email="info@aisukam.ru",
        default_from_name="Айсу Кам",
        default_reply_to_email="info@aisukam.ru",
        http_client=http_client,
    )

    try:
        result = await client.send_email(
            to_email="lead@example.com",
            subject="Тестовое письмо",
            text="Здравствуйте",
            html="<p>Здравствуйте</p>",
            metadata={
                "lead_id": "lead-123",
                "message_id": "message-123",
                "unsubscribe_url": "https://bot.aisukam.ru/email/unsubscribe/token",
                "buttons": [{"text": "ignored"}],
            },
        )
    finally:
        await http_client.aclose()

    assert result.external_message_id == "unisender-job-123"
    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.headers["X-API-KEY"] == "test-api-key"

    payload = json.loads(request.content)
    message = payload["message"]
    assert message["recipients"] == [{"email": "lead@example.com"}]
    assert message["subject"] == "Тестовое письмо"
    assert message["from_email"] == "info@aisukam.ru"
    assert message["from_name"] == "Айсу Кам"
    assert message["reply_to"] == "info@aisukam.ru"
    assert message["body"]["plaintext"] == "Здравствуйте"
    assert message["body"]["html"] == "<p>Здравствуйте</p>"
    assert message["idempotence_key"] == "message-123"
    assert message["options"]["unsubscribe_url"] == (
        "https://bot.aisukam.ru/email/unsubscribe/token"
    )
    assert message["global_metadata"] == {
        "lead_id": "lead-123",
        "message_id": "message-123",
        "unsubscribe_url": "https://bot.aisukam.ru/email/unsubscribe/token",
    }


async def test_unisender_go_client_raises_on_provider_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"error": "bad request"})

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    client = UnisenderGoEmailProviderClient(
        api_key="test-api-key",
        api_url="https://goapi.unisender.ru/ru/transactional/api/v1/email/send.json",
        default_from_email="info@aisukam.ru",
        http_client=http_client,
    )

    try:
        with pytest.raises(RuntimeError, match="Unisender Go email send failed"):
            await client.send_email(
                to_email="lead@example.com",
                subject="Ошибка",
                text="Ошибка",
            )
    finally:
        await http_client.aclose()


def test_build_email_provider_client_supports_unisender_go() -> None:
    client = build_email_provider_client(
        Settings(
            EMAIL_PROVIDER="unisender_go",
            EMAIL_UNISENDER_GO_API_KEY="test-api-key",
            EMAIL_FROM_EMAIL="info@aisukam.ru",
            EMAIL_FROM_NAME="Айсу Кам",
            EMAIL_REPLY_TO_EMAIL="info@aisukam.ru",
        )
    )

    assert isinstance(client, UnisenderGoEmailProviderClient)


def test_build_email_provider_client_debug() -> None:
    client = build_email_provider_client(Settings(EMAIL_PROVIDER="debug"))

    assert isinstance(client, DebugEmailProviderClient)
