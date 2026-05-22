from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from funnelhub.db.base import Base
from funnelhub.db.models import Lead, LeadContact, LeadCustomField, LeadExternalId
from funnelhub.db.session import async_session_maker, engine
from funnelhub.main import app

TEST_EMAIL = "webhook-test@example.com"
TEST_PHONE = "79990000000"
TEST_GC_ID = "987654321"
TEST_GC_ID_UPDATED = "987654322"


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
        lead_ids: set[uuid.UUID] = set()
        contact_result = await session.scalars(
            select(LeadContact.lead_id).where(
                LeadContact.normalized_value.in_({TEST_EMAIL, TEST_PHONE})
            )
        )
        lead_ids.update(contact_result.all())

        external_result = await session.scalars(
            select(LeadExternalId.lead_id).where(
                LeadExternalId.provider == "getcourse",
                LeadExternalId.external_id.in_({TEST_GC_ID, TEST_GC_ID_UPDATED}),
            )
        )
        lead_ids.update(external_result.all())

        if lead_ids:
            await session.execute(delete(Lead).where(Lead.id.in_(lead_ids)))
        await session.commit()


async def test_getcourse_webhook_creates_lead_from_query_params() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/webhooks/getcourse",
            params={
                "gc_user_id": TEST_GC_ID,
                "email": TEST_EMAIL,
                "phone": "+7 999 000-00-00",
                "name": "Сергей тест Gurban",
                "first_name": "Сергей тест",
                "last_name": "Gurban",
                "country": "Россия",
                "utm_source": "localhost",
                "utm_medium": "referral",
                "custom_10558670": "Да",
            },
        )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["created"] is True


async def test_getcourse_webhook_persists_lead_contacts_and_custom_fields() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/webhooks/getcourse",
            params={
                "gc_user_id": TEST_GC_ID,
                "email": TEST_EMAIL.upper(),
                "phone": "+7 999 000-00-00",
                "first_name": "Сергей",
                "custom_10558670": "Да",
            },
        )
    lead_id = uuid.UUID(response.json()["lead_id"])

    async with async_session_maker() as session:
        lead = await session.get(Lead, lead_id)
        assert lead is not None
        assert lead.getcourse_user_id == int(TEST_GC_ID)
        assert lead.first_name == "Сергей"
        assert lead.raw_getcourse_data["custom_10558670"] == "Да"

        email_contact = await session.scalar(
            select(LeadContact).where(
                LeadContact.contact_type == "email",
                LeadContact.normalized_value == TEST_EMAIL,
            )
        )
        assert email_contact is not None
        assert email_contact.lead_id == lead_id

        phone_contact = await session.scalar(
            select(LeadContact).where(
                LeadContact.contact_type == "phone",
                LeadContact.normalized_value == TEST_PHONE,
            )
        )
        assert phone_contact is not None
        assert phone_contact.lead_id == lead_id

        custom_field = await session.scalar(
            select(LeadCustomField).where(
                LeadCustomField.lead_id == lead_id,
                LeadCustomField.field_key == "custom_10558670",
            )
        )
        assert custom_field is not None
        assert custom_field.value == "Да"
        assert custom_field.normalized_bool is True


async def test_getcourse_webhook_updates_existing_lead_by_getcourse_id() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first_response = await client.get(
            "/webhooks/getcourse",
            params={"gc_user_id": TEST_GC_ID, "email": TEST_EMAIL, "first_name": "Сергей"},
        )
        second_response = await client.get(
            "/webhooks/getcourse",
            params={"gc_user_id": TEST_GC_ID, "email": TEST_EMAIL, "first_name": "Иван"},
        )

    assert first_response.json()["created"] is True
    assert second_response.json()["created"] is False
    assert second_response.json()["lead_id"] == first_response.json()["lead_id"]

    async with async_session_maker() as session:
        lead_count = await session.scalar(
            select(func.count()).select_from(Lead).where(Lead.getcourse_user_id == int(TEST_GC_ID))
        )
        assert lead_count == 1


async def test_getcourse_webhook_deduplicates_by_email_without_getcourse_id() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first_response = await client.get(
            "/webhooks/getcourse",
            params={"email": TEST_EMAIL, "first_name": "Сергей"},
        )
        second_response = await client.get(
            "/webhooks/getcourse",
            params={"gc_user_id": TEST_GC_ID_UPDATED, "email": TEST_EMAIL, "first_name": "Иван"},
        )

    assert first_response.json()["created"] is True
    assert second_response.json()["created"] is False
    assert second_response.json()["lead_id"] == first_response.json()["lead_id"]


async def test_getcourse_webhook_rejects_payload_without_identity() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/webhooks/getcourse", params={"utm_source": "localhost"})

    assert response.status_code == 422
    assert response.json()["detail"] == "Webhook must include gc_user_id, email, or phone."
