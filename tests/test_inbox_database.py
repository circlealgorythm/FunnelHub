from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from io import BytesIO

import pytest
from httpx import ASGITransport, AsyncClient
from openpyxl import load_workbook
from sqlalchemy import delete, select

from funnelhub.config import get_settings
from funnelhub.db.base import Base
from funnelhub.db.models import ImportBatch, Lead, LeadContact, Message, MessengerIdentity
from funnelhub.db.session import async_session_maker, engine
from funnelhub.main import app
from funnelhub.services.auth import hash_password
from funnelhub.services.inbox_database import (
    export_database_leads_csv,
    export_database_leads_xlsx,
    get_database_lead_detail,
    import_database_leads_csv,
    list_database_leads,
)

TEST_GC_ID = 987656000
TEST_EMAIL = "database@example.com"
IMPORT_EMAIL = "imported-database@example.com"
API_IMPORT_EMAIL = "api-db@example.com"


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
                select(LeadContact.lead_id).where(
                    LeadContact.normalized_value.in_(
                        {TEST_EMAIL, IMPORT_EMAIL, API_IMPORT_EMAIL}
                    )
                )
            )
        )
        lead_ids.update(contact_lead_ids)
        if lead_ids:
            await session.execute(delete(Lead).where(Lead.id.in_(lead_ids)))
        await session.execute(
            delete(ImportBatch).where(ImportBatch.file_name.in_({"leads.csv", "broken.csv"}))
        )
        await session.commit()


async def create_database_lead() -> uuid.UUID:
    async with async_session_maker() as session:
        lead = Lead(
            id=uuid.uuid4(),
            getcourse_user_id=TEST_GC_ID,
            full_name="Database Test Lead",
            city="Moscow",
            country="Russia",
            source="manual",
            raw_getcourse_data={"name": "Database Test Lead"},
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
                external_user_id="db-tg",
                username="database_tg",
                is_subscribed=True,
                raw_profile={},
            )
        )
        session.add(
            Message(
                id=uuid.uuid4(),
                lead_id=lead.id,
                channel="telegram",
                direction="inbound",
                message_type="text",
                body="Database message",
                status="received",
                metadata_={},
            )
        )
        await session.commit()
        return lead.id


async def test_list_database_leads_searches_contacts_and_counts_messages() -> None:
    await create_database_lead()

    async with async_session_maker() as session:
        lead_list = await list_database_leads(session, query="database@example.com")

    assert lead_list.total == 1
    assert lead_list.items[0].name == "Database Test Lead"
    assert lead_list.items[0].email == TEST_EMAIL
    assert lead_list.items[0].telegram == "database_tg"
    assert lead_list.items[0].messages_count == 1


async def test_export_database_leads_csv() -> None:
    await create_database_lead()

    async with async_session_maker() as session:
        csv_text = await export_database_leads_csv(session, query="Database Test Lead")

    assert "lead_id,getcourse_user_id,name" in csv_text
    assert "Database Test Lead" in csv_text
    assert TEST_EMAIL in csv_text


async def test_export_database_leads_xlsx_uses_human_readable_columns() -> None:
    await create_database_lead()

    async with async_session_maker() as session:
        content = await export_database_leads_xlsx(session, query="Database Test Lead")

    workbook = load_workbook(BytesIO(content), read_only=True)
    sheet = workbook.active
    headers = [cell.value for cell in sheet[1]]
    values = [cell.value for cell in sheet[2]]

    assert "ID GetCourse" in headers
    assert "Имя" in headers
    assert "Согласия" in headers
    assert TEST_GC_ID in values
    assert "Database Test Lead" in values


async def test_imported_getcourse_fields_are_available_in_database_detail() -> None:
    content = (
        "id,Email,VK-ID,gc_system_user_utm_source,Откуда пришел,"
        "id групп пользователя/дата добавления\n"
        f"{TEST_GC_ID + 3},{IMPORT_EMAIL},88996633,gc-source,mamba.ru,3971958:2025-12-19\n"
    ).encode()

    async with async_session_maker() as session:
        result = await import_database_leads_csv(
            session,
            file_name="leads.csv",
            content=content,
        )
        await session.commit()

    assert result.processed_rows == 1

    async with async_session_maker() as session:
        lead = await session.scalar(select(Lead).where(Lead.getcourse_user_id == TEST_GC_ID + 3))
        assert lead is not None
        detail = await get_database_lead_detail(session, lead.id)

    assert detail is not None
    assert any(item["provider"] == "getcourse_vk_id" for item in detail.external_ids)
    assert any(
        item["key"] == "vk_id" and item["value"] == "88996633"
        for item in detail.custom_fields
    )
    assert any(
        item["source_kind"] == "getcourse_system" and item["utm_source"] == "gc-source"
        for item in detail.utm_snapshots
    )


async def test_import_database_leads_csv_creates_and_updates_leads() -> None:
    content = (
        "gc_user_id,name,email,phone,city\n"
        f"{TEST_GC_ID + 1},Imported Lead,{IMPORT_EMAIL},+7 900 000 00 00,Paris\n"
        f"{TEST_GC_ID + 1},Imported Lead Updated,{IMPORT_EMAIL},+7 900 000 00 00,Berlin\n"
        ",No Identity,,,\n"
    ).encode()

    async with async_session_maker() as session:
        result = await import_database_leads_csv(
            session,
            file_name="leads.csv",
            content=content,
        )
        await session.commit()

    assert result.total_rows == 3
    assert result.processed_rows == 2
    assert result.failed_rows == 1
    assert result.created_rows == 1
    assert result.updated_rows == 1

    async with async_session_maker() as session:
        lead = await session.scalar(select(Lead).where(Lead.getcourse_user_id == TEST_GC_ID + 1))
        assert lead is not None
        assert lead.full_name == "Imported Lead Updated"
        assert lead.city == "Berlin"


async def test_database_api_requires_auth_and_supports_list_export_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_auth(monkeypatch)
    await create_database_lead()

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
        ) as client:
            anonymous_response = await client.get("/api/inbox/database/leads")
            login_response = await client.post(
                "/api/auth/login",
                json={"username": "aisu", "password": "secret"},
            )
            list_response = await client.get("/api/inbox/database/leads?q=Database")
            export_response = await client.get("/api/inbox/database/leads/export")
            import_response = await client.post(
                "/api/inbox/database/leads/import",
                files={
                    "file": (
                        "leads.csv",
                        f"gc_user_id,name,email\n{TEST_GC_ID + 2},API Lead,{API_IMPORT_EMAIL}\n",
                        "text/csv",
                    )
                },
            )
    finally:
        get_settings.cache_clear()

    assert anonymous_response.status_code == 401
    assert login_response.status_code == 200
    assert list_response.status_code == 200
    assert list_response.json()["items"][0]["name"] == "Database Test Lead"
    assert export_response.status_code == 200
    assert "Database Test Lead" in export_response.text
    assert import_response.status_code == 200
    assert import_response.json()["processed_rows"] == 1


def configure_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("INBOX_ADMIN_USERNAME", "aisu")
    monkeypatch.setenv(
        "INBOX_ADMIN_PASSWORD_HASH",
        hash_password("secret", salt=b"1234567890123456"),
    )
    monkeypatch.setenv("INBOX_SESSION_SECRET", "test-session-secret")
    get_settings.cache_clear()
