from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import httpx
import pytest
from sqlalchemy import delete, select

from funnelhub.config import Settings
from funnelhub.db.base import Base
from funnelhub.db.models import Lead, LeadContact, LeadExternalId
from funnelhub.db.session import async_session_maker, engine
from funnelhub.services.getcourse_api import (
    build_user_export_filter,
    enrich_lead_from_getcourse_api,
    parse_export_rows,
)

TEST_EMAIL = "api-vk@example.com"
TEST_PHONE = "79990000000"


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
                select(LeadContact.lead_id).where(
                    LeadContact.normalized_value.in_({TEST_EMAIL, TEST_PHONE})
                )
            )
        )
        if lead_ids:
            await session.execute(delete(Lead).where(Lead.id.in_(lead_ids)))
        await session.commit()


async def create_lead_with_email() -> uuid.UUID:
    async with async_session_maker() as session:
        lead = Lead(id=uuid.uuid4(), full_name="API Lead", raw_getcourse_data={})
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
        await session.commit()
        return lead.id


def test_parse_export_rows_maps_fields_to_items() -> None:
    rows = parse_export_rows(
        {
            "success": True,
            "info": {
                "fields": ["ID", "Email", "VK-ID"],
                "items": [[505, TEST_EMAIL, "id321654"]],
            },
        }
    )

    assert rows == [{"ID": 505, "Email": TEST_EMAIL, "VK-ID": "id321654"}]


def test_build_user_export_filter_prefers_email_contact() -> None:
    lead = Lead(
        id=uuid.uuid4(),
        getcourse_user_id=505218377,
        raw_getcourse_data={},
    )

    assert build_user_export_filter(
        lead,
        {"email": TEST_EMAIL, "phone": TEST_PHONE},
    ) == {"email": TEST_EMAIL}


def test_build_user_export_filter_skips_getcourse_vk_technical_email() -> None:
    lead = Lead(
        id=uuid.uuid4(),
        getcourse_user_id=505218377,
        raw_getcourse_data={},
    )

    assert build_user_export_filter(lead, {"email": "id756616057@vktech.gc"}) == {}


async def test_enrich_lead_from_getcourse_api_saves_vk_id(
    prepare_database: None,
) -> None:
    lead_id = await create_lead_with_email()
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path.endswith("/pl/api/account/users"):
            assert request.url.params.get("email") == TEST_EMAIL
            assert request.url.params.get("key") == "api-key"
            return httpx.Response(200, json={"success": True, "info": {"export_id": 123}})
        if request.url.path.endswith("/pl/api/account/exports/123"):
            return httpx.Response(
                200,
                json={
                    "success": True,
                    "info": {
                        "fields": ["ID", "Email", "VK-ID", "Телефон"],
                        "items": [[505218377, TEST_EMAIL, "id321654", "+7 999 000 00 00"]],
                    },
                },
            )
        return httpx.Response(404)

    http_client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    settings = Settings(
        GETCOURSE_API_BASE_URL="https://school.example.test",
        GETCOURSE_API_KEY="api-key",
        GETCOURSE_API_POLL_ATTEMPTS=1,
        GETCOURSE_API_POLL_INTERVAL_SECONDS=0,
    )

    try:
        async with async_session_maker() as session:
            result = await enrich_lead_from_getcourse_api(
                session=session,
                settings=settings,
                lead_id=lead_id,
                http_client=http_client,
            )
            await session.commit()
    finally:
        await http_client.aclose()

    assert result.attempted is True
    assert result.updated is True
    assert calls == ["/pl/api/account/users", "/pl/api/account/exports/123"]

    async with async_session_maker() as session:
        lead = await session.get(Lead, lead_id)
        assert lead is not None
        assert lead.getcourse_user_id == 505218377

        external_id = await session.scalar(
            select(LeadExternalId).where(
                LeadExternalId.lead_id == lead_id,
                LeadExternalId.provider == "getcourse_vk_id",
            )
        )
        assert external_id is not None
        assert external_id.external_id == "321654"
