from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from funnelhub.config import get_settings
from funnelhub.db.base import Base
from funnelhub.db.models import Broadcast, Lead, LeadContact, MessengerIdentity
from funnelhub.db.session import async_session_maker, engine
from funnelhub.main import app
from funnelhub.services.auth import hash_password

TEST_GC_ID = 987657000
TEST_EMAIL = "broadcast-target-test@example.com"


@pytest.fixture(autouse=True)
async def prepare_database() -> AsyncGenerator[None]:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    await cleanup_test_data()
    yield
    await cleanup_test_data()
    await engine.dispose()


async def cleanup_test_data() -> None:
    async with async_session_maker() as session:
        lead_ids = set(
            await session.scalars(
                select(Lead.id).where(
                    Lead.getcourse_user_id >= TEST_GC_ID,
                    Lead.getcourse_user_id < TEST_GC_ID + 100,
                )
            )
        )
        contact_lead_ids = set(
            await session.scalars(
                select(LeadContact.lead_id).where(LeadContact.normalized_value == TEST_EMAIL)
            )
        )
        lead_ids.update(contact_lead_ids)
        if lead_ids:
            await session.execute(delete(Lead).where(Lead.id.in_(lead_ids)))
        await session.execute(
            delete(Broadcast).where(Broadcast.segment_query == TEST_EMAIL)
        )
        await session.commit()


async def create_broadcast_lead() -> uuid.UUID:
    async with async_session_maker() as session:
        lead = Lead(
            id=uuid.uuid4(),
            getcourse_user_id=TEST_GC_ID,
            full_name="Broadcast Target Lead",
            raw_getcourse_data={},
        )
        session.add(lead)
        await session.flush()
        session.add(
            LeadContact(
                id=uuid.uuid4(),
                lead_id=lead.id,
                contact_type="email",
                value=TEST_EMAIL,
                normalized_value=TEST_EMAIL,
                is_primary=True,
            )
        )
        session.add(
            MessengerIdentity(
                id=uuid.uuid4(),
                lead_id=lead.id,
                channel="telegram",
                external_user_id="broadcast-tg-1",
                username="broadcast_tg",
                is_subscribed=True,
                raw_profile={},
            )
        )
        await session.commit()
        return lead.id


def configure_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INBOX_ADMIN_USERNAME", "aisu")
    monkeypatch.setenv(
        "INBOX_ADMIN_PASSWORD_HASH",
        hash_password("secret", salt=b"1234567890123456"),
    )
    monkeypatch.setenv("INBOX_SESSION_SECRET", "test-session-secret")
    get_settings.cache_clear()


async def test_broadcast_api_creates_and_lists_targets(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_auth(monkeypatch)
    lead_id = await create_broadcast_lead()

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
        ) as client:
            await client.post(
                "/api/auth/login",
                json={"username": "aisu", "password": "secret"},
            )
            create_response = await client.post(
                "/api/inbox/broadcasts",
                json={
                    "segment_query": TEST_EMAIL,
                    "channels": ["telegram", "telegram", "email"],
                    "message_text": "  Тестовая ручная рассылка  ",
                },
            )
            whitespace_response = await client.post(
                "/api/inbox/broadcasts",
                json={
                    "segment_query": TEST_EMAIL,
                    "channels": ["telegram"],
                    "message_text": "   ",
                },
            )
    finally:
        get_settings.cache_clear()

    assert create_response.status_code == 200
    created = create_response.json()
    assert created["channels"] == ["telegram", "email"]
    assert created["total_leads"] == 1
    assert created["status"] == "created"
    assert whitespace_response.status_code == 422

    broadcast_id = created["id"]
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
        ) as client:
            await client.post(
                "/api/auth/login",
                json={"username": "aisu", "password": "secret"},
            )
            targets_response = await client.get(
                f"/api/inbox/broadcasts/{broadcast_id}/targets"
            )
            missing_response = await client.get(
                f"/api/inbox/broadcasts/{uuid.uuid4()}/targets"
            )
    finally:
        get_settings.cache_clear()

    assert targets_response.status_code == 200
    targets = targets_response.json()
    assert targets["total"] == 1
    assert targets["items"] == [
        {
            "id": targets["items"][0]["id"],
            "lead_id": str(lead_id),
            "lead_name": "Broadcast Target Lead",
            "lead_contact": TEST_EMAIL,
            "status": "pending",
            "error": None,
        }
    ]
    assert missing_response.status_code == 404
