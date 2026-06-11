from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from funnelhub.config import get_settings
from funnelhub.db.base import Base
from funnelhub.db.models import EmailSubscription, Event, Lead, Message
from funnelhub.db.session import async_session_maker, engine
from funnelhub.main import app

TEST_GC_ID = 987657000
TEST_EMAIL = "provider-webhook@example.com"
TEST_API_KEY = "test-unisender-api-key"
TEST_JOB_ID = "unisender-job-provider-webhook"


@pytest.fixture(autouse=True)
async def prepare_database(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[None]:
    monkeypatch.setenv("EMAIL_UNISENDER_GO_API_KEY", TEST_API_KEY)
    get_settings.cache_clear()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    await cleanup_test_data()
    yield
    get_settings.cache_clear()
    await cleanup_test_data()
    await engine.dispose()


async def cleanup_test_data() -> None:
    async with async_session_maker() as session:
        lead_ids = set(
            await session.scalars(
                select(Lead.id).where(
                    Lead.getcourse_user_id >= TEST_GC_ID,
                    Lead.getcourse_user_id < TEST_GC_ID + 20,
                )
            )
        )
        subscription_leads = set(
            await session.scalars(
                select(EmailSubscription.lead_id).where(
                    EmailSubscription.normalized_email.like("provider-webhook%@example.com")
                )
            )
        )
        lead_ids.update(subscription_leads)
        if lead_ids:
            await session.execute(delete(Event).where(Event.lead_id.in_(lead_ids)))
            await session.execute(delete(Message).where(Message.lead_id.in_(lead_ids)))
            await session.execute(delete(Lead).where(Lead.id.in_(lead_ids)))
        await session.execute(
            delete(Event).where(
                Event.source == "unisender_go",
                Event.payload["email"].as_string().like("provider-webhook%@example.com"),
            )
        )
        await session.execute(
            delete(Message).where(Message.external_message_id.like(f"{TEST_JOB_ID}%"))
        )
        await session.commit()


async def create_email_message(
    *,
    email: str = TEST_EMAIL,
    getcourse_user_id: int = TEST_GC_ID,
    job_id: str = TEST_JOB_ID,
) -> tuple[uuid.UUID, uuid.UUID]:
    async with async_session_maker() as session:
        lead = Lead(id=uuid.uuid4(), getcourse_user_id=getcourse_user_id, raw_getcourse_data={})
        session.add(lead)
        await session.flush()
        session.add(
            EmailSubscription(
                id=uuid.uuid4(),
                lead_id=lead.id,
                email=email,
                normalized_email=email,
                status="subscribed",
                subscribed_at=datetime.now(UTC),
                provider="unisender_go",
            )
        )
        message = Message(
            id=uuid.uuid4(),
            lead_id=lead.id,
            channel="email",
            direction="outbound",
            message_type="text",
            body="Тестовое письмо",
            external_message_id=job_id,
            status="sent",
            sent_at=datetime.now(UTC),
            metadata_={"subject": "Тест"},
        )
        session.add(message)
        await session.commit()
        return lead.id, message.id


def signed_unisender_body(payload: dict[str, Any]) -> bytes:
    payload_for_hash = {**payload, "auth": TEST_API_KEY}
    auth = hashlib.md5(
        json.dumps(
            payload_for_hash,
            ensure_ascii=False,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    return json.dumps(
        {**payload, "auth": auth},
        ensure_ascii=False,
        separators=(",", ":"),
    ).encode()


def webhook_payload(
    *,
    lead_id: uuid.UUID,
    message_id: uuid.UUID,
    email: str = TEST_EMAIL,
    job_id: str = TEST_JOB_ID,
    events: list[dict[str, Any]],
) -> dict[str, Any]:
    provider_events: list[dict[str, Any]] = []
    for event in events:
        event_data = dict(event["event_data"])
        event_data.setdefault("job_id", job_id)
        event_data.setdefault("email", email)
        event_data.setdefault(
            "metadata",
            {
                "lead_id": str(lead_id),
                "message_id": str(message_id),
                "funnel_key": "aisu_email_sequence",
                "step_key": "day_01_intro",
            },
        )
        if "event_time" in event:
            event_data.setdefault("event_time", event["event_time"])
        provider_events.append(
            {
                "event_name": event.get("event_name", "transactional_email_status"),
                "event_data": event_data,
            }
        )

    return {
        "events_by_user": [
            {
                "events": provider_events,
            }
        ],
    }


async def post_unisender_webhook(payload: dict[str, Any]) -> Any:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        return await client.post(
            "/webhooks/email/unisender-go",
            content=signed_unisender_body(payload),
            headers={"content-type": "application/json"},
        )


async def test_unisender_webhook_records_delivery_open_and_click() -> None:
    lead_id, message_id = await create_email_message()
    response = await post_unisender_webhook(
        webhook_payload(
            lead_id=lead_id,
            message_id=message_id,
            events=[
                {
                    "event_name": "transactional_email_status",
                    "event_time": "2026-06-05 12:00:00",
                    "event_data": {"status": "delivered"},
                },
                {
                    "event_name": "transactional_email_status",
                    "event_time": "2026-06-05 12:01:00",
                    "event_data": {"status": "opened"},
                },
                {
                    "event_name": "transactional_email_status",
                    "event_time": "2026-06-05 12:02:00",
                    "event_data": {
                        "status": "clicked",
                        "url": "https://aisukam.ru/courses",
                    },
                },
            ],
        )
    )

    assert response.status_code == 200
    assert response.json() == {
        "status": "ok",
        "processed": 3,
        "matched_messages": 3,
        "updated_subscriptions": 0,
        "skipped": 0,
    }

    async with async_session_maker() as session:
        message = await session.get(Message, message_id)
        assert message is not None
        assert message.status == "read"
        assert message.delivered_at is not None
        assert message.read_at is not None
        assert message.metadata_["open_count"] == 1
        assert message.metadata_["click_count"] == 1
        assert message.metadata_["last_clicked_url"] == "https://aisukam.ru/courses"

        event_types = set(
            await session.scalars(
                select(Event.event_type).where(
                    Event.lead_id == lead_id,
                    Event.source == "unisender_go",
                )
            )
        )
        assert event_types == {"email.delivered", "email.opened", "email.clicked"}


async def test_unisender_webhook_is_idempotent_for_duplicate_events() -> None:
    lead_id, message_id = await create_email_message(job_id=f"{TEST_JOB_ID}-duplicate")
    payload = webhook_payload(
        lead_id=lead_id,
        message_id=message_id,
        job_id=f"{TEST_JOB_ID}-duplicate",
        events=[
            {
                "event_name": "transactional_email_status",
                "event_time": "2026-06-05 12:01:00",
                "event_data": {"status": "opened"},
            }
        ],
    )

    first_response = await post_unisender_webhook(payload)
    second_response = await post_unisender_webhook(payload)

    assert first_response.status_code == 200
    assert first_response.json()["processed"] == 1
    assert second_response.status_code == 200
    assert second_response.json()["processed"] == 0
    assert second_response.json()["skipped"] == 1

    async with async_session_maker() as session:
        message = await session.get(Message, message_id)
        assert message is not None
        assert message.metadata_["open_count"] == 1
        event_count = await session.scalar(
            select(func.count(Event.id)).where(
                Event.lead_id == lead_id,
                Event.event_type == "email.opened",
            )
        )
        assert event_count == 1


async def test_unisender_webhook_records_bounce_complaint_and_provider_unsubscribe() -> None:
    lead_id, message_id = await create_email_message(job_id=f"{TEST_JOB_ID}-bounce")
    response = await post_unisender_webhook(
        webhook_payload(
            lead_id=lead_id,
            message_id=message_id,
            job_id=f"{TEST_JOB_ID}-bounce",
            events=[
                {
                    "event_name": "transactional_email_status",
                    "event_time": "2026-06-05 12:00:00",
                    "event_data": {
                        "status": "hard_bounced",
                        "delivery_info": {"destination_response": "550 mailbox unavailable"},
                    },
                },
                {
                    "event_name": "transactional_email_status",
                    "event_time": "2026-06-05 12:01:00",
                    "event_data": {"status": "spam"},
                },
                {
                    "event_name": "transactional_email_status",
                    "event_time": "2026-06-05 12:02:00",
                    "event_data": {"status": "unsubscribed"},
                },
            ],
        )
    )

    assert response.status_code == 200
    assert response.json()["processed"] == 3
    assert response.json()["updated_subscriptions"] == 3

    async with async_session_maker() as session:
        subscription = await session.scalar(
            select(EmailSubscription).where(EmailSubscription.lead_id == lead_id)
        )
        assert subscription is not None
        assert subscription.status == "unsubscribed"
        assert subscription.unsubscribed_at is not None

        message = await session.get(Message, message_id)
        assert message is not None
        assert message.status == "failed"

        event_types = set(
            await session.scalars(
                select(Event.event_type).where(
                    Event.lead_id == lead_id,
                    Event.source == "unisender_go",
                )
            )
        )
        assert event_types == {
            "email.hard_bounced",
            "email.complained",
            "email.unsubscribed",
        }


async def test_unisender_webhook_accepts_status_aliases_and_event_names() -> None:
    lead_id, message_id = await create_email_message(job_id=f"{TEST_JOB_ID}-aliases")
    payload = {
        "events_by_user": [
            {
                "Events": [
                    {
                        "EventName": "transactional_email_status",
                        "event_data": {
                            "email_status": "ok_read",
                            "job_id": f"{TEST_JOB_ID}-aliases",
                            "email": TEST_EMAIL,
                            "event_time": "2026-06-05T12:01:00+00:00",
                            "metadata": {
                                "lead_id": str(lead_id),
                                "message_id": str(message_id),
                            },
                        },
                    },
                    {
                        "event_name": "ok_link_visited",
                        "event_data": {
                            "job_id": f"{TEST_JOB_ID}-aliases",
                            "email": TEST_EMAIL,
                            "event_time": "2026-06-05T12:02:00+00:00",
                            "url": "https://aisukam.ru/alias-click",
                            "metadata": {
                                "lead_id": str(lead_id),
                                "message_id": str(message_id),
                            },
                        },
                    },
                    {
                        "event_name": "unsubscribe",
                        "event_data": {
                            "job_id": f"{TEST_JOB_ID}-aliases",
                            "email": TEST_EMAIL,
                            "event_time": "2026-06-05T12:03:00+00:00",
                            "metadata": {
                                "lead_id": str(lead_id),
                                "message_id": str(message_id),
                            },
                        },
                    },
                ],
            }
        ],
    }

    response = await post_unisender_webhook(payload)

    assert response.status_code == 200
    assert response.json()["processed"] == 3
    assert response.json()["matched_messages"] == 3
    assert response.json()["updated_subscriptions"] == 1

    async with async_session_maker() as session:
        message = await session.get(Message, message_id)
        assert message is not None
        assert message.status == "failed"
        assert message.read_at is not None
        assert message.metadata_["open_count"] == 1
        assert message.metadata_["click_count"] == 1
        assert message.metadata_["last_clicked_url"] == "https://aisukam.ru/alias-click"

        subscription = await session.scalar(
            select(EmailSubscription).where(EmailSubscription.lead_id == lead_id)
        )
        assert subscription is not None
        assert subscription.status == "unsubscribed"

        event_types = set(
            await session.scalars(
                select(Event.event_type).where(
                    Event.lead_id == lead_id,
                    Event.source == "unisender_go",
                )
            )
        )
        assert event_types == {"email.opened", "email.clicked", "email.unsubscribed"}


async def test_unisender_webhook_rejects_invalid_auth() -> None:
    lead_id, message_id = await create_email_message(job_id=f"{TEST_JOB_ID}-auth")
    payload = webhook_payload(
        lead_id=lead_id,
        message_id=message_id,
        job_id=f"{TEST_JOB_ID}-auth",
        events=[
            {
                "event_name": "transactional_email_status",
                "event_time": "2026-06-05 12:00:00",
                "event_data": {"status": "delivered"},
            }
        ],
    )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/webhooks/email/unisender-go",
            json={**payload, "auth": "bad-auth"},
        )

    assert response.status_code == 403
    async with async_session_maker() as session:
        message = await session.get(Message, message_id)
        assert message is not None
        assert message.status == "sent"
        event_count = await session.scalar(
            select(func.count(Event.id)).where(Event.lead_id == lead_id)
        )
        assert event_count == 0
