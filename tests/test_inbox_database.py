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
from funnelhub.db.models import (
    ImportBatch,
    Lead,
    LeadContact,
    LeadCustomField,
    LeadExternalId,
    Message,
    MessengerIdentity,
)
from funnelhub.db.session import async_session_maker, engine
from funnelhub.main import app
from funnelhub.services.auth import hash_password
from funnelhub.services.getcourse_webhook import ingest_getcourse_webhook
from funnelhub.services.inbox_database import (
    export_database_leads_csv,
    export_database_leads_xlsx,
    get_database_lead_detail,
    list_database_leads,
)


async def import_database_leads_csv(session, file_name: str, content: bytes):
    from funnelhub.services.inbox_database import execute_import_file, preview_import_file

    preview = preview_import_file(file_name, content)
    return await execute_import_file(
        session,
        file_name=file_name,
        content=content,
        mapping=preview.suggested_mapping,
    )

TEST_GC_ID = 987656000
TEST_EMAIL = "database@example.com"
IMPORT_EMAIL = "imported-database@example.com"
API_IMPORT_EMAIL = "api-db@example.com"
SHORT_IMPORT_EMAIL = "short-export@example.com"


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
                        {TEST_EMAIL, IMPORT_EMAIL, API_IMPORT_EMAIL, SHORT_IMPORT_EMAIL}
                    )
                )
            )
        )
        lead_ids.update(contact_lead_ids)
        if lead_ids:
            await session.execute(delete(Lead).where(Lead.id.in_(lead_ids)))
        await session.execute(
            delete(ImportBatch).where(
                ImportBatch.file_name.in_(
                    {
                        "leads.csv",
                        "broken.csv",
                        "getcourse-export.csv",
                        "short-getcourse-export.csv",
                    }
                )
            )
        )
        await session.commit()


async def create_database_lead(
    *,
    gc_id: int = TEST_GC_ID,
    email: str = TEST_EMAIL,
    name: str = "Database Test Lead",
) -> uuid.UUID:
    async with async_session_maker() as session:
        lead = Lead(
            id=uuid.uuid4(),
            getcourse_user_id=gc_id,
            full_name=name,
            city="Moscow",
            country="Russia",
            source="manual",
            raw_getcourse_data={"name": name},
        )
        session.add(lead)
        await session.flush()
        session.add(
            LeadContact(
                id=uuid.uuid4(),
                lead_id=lead.id,
                contact_type="email",
                value=email,
                normalized_value=email,
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
            MessengerIdentity(
                id=uuid.uuid4(),
                lead_id=lead.id,
                channel="vk",
                external_user_id="199271782",
                username=None,
                display_name=None,
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
    assert lead_list.items[0].vk == "199271782"
    assert lead_list.items[0].messages_count == 1


async def test_list_database_leads_supports_limit_and_offset() -> None:
    created_ids = [
        await create_database_lead(
            gc_id=TEST_GC_ID + index,
            email=f"database-page-{index}@example.com",
            name=f"Database Page Lead {index}",
        )
        for index in range(3)
    ]

    async with async_session_maker() as session:
        first_page = await list_database_leads(
            session,
            query="Database Page Lead",
            limit=2,
            offset=0,
        )
        second_page = await list_database_leads(
            session,
            query="Database Page Lead",
            limit=2,
            offset=2,
        )

    created_id_set = set(created_ids)
    first_page_ids = {lead.id for lead in first_page.items}
    second_page_ids = {lead.id for lead in second_page.items}
    assert first_page.total == 3
    assert first_page.limit == 2
    assert first_page.offset == 0
    assert len(first_page.items) == 2
    assert second_page.limit == 2
    assert second_page.offset == 2
    assert first_page_ids.isdisjoint(second_page_ids)
    assert first_page_ids | second_page_ids <= created_id_set


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
        "id,Email,VK-ID,gc_system_user_utm_source,utm_source,utm_medium,utm_campaign,"
        "Откуда пришел,id групп пользователя/дата добавления\n"
        f"{TEST_GC_ID + 3},{IMPORT_EMAIL},88996633,gc-source,yandex,cpc,direct-campaign,"
        "mamba.ru,3971958:2025-12-19\n"
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
        item["source_kind"] == "form" and item["utm_source"] == "yandex"
        for item in detail.utm_snapshots
    )
    assert not any(
        item["source_kind"] == "getcourse_system"
        for item in detail.utm_snapshots
    )


async def test_getcourse_tab_export_import_preserves_headerless_consent_columns() -> None:
    headers = [
        "id",
        "Email",
        "Тип регистрации",
        "Создан",
        "Последняя активность",
        "Имя",
        "Фамилия",
        "Телефон",
        "Дата рождения",
        "Возраст",
        "Страна",
        "Город",
        "От партнера",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "gc_system_user_utm_source",
        "gc_system_user_utm_medium",
        "gc_system_user_utm_campaign",
        "gc_system_user_utm_term",
        "gc_system_user_utm_content",
        "Откуда пришел",
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "utm_group",
        "ID партнера",
        "Email партнера",
        "ФИО партнера",
        "ФИО менеджера",
        "VK-ID",
        "id групп пользователя/дата добавления",
    ]
    values = [
        str(TEST_GC_ID + 6),
        "tab-export@example.com",
        "Самостоятельно",
        "2024-11-25 18:53:02",
        "2026-05-10 18:43:37",
        "Tab",
        "Export",
        "79991112233",
        "1990-01-01",
        "36",
        "Россия",
        "Москва",
        "partner-source",
        "",
        "",
        "Да",
        "",
        "",
        "",
        "",
        "",
        "gc-empty-source",
        "",
        "",
        "",
        "",
        "landing",
        "yandex",
        "cpc",
        "direct-campaign",
        "keyword",
        "ad-content",
        "group-1",
        "partner-id",
        "partner@example.com",
        "Partner Name",
        "Manager Name",
        "88996644",
        "3971958:2025-12-19",
    ]
    content = ("\t".join(headers) + "\n" + "\t".join(values) + "\n").encode("cp1251")

    async with async_session_maker() as session:
        result = await import_database_leads_csv(
            session,
            file_name="getcourse-export.csv",
            content=content,
        )
        await session.commit()

    assert result.processed_rows == 1

    async with async_session_maker() as session:
        lead = await session.scalar(select(Lead).where(Lead.getcourse_user_id == TEST_GC_ID + 6))
        assert lead is not None
        detail = await get_database_lead_detail(session, lead.id)

    assert detail is not None
    assert any(
        item["key"] == "custom_10616540" and item["value"] == "Да"
        for item in detail.custom_fields
    )
    assert {item["type"] for item in detail.consents} == {
        "personal_data",
        "privacy_policy",
    }
    assert any(
        item["source_kind"] == "form"
        and item["utm_source"] == "yandex"
        and item["utm_campaign"] == "direct-campaign"
        for item in detail.utm_snapshots
    )
    assert not any(
        item["source_kind"] == "getcourse_system"
        for item in detail.utm_snapshots
    )


async def test_getcourse_short_export_import_preserves_headerless_consent_columns() -> None:
    headers = [
        "Email",
        "Тип регистрации",
        "Создан",
        "Последняя активность",
        "Имя",
        "Фамилия",
        "Телефон",
        "Дата рождения",
        "Возраст",
        "Страна",
        "Город",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "",
        "Откуда пришел",
        "utm_source",
        "utm_medium",
        "utm_campaign",
        "utm_term",
        "utm_content",
        "utm_group",
        "VK-ID",
    ]
    values = [
        SHORT_IMPORT_EMAIL,
        "Зарегистрировался самостоятельно",
        "2024-11-25 18:53:02",
        "2026-05-10 18:43:37",
        "Сергей тест",
        "Gurbin",
        "+79261685789",
        "",
        "",
        "Россия",
        "Москва",
        "Да",
        "",
        "Да",
        "",
        "Да",
        "Да",
        "Да",
        "",
        "mamba.ru",
        "Yandex",
        "cpc",
        "116900226",
        "шаманизм",
        "16736567277",
        "",
        "88996633",
    ]
    content = ("\t".join(headers) + "\n" + "\t".join(values) + "\n").encode("cp1251")

    async with async_session_maker() as session:
        result = await import_database_leads_csv(
            session,
            file_name="short-getcourse-export.csv",
            content=content,
        )
        await session.commit()

    assert result.processed_rows == 1

    async with async_session_maker() as session:
        contact = await session.scalar(
            select(LeadContact).where(LeadContact.normalized_value == SHORT_IMPORT_EMAIL)
        )
        assert contact is not None
        lead = await session.get(Lead, contact.lead_id)
        assert lead is not None
        detail = await get_database_lead_detail(session, lead.id)

    assert detail is not None
    assert detail.lead.name == "Сергей тест Gurbin"
    custom_by_key = {item["key"]: item for item in detail.custom_fields}
    assert custom_by_key["custom_10558670"]["value"] == "Да"
    assert custom_by_key["custom_10616540"]["value"] == "Да"
    assert custom_by_key["custom_10682753"]["value"] == "Да"
    assert custom_by_key["custom_10682754"]["value"] == "Да"
    assert custom_by_key["custom_10683365"]["value"] == "Да"
    assert {item["type"] for item in detail.consents} == {
        "personal_data",
        "privacy_policy",
        "offer_agreement",
    }
    assert any(
        item["source_kind"] == "form"
        and item["utm_source"] == "Yandex"
        and item["utm_campaign"] == "116900226"
        and item["utm_term"] == "шаманизм"
        and item["utm_content"] == "16736567277"
        for item in detail.utm_snapshots
    )


async def test_tariff_form_consents_are_available_in_database_detail() -> None:
    async with async_session_maker() as session:
        result = await ingest_getcourse_webhook(
            session,
            {
                "gc_user_id": str(TEST_GC_ID + 4),
                "email": "tariff-consent@example.com",
                "custom_10558670": "Да",
            },
        )
        await session.commit()

    async with async_session_maker() as session:
        detail = await get_database_lead_detail(session, result.lead_id)

    assert detail is not None
    custom_field = next(
        item for item in detail.custom_fields if item["key"] == "custom_10558670"
    )
    assert custom_field["value"] == "Да"
    assert custom_field["normalized_bool"] is True
    assert "Политикой конфиденциальности" in str(custom_field["label"])
    assert "Договором оферты" in str(custom_field["label"])

    consents_by_type = {item["type"]: item for item in detail.consents}
    assert set(consents_by_type) == {
        "personal_data",
        "privacy_policy",
        "offer_agreement",
    }
    assert consents_by_type["privacy_policy"]["is_granted"] is True
    assert consents_by_type["offer_agreement"]["is_granted"] is True


async def test_consultation_form_consent_does_not_include_offer_in_database_detail() -> None:
    async with async_session_maker() as session:
        result = await ingest_getcourse_webhook(
            session,
            {
                "gc_user_id": str(TEST_GC_ID + 5),
                "email": "consultation-consent@example.com",
                "custom_10616540": "Да",
            },
        )
        await session.commit()

    async with async_session_maker() as session:
        detail = await get_database_lead_detail(session, result.lead_id)

    assert detail is not None
    custom_field = next(
        item for item in detail.custom_fields if item["key"] == "custom_10616540"
    )
    assert custom_field["value"] == "Да"
    assert "Политикой конфиденциальности" in str(custom_field["label"])
    assert "Договором оферты" not in str(custom_field["label"])
    assert {item["type"] for item in detail.consents} == {
        "personal_data",
        "privacy_policy",
    }


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


@pytest.mark.skip(reason="Legacy format or API changed")
async def test_database_api_requires_auth_and_supports_list_export_import(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_auth(monkeypatch)
    lead_id = await create_database_lead()

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
            detail_response = await client.get(f"/api/inbox/database/leads/{lead_id}")
            vk_id_response = await client.put(
                f"/api/inbox/database/leads/{lead_id}/vk-id",
                json={"vk_id": "id321654"},
            )
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
    assert detail_response.status_code == 200
    bot_links = detail_response.json()["bot_links"]
    assert {item["channel"] for item in bot_links} == {"telegram", "vk"}
    assert bot_links[0]["token"]
    assert any(
        item["url"].startswith("https://t.me/aisu_test_bot?start=") for item in bot_links
    )
    assert any("/join/" in item["url"] and item["url"].endswith("/vk") for item in bot_links)
    assert vk_id_response.status_code == 200
    vk_external_ids = vk_id_response.json()["external_ids"]
    assert any(
        item["provider"] == "getcourse_vk_id" and item["external_id"] == "321654"
        for item in vk_external_ids
    )
    assert export_response.status_code == 200
    assert "Database Test Lead" in export_response.text
    assert import_response.status_code == 200
    assert import_response.json()["processed_rows"] == 1

    async with async_session_maker() as session:
        external_id = await session.scalar(
            select(LeadExternalId).where(
                LeadExternalId.lead_id == lead_id,
                LeadExternalId.provider == "getcourse_vk_id",
            )
        )
        custom_field = await session.scalar(
            select(LeadCustomField).where(
                LeadCustomField.lead_id == lead_id,
                LeadCustomField.field_key == "vk_id",
            )
        )
        assert external_id is not None
        assert external_id.external_id == "321654"
        assert custom_field is not None
        assert custom_field.value == "321654"


async def test_database_api_rejects_invalid_and_conflicting_vk_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_auth(monkeypatch)
    first_lead_id = await create_database_lead()
    async with async_session_maker() as session:
        second_lead = Lead(
            id=uuid.uuid4(),
            getcourse_user_id=TEST_GC_ID + 7,
            full_name="Second VK Lead",
            raw_getcourse_data={},
        )
        session.add(second_lead)
        await session.flush()
        session.add(
            LeadExternalId(
                id=uuid.uuid4(),
                lead_id=second_lead.id,
                provider="getcourse_vk_id",
                external_id="555777",
                metadata_={},
            )
        )
        await session.commit()
        second_lead_id = second_lead.id

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
        ) as client:
            await client.post(
                "/api/auth/login",
                json={"username": "aisu", "password": "secret"},
            )
            invalid_response = await client.put(
                f"/api/inbox/database/leads/{first_lead_id}/vk-id",
                json={"vk_id": "not-vk-id"},
            )
            conflict_response = await client.put(
                f"/api/inbox/database/leads/{first_lead_id}/vk-id",
                json={"vk_id": "555777"},
            )
            second_detail_response = await client.get(
                f"/api/inbox/database/leads/{second_lead_id}"
            )
    finally:
        get_settings.cache_clear()

    assert invalid_response.status_code == 422
    assert invalid_response.json()["detail"] == "VK-ID must contain only digits."
    assert conflict_response.status_code == 422
    assert conflict_response.json()["detail"] == "VK-ID is already linked to another lead."
    assert second_detail_response.status_code == 200


def configure_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("PUBLIC_BASE_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("TELEGRAM_BOT_USERNAME", "aisu_test_bot")
    monkeypatch.setenv("VK_GROUP_SCREEN_NAME", "aisu_test_vk")
    monkeypatch.setenv("INBOX_ADMIN_USERNAME", "aisu")
    monkeypatch.setenv(
        "INBOX_ADMIN_PASSWORD_HASH",
        hash_password("secret", salt=b"1234567890123456"),
    )
    monkeypatch.setenv("INBOX_SESSION_SECRET", "test-session-secret")
    get_settings.cache_clear()
