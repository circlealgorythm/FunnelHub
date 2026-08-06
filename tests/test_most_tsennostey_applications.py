from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from funnelhub.config import get_settings
from funnelhub.db.base import Base
from funnelhub.db.models import (
    Conversation,
    Lead,
    LeadContact,
    LeadPostSubmitTask,
    LeadTag,
    MessengerIdentity,
)
from funnelhub.db.session import async_session_maker, engine
from funnelhub.main import app
from funnelhub.services.inbox import list_inbox_conversations
from funnelhub.services.inbox_database import list_database_leads
from funnelhub.services.landing_applications import (
    MOST_TSENNOSTEY_SOURCE,
    ingest_most_tsennostey_application,
)


@pytest.fixture(autouse=True)
async def prepare_database() -> AsyncGenerator[None]:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    await cleanup_most_tsennostey_leads()
    yield
    await cleanup_most_tsennostey_leads()
    await engine.dispose()


async def cleanup_most_tsennostey_leads() -> None:
    test_emails = ("most-test@example.com", "most-api@example.com", "most-shared@example.com")
    async with async_session_maker() as session:
        lead_ids = select(LeadContact.lead_id).where(
            LeadContact.contact_type == "email",
            LeadContact.normalized_value.in_(test_emails),
        )
        await session.execute(delete(Lead).where(Lead.id.in_(lead_ids)))
        await session.commit()


async def test_landing_application_creates_isolated_inbox_conversation() -> None:
    async with async_session_maker() as session:
        result = await ingest_most_tsennostey_application(
            session,
            name="Мост Тест",
            phone="+7 999 000-00-01",
            email="most-test@example.com",
        )
        await session.commit()

    async with async_session_maker() as session:
        lead = await session.get(Lead, result.lead_id)
        assert lead is not None
        assert lead.source == MOST_TSENNOSTEY_SOURCE
        session.add(
            MessengerIdentity(
                id=uuid.uuid4(),
                lead_id=lead.id,
                channel="telegram_most",
                external_user_id="most-test-user",
                username="most_test_user",
                is_subscribed=True,
            )
        )
        await session.commit()

        most_conversations = await list_inbox_conversations(
            session,
            source=MOST_TSENNOSTEY_SOURCE,
        )
        main_conversations = await list_inbox_conversations(
            session,
            exclude_source=MOST_TSENNOSTEY_SOURCE,
        )
        most_database_leads = await list_database_leads(
            session,
            source=MOST_TSENNOSTEY_SOURCE,
        )
        main_database_leads = await list_database_leads(
            session,
            exclude_source=MOST_TSENNOSTEY_SOURCE,
        )

    most_conversation = next(
        item for item in most_conversations if item.id == result.conversation_id
    )
    assert result.conversation_id not in [item.id for item in main_conversations]
    assert most_conversation.status == "needs_reply"
    assert most_conversation.last_message_body == "Новая заявка с сайта «Мост ценностей»."
    assert result.lead_id in [item.id for item in most_database_leads.items]
    assert result.lead_id not in [item.id for item in main_database_leads.items]
    assert most_database_leads.items[0].telegram == "most_test_user"
    async with async_session_maker() as session:
        tags = list(
            await session.scalars(select(LeadTag.tag).where(LeadTag.lead_id == result.lead_id))
        )
    assert tags == ["заявка с сайта"]


async def test_existing_main_lead_is_available_in_both_database_segments() -> None:
    shared_email = "most-shared@example.com"
    shared_phone = "+79990000003"
    existing_lead_id = uuid.uuid4()
    async with async_session_maker() as session:
        session.add(
            Lead(
                id=existing_lead_id,
                full_name="Основной лид",
                source="main-site",
                raw_getcourse_data={},
            )
        )
        session.add_all(
            [
                LeadContact(
                    id=uuid.uuid4(),
                    lead_id=existing_lead_id,
                    contact_type="email",
                    value=shared_email,
                    normalized_value=shared_email,
                ),
                LeadContact(
                    id=uuid.uuid4(),
                    lead_id=existing_lead_id,
                    contact_type="phone",
                    value=shared_phone,
                    normalized_value=shared_phone,
                ),
            ]
        )
        await session.commit()

    async with async_session_maker() as session:
        result = await ingest_most_tsennostey_application(
            session,
            name="Общий лид",
            phone="+7 999 000-00-03",
            email=shared_email,
        )
        await session.commit()

    assert result.lead_id == existing_lead_id
    assert result.created is False
    async with async_session_maker() as session:
        lead = await session.get(Lead, existing_lead_id)
        assert lead is not None
        assert lead.source == "main-site"
        most_leads = await list_database_leads(session, source=MOST_TSENNOSTEY_SOURCE)
        main_leads = await list_database_leads(session, exclude_source=MOST_TSENNOSTEY_SOURCE)
        most_conversation = await session.scalar(
            select(Conversation).where(
                Conversation.lead_id == existing_lead_id,
                Conversation.source == MOST_TSENNOSTEY_SOURCE,
            )
        )

    assert existing_lead_id in [item.id for item in most_leads.items]
    assert existing_lead_id in [item.id for item in main_leads.items]
    assert most_conversation is not None


async def test_landing_application_endpoint_requires_token_and_records_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MOST_TSENNOSTEY_INGEST_TOKEN", "test-most-token")
    monkeypatch.setenv("MOST_TELEGRAM_BOT_USERNAME", "most_test_bot")
    monkeypatch.setenv("LEAD_NOTIFICATION_EMAIL_TO", "notifications@example.com")
    get_settings.cache_clear()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
        ) as client:
            forbidden_response = await client.post(
                "/webhooks/landing-applications/most-tsennostey",
                json={
                    "name": "Мост Тест",
                    "phone": "+7 999 000-00-02",
                    "email": "most-api@example.com",
                },
            )
            response = await client.post(
                "/webhooks/landing-applications/most-tsennostey",
                headers={"Authorization": "Bearer test-most-token"},
                json={
                    "name": "Мост Тест",
                    "phone": "+7 999 000-00-02",
                    "email": "most-api@example.com",
                },
            )
    finally:
        get_settings.cache_clear()

    assert forbidden_response.status_code == 401
    assert response.status_code == 201
    assert response.json()["created"] is True
    assert response.json()["telegram_url"].startswith("https://t.me/most_test_bot?start=")
    async with async_session_maker() as session:
        task_types = list(
            await session.scalars(
                select(LeadPostSubmitTask.task_type).where(
                    LeadPostSubmitTask.lead_id == uuid.UUID(response.json()["lead_id"])
                )
            )
        )
    assert {"lead_application_notification", "lead_tag_notification"}.issubset(task_types)
