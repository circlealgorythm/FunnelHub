from __future__ import annotations

from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from funnelhub.config import get_settings
from funnelhub.db.base import Base
from funnelhub.db.models import Lead, LeadContact, LeadTag
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
    test_emails = ("most-test@example.com", "most-api@example.com")
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

    assert [item.id for item in most_conversations] == [result.conversation_id]
    assert main_conversations == []
    assert most_conversations[0].status == "needs_reply"
    assert most_conversations[0].last_message_body == "Новая заявка с сайта «Мост ценностей»."
    assert result.lead_id in [item.id for item in most_database_leads.items]
    assert result.lead_id not in [item.id for item in main_database_leads.items]
    async with async_session_maker() as session:
        tags = list(
            await session.scalars(select(LeadTag.tag).where(LeadTag.lead_id == result.lead_id))
        )
    assert tags == ["заявка с сайта"]


async def test_landing_application_endpoint_requires_token_and_records_application(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("MOST_TSENNOSTEY_INGEST_TOKEN", "test-most-token")
    monkeypatch.setenv("MOST_TELEGRAM_BOT_USERNAME", "most_test_bot")
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
