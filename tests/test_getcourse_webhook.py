from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from funnelhub.config import get_settings
from funnelhub.db.base import Base
from funnelhub.db.models import (
    BotLinkToken,
    Event,
    FunnelState,
    Lead,
    LeadConsent,
    LeadContact,
    LeadCustomField,
    LeadExternalId,
    LeadUtm,
    Message,
    MessengerIdentity,
)
from funnelhub.db.session import async_session_maker, engine
from funnelhub.main import app
from funnelhub.services.bot_linking import link_messenger_identity
from funnelhub.services.ingestion_guard import getcourse_rate_limiter

TEST_EMAIL = "webhook-test@example.com"
TEST_PHONE = "79990000000"
TEST_GC_ID = "987654321"
TEST_GC_ID_UPDATED = "987654322"
TEST_EMAIL_SECOND = "webhook-test-second@example.com"
TEST_GC_ID_SECOND = "987654323"


@pytest.fixture(autouse=True)
async def prepare_database(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[None]:
    monkeypatch.setenv("GETCOURSE_WEBHOOK_SECRET", "")
    monkeypatch.setenv("GETCOURSE_WEBHOOK_SECRET_REQUIRED", "false")
    monkeypatch.setenv("GETCOURSE_WEBHOOK_RATE_LIMIT_PER_MINUTE", "120")
    monkeypatch.setenv("GETCOURSE_API_BASE_URL", "")
    monkeypatch.setenv("GETCOURSE_API_KEY", "")
    get_settings.cache_clear()
    getcourse_rate_limiter.reset()
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    await cleanup_test_leads()
    yield
    getcourse_rate_limiter.reset()
    get_settings.cache_clear()
    await cleanup_test_leads()
    await engine.dispose()


async def cleanup_test_leads() -> None:
    async with async_session_maker() as session:
        lead_ids: set[uuid.UUID] = set()
        contact_result = await session.scalars(
            select(LeadContact.lead_id).where(
                LeadContact.normalized_value.in_({TEST_EMAIL, TEST_EMAIL_SECOND, TEST_PHONE})
            )
        )
        lead_ids.update(contact_result.all())

        external_result = await session.scalars(
            select(LeadExternalId.lead_id).where(
                LeadExternalId.provider == "getcourse",
                LeadExternalId.external_id.in_(
                    {TEST_GC_ID, TEST_GC_ID_UPDATED, TEST_GC_ID_SECOND}
                ),
            )
        )
        lead_ids.update(external_result.all())

        lead_result = await session.scalars(
            select(Lead.id).where(
                Lead.getcourse_user_id.in_(
                    {int(TEST_GC_ID), int(TEST_GC_ID_UPDATED), int(TEST_GC_ID_SECOND)}
                )
            )
        )
        lead_ids.update(lead_result.all())

        if lead_ids:
            await session.execute(delete(Message).where(Message.lead_id.in_(lead_ids)))
            await session.execute(delete(Event).where(Event.lead_id.in_(lead_ids)))
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
    assert body["bot_link_token"]
    assert body["join_url"] == f"http://localhost:8000/join/{body['bot_link_token']}"

    async with async_session_maker() as session:
        email_funnel_state = await session.scalar(
            select(FunnelState).where(
                FunnelState.lead_id == uuid.UUID(body["lead_id"]),
                FunnelState.funnel_key == "aisu_email_sequence",
            )
        )
        assert email_funnel_state is not None
        assert email_funnel_state.status == "active"
        assert email_funnel_state.current_step_key == "day_01_intro"
        assert email_funnel_state.next_run_at is not None


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


async def test_getcourse_webhook_persists_extended_profile_and_source_fields() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/webhooks/getcourse",
            params={
                "gc_user_id": TEST_GC_ID,
                "email": TEST_EMAIL,
                "Тип регистрации": "Зарегистрировался самостоятельно",
                "Создан": "2024-11-25 18:53:02",
                "Последняя активность": "2026-05-10 18:43:37",
                "Имя": "Сергей тест",
                "Фамилия": "Gurbin",
                "Откуда пришел": "mamba.ru",
                "utm_source": "Yandex",
                "utm_medium": "cpc",
                "utm_campaign": "116900226",
                "utm_term": "шаманизм",
                "utm_content": "16736567277",
                "gc_system_user_utm_source": "gc-source",
                "gc_system_user_utm_campaign": "gc-campaign",
                "VK-ID": "88996633",
                "id групп пользователя/дата добавления": "3971958:2025-12-19",
            },
        )

    assert response.status_code == 200
    lead_id = uuid.UUID(response.json()["lead_id"])

    async with async_session_maker() as session:
        lead = await session.get(Lead, lead_id)
        assert lead is not None
        assert lead.registration_type == "Зарегистрировался самостоятельно"
        assert lead.getcourse_created_at is not None
        assert lead.getcourse_last_activity_at is not None
        assert lead.first_name == "Сергей тест"
        assert lead.last_name == "Gurbin"
        assert lead.full_name == "Сергей тест Gurbin"
        assert lead.source == "mamba.ru"

        external_id = await session.scalar(
            select(LeadExternalId).where(
                LeadExternalId.provider == "getcourse_vk_id",
                LeadExternalId.external_id == "88996633",
            )
        )
        assert external_id is not None
        assert external_id.lead_id == lead_id

        field_values = {
            field.field_key: field.value
            for field in await session.scalars(
                select(LeadCustomField).where(LeadCustomField.lead_id == lead_id)
            )
        }
        assert field_values["vk_id"] == "88996633"
        assert field_values["getcourse_groups"] == "3971958:2025-12-19"

        utm_rows = (
            await session.scalars(select(LeadUtm).where(LeadUtm.lead_id == lead_id))
        ).all()
        utm_by_kind = {row.source_kind: row for row in utm_rows}
        assert set(utm_by_kind) == {"form"}
        assert utm_by_kind["form"].utm_source == "Yandex"
        assert utm_by_kind["form"].utm_campaign == "116900226"
        assert utm_by_kind["form"].utm_term == "шаманизм"
        assert utm_by_kind["form"].utm_content == "16736567277"


async def test_getcourse_webhook_normalizes_vk_id_from_profile_url() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/webhooks/getcourse",
            params={
                "gc_user_id": TEST_GC_ID,
                "email": TEST_EMAIL,
                "ID VK": "https://vk.com/id88996633",
            },
        )

    assert response.status_code == 200
    lead_id = uuid.UUID(response.json()["lead_id"])

    async with async_session_maker() as session:
        external_id = await session.scalar(
            select(LeadExternalId).where(
                LeadExternalId.provider == "getcourse_vk_id",
                LeadExternalId.external_id == "88996633",
            )
        )
        assert external_id is not None
        assert external_id.lead_id == lead_id

        custom_field = await session.scalar(
            select(LeadCustomField).where(
                LeadCustomField.lead_id == lead_id,
                LeadCustomField.field_key == "vk_id",
            )
        )
        assert custom_field is not None
        assert custom_field.value == "88996633"


async def test_getcourse_webhook_sends_one_admin_notification_for_duplicate_ingest(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("EMAIL_PROVIDER", "debug")
    monkeypatch.setenv("LEAD_NOTIFICATION_EMAIL_TO", "aisukam-info@example.com")
    monkeypatch.setenv("LEAD_NOTIFICATION_COOLDOWN_SECONDS", "300")
    get_settings.cache_clear()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first_response = await client.post(
            "/webhooks/getcourse",
            data={
                "gc_user_id": TEST_GC_ID,
                "email": TEST_EMAIL,
                "phone": "+7 999 000-00-00",
                "name": "Ольга",
                "form_type": "consultation",
            },
        )
        redirect_response = await client.get(
            "/join/getcourse",
            params={
                "gc_user_id": TEST_GC_ID,
                "email": TEST_EMAIL,
                "phone": "+7 999 000-00-00",
                "name": "Ольга",
            },
        )

    assert first_response.status_code == 200
    assert redirect_response.status_code == 200
    lead_id = uuid.UUID(first_response.json()["lead_id"])

    async with async_session_maker() as session:
        messages = (
            await session.scalars(
                select(Message).where(
                    Message.lead_id == lead_id,
                    Message.channel == "email",
                    Message.direction == "outbound",
                )
            )
        ).all()
        notification_messages = [
            message
            for message in messages
            if message.metadata_.get("notification_type") == "lead_application"
        ]
        assert len(notification_messages) == 1
        assert notification_messages[0].status == "sent"
        assert notification_messages[0].metadata_["to_email"] == "aisukam-info@example.com"
        assert "Ольга" in (notification_messages[0].body or "")

        sent_events = (
            await session.scalars(
                select(Event).where(
                    Event.lead_id == lead_id,
                    Event.event_type == "lead.application.notification.sent",
                )
            )
        ).all()
        assert len(sent_events) == 1


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


async def test_getcourse_webhook_reuses_active_bot_link_token_for_existing_lead() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first_response = await client.get(
            "/webhooks/getcourse",
            params={"gc_user_id": TEST_GC_ID, "email": TEST_EMAIL},
        )
        second_response = await client.get(
            "/webhooks/getcourse",
            params={"gc_user_id": TEST_GC_ID, "email": TEST_EMAIL},
        )

    assert first_response.json()["bot_link_token"] == second_response.json()["bot_link_token"]

    lead_id = uuid.UUID(first_response.json()["lead_id"])
    async with async_session_maker() as session:
        email_funnel_count = await session.scalar(
            select(func.count())
            .select_from(FunnelState)
            .where(
                FunnelState.lead_id == lead_id,
                FunnelState.funnel_key == "aisu_email_sequence",
            )
        )
    assert email_funnel_count == 1


async def test_join_page_renders_for_active_bot_link_token() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        webhook_response = await client.get(
            "/webhooks/getcourse",
            params={"gc_user_id": TEST_GC_ID, "email": TEST_EMAIL},
        )
        token = webhook_response.json()["bot_link_token"]
        join_response = await client.get(f"/join/{token}")

    assert join_response.status_code == 200
    assert "Спасибо за вашу заявку!" in join_response.text
    assert "Открыть Telegram" in join_response.text
    assert "Открыть VK" in join_response.text
    assert join_response.text.index('class="actions"') < join_response.text.index(
        'class="gift-list"'
    )
    assert join_response.text.index('class="actions"') < join_response.text.index(
        'class="visual"'
    )
    assert token in join_response.text


async def test_getcourse_redirect_join_page_creates_lead_and_renders_buttons() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/join/getcourse",
            params={
                "gc_user_id": TEST_GC_ID,
                "email": TEST_EMAIL,
                "phone": "+7 999 000-00-00",
                "name": "Сергей тест Gurban",
                "utm_source": "yandex",
            },
        )

    assert response.status_code == 200
    assert "Спасибо за вашу заявку!" in response.text
    assert "Открыть Telegram" in response.text
    assert "Открыть VK" in response.text

    async with async_session_maker() as session:
        lead = await session.scalar(
            select(Lead).where(Lead.getcourse_user_id == int(TEST_GC_ID))
        )
        assert lead is not None
        assert lead.full_name == "Сергей тест Gurban"

        email_contact = await session.scalar(
            select(LeadContact).where(
                LeadContact.contact_type == "email",
                LeadContact.normalized_value == TEST_EMAIL,
            )
        )
        assert email_contact is not None
        assert email_contact.lead_id == lead.id
        consent_types = set(
            await session.scalars(
                select(LeadConsent.consent_type).where(LeadConsent.lead_id == lead.id)
            )
        )
        assert consent_types == {"personal_data", "privacy_policy"}


async def test_getcourse_redirect_join_page_derives_tariff_consent_from_form_type() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/join/getcourse",
            params={
                "gc_user_id": TEST_GC_ID,
                "email": TEST_EMAIL,
                "phone": "+7 999 000-00-00",
                "name": "Тариф тест",
                "form_type": "baseTariff",
            },
        )

    assert response.status_code == 200

    async with async_session_maker() as session:
        lead = await session.scalar(
            select(Lead).where(Lead.getcourse_user_id == int(TEST_GC_ID))
        )
        assert lead is not None
        custom_field = await session.scalar(
            select(LeadCustomField).where(
                LeadCustomField.lead_id == lead.id,
                LeadCustomField.field_key == "custom_10682754",
            )
        )
        assert custom_field is not None
        assert custom_field.value == "Да"
        consent_types = set(
            await session.scalars(
                select(LeadConsent.consent_type).where(LeadConsent.lead_id == lead.id)
            )
        )
        assert consent_types == {"personal_data", "privacy_policy", "offer_agreement"}


async def test_getcourse_redirect_join_page_rejects_unresolved_placeholders() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/join/getcourse",
            params={
                "name": "{name}",
                "phone": "{phone}",
                "email": "{email}",
            },
        )

    assert response.status_code == 400
    assert "Не удалось получить данные заявки" in response.text


async def test_getcourse_webhook_allows_missing_secret_in_compatibility_mode(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GETCOURSE_WEBHOOK_SECRET", "expected-secret")
    monkeypatch.setenv("GETCOURSE_WEBHOOK_SECRET_REQUIRED", "false")
    get_settings.cache_clear()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/webhooks/getcourse",
            params={"gc_user_id": TEST_GC_ID, "email": TEST_EMAIL},
        )

    assert response.status_code == 200


async def test_getcourse_webhook_accepts_valid_shared_secret_header(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GETCOURSE_WEBHOOK_SECRET", "expected-secret")
    monkeypatch.setenv("GETCOURSE_WEBHOOK_SECRET_REQUIRED", "true")
    get_settings.cache_clear()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/webhooks/getcourse",
            params={"gc_user_id": TEST_GC_ID, "email": TEST_EMAIL},
            headers={"X-FunnelHub-Webhook-Secret": "expected-secret"},
        )

    assert response.status_code == 200


async def test_getcourse_webhook_rejects_invalid_shared_secret_without_creating_lead(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GETCOURSE_WEBHOOK_SECRET", "expected-secret")
    monkeypatch.setenv("GETCOURSE_WEBHOOK_SECRET_REQUIRED", "true")
    get_settings.cache_clear()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/webhooks/getcourse",
            params={
                "gc_user_id": TEST_GC_ID,
                "email": TEST_EMAIL,
                "fh_secret": "wrong-secret",
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "Invalid GetCourse webhook secret."
    async with async_session_maker() as session:
        lead_count = await session.scalar(
            select(func.count()).select_from(Lead).where(Lead.getcourse_user_id == int(TEST_GC_ID))
        )
    assert lead_count == 0


async def test_getcourse_webhook_rejects_missing_required_shared_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GETCOURSE_WEBHOOK_SECRET", "expected-secret")
    monkeypatch.setenv("GETCOURSE_WEBHOOK_SECRET_REQUIRED", "true")
    get_settings.cache_clear()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/webhooks/getcourse",
            params={"gc_user_id": TEST_GC_ID, "email": TEST_EMAIL},
        )

    assert response.status_code == 403
    assert response.json()["detail"] == "GetCourse webhook secret is required."


async def test_getcourse_webhook_strips_query_secret_from_raw_payload(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GETCOURSE_WEBHOOK_SECRET", "expected-secret")
    monkeypatch.setenv("GETCOURSE_WEBHOOK_SECRET_REQUIRED", "true")
    get_settings.cache_clear()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/webhooks/getcourse",
            params={
                "gc_user_id": TEST_GC_ID,
                "email": TEST_EMAIL,
                "fh_secret": "expected-secret",
            },
        )

    assert response.status_code == 200
    lead_id = uuid.UUID(response.json()["lead_id"])
    async with async_session_maker() as session:
        lead = await session.get(Lead, lead_id)
    assert lead is not None
    assert "fh_secret" not in lead.raw_getcourse_data


async def test_getcourse_webhook_rate_limits_by_client_ip(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GETCOURSE_WEBHOOK_RATE_LIMIT_PER_MINUTE", "1")
    get_settings.cache_clear()
    getcourse_rate_limiter.reset()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first_response = await client.get(
            "/webhooks/getcourse",
            params={"gc_user_id": TEST_GC_ID, "email": TEST_EMAIL},
            headers={"X-Forwarded-For": "203.0.113.10"},
        )
        second_response = await client.get(
            "/webhooks/getcourse",
            params={"gc_user_id": TEST_GC_ID_SECOND, "email": TEST_EMAIL_SECOND},
            headers={"X-Forwarded-For": "203.0.113.10"},
        )

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    async with async_session_maker() as session:
        second_lead_count = await session.scalar(
            select(func.count())
            .select_from(Lead)
            .where(Lead.getcourse_user_id == int(TEST_GC_ID_SECOND))
        )
    assert second_lead_count == 0


async def test_getcourse_redirect_join_page_rejects_invalid_shared_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("GETCOURSE_WEBHOOK_SECRET", "expected-secret")
    monkeypatch.setenv("GETCOURSE_WEBHOOK_SECRET_REQUIRED", "true")
    get_settings.cache_clear()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/join/getcourse",
            params={
                "gc_user_id": TEST_GC_ID,
                "email": TEST_EMAIL,
                "fh_secret": "wrong-secret",
            },
        )

    assert response.status_code == 403
    async with async_session_maker() as session:
        lead_count = await session.scalar(
            select(func.count()).select_from(Lead).where(Lead.getcourse_user_id == int(TEST_GC_ID))
        )
    assert lead_count == 0


async def test_messenger_link_binds_telegram_identity_to_lead() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        webhook_response = await client.get(
            "/webhooks/getcourse",
            params={"gc_user_id": TEST_GC_ID, "email": TEST_EMAIL},
        )
        token = webhook_response.json()["bot_link_token"]
        link_response = await client.post(
            "/api/messenger/link",
            json={
                "token": token,
                "channel": "telegram",
                "external_user_id": "telegram-123",
                "username": "test_user",
                "display_name": "Test User",
                "raw_profile": {"language_code": "ru"},
            },
        )

    assert link_response.status_code == 200
    assert link_response.json()["created"] is True

    async with async_session_maker() as session:
        lead_id = uuid.UUID(webhook_response.json()["lead_id"])
        identity = await session.scalar(
            select(MessengerIdentity).where(
                MessengerIdentity.channel == "telegram",
                MessengerIdentity.external_user_id == "telegram-123",
            )
        )
        assert identity is not None
        assert identity.lead_id == lead_id
        assert identity.username == "test_user"

        bot_link_token = await session.scalar(
            select(BotLinkToken).where(BotLinkToken.token == token)
        )
        assert bot_link_token is not None
        assert bot_link_token.used_at is not None

        funnel_state = await session.scalar(
            select(FunnelState).where(
                FunnelState.lead_id == lead_id,
                FunnelState.funnel_key == "aisu_consultation",
            )
        )
        assert funnel_state is not None
        assert funnel_state.status == "active"
        assert funnel_state.current_step_key == "welcome"
        assert funnel_state.metadata_["messenger_channel"] == "telegram"


async def test_repeated_telegram_link_reuses_default_funnel_state() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        webhook_response = await client.get(
            "/webhooks/getcourse",
            params={"gc_user_id": TEST_GC_ID, "email": TEST_EMAIL},
        )
        token = webhook_response.json()["bot_link_token"]
        payload = {
            "token": token,
            "channel": "telegram",
            "external_user_id": "telegram-123",
        }
        first_link_response = await client.post("/api/messenger/link", json=payload)
        second_link_response = await client.post("/api/messenger/link", json=payload)

    assert first_link_response.status_code == 200
    assert first_link_response.json()["created"] is True
    assert second_link_response.status_code == 200
    assert second_link_response.json()["created"] is False

    lead_id = uuid.UUID(webhook_response.json()["lead_id"])
    async with async_session_maker() as session:
        funnel_count = await session.scalar(
            select(func.count())
            .select_from(FunnelState)
            .where(
                FunnelState.lead_id == lead_id,
                FunnelState.funnel_key == "aisu_consultation",
            )
        )
    assert funnel_count == 1


async def test_messenger_link_binds_vk_identity_and_starts_default_funnel() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        webhook_response = await client.get(
            "/webhooks/getcourse",
            params={"gc_user_id": TEST_GC_ID, "email": TEST_EMAIL},
        )
        token = webhook_response.json()["bot_link_token"]
        link_response = await client.post(
            "/api/messenger/link",
            json={
                "token": token,
                "channel": "vk",
                "external_user_id": "vk-123",
                "raw_profile": {"from_id": 123},
            },
        )

    assert link_response.status_code == 200
    assert link_response.json()["created"] is True

    lead_id = uuid.UUID(webhook_response.json()["lead_id"])
    async with async_session_maker() as session:
        identity = await session.scalar(
            select(MessengerIdentity).where(
                MessengerIdentity.channel == "vk",
                MessengerIdentity.external_user_id == "vk-123",
            )
        )
        assert identity is not None
        assert identity.lead_id == lead_id

        funnel_state = await session.scalar(
            select(FunnelState).where(
                FunnelState.lead_id == lead_id,
                FunnelState.funnel_key == "aisu_consultation",
            )
        )
        assert funnel_state is not None
        assert funnel_state.status == "active"
        assert funnel_state.metadata_["messenger_channel"] == "vk"


async def test_vk_callback_confirmation_returns_configured_code(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VK_CALLBACK_SECRET", "secret")
    monkeypatch.setenv("VK_CONFIRMATION_CODE", "confirm-code")
    get_settings.cache_clear()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            response = await client.post(
                "/webhooks/vk",
                json={"type": "confirmation", "secret": "secret", "group_id": 123},
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert response.text == "confirm-code"


async def test_vk_callback_message_new_links_identity_and_starts_funnel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VK_GROUP_ACCESS_TOKEN", "")
    get_settings.cache_clear()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            webhook_response = await client.get(
                "/webhooks/getcourse",
                params={"gc_user_id": TEST_GC_ID, "email": TEST_EMAIL},
            )
            token = webhook_response.json()["bot_link_token"]
            response = await client.post(
                "/webhooks/vk",
                json={
                    "type": "message_new",
                    "secret": get_settings().vk_callback_secret,
                    "group_id": 123,
                    "object": {
                        "message": {
                            "from_id": 321,
                            "peer_id": 321,
                            "text": f"/start {token}",
                        }
                    },
                },
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert response.text == "ok"

    lead_id = uuid.UUID(webhook_response.json()["lead_id"])
    async with async_session_maker() as session:
        identity = await session.scalar(
            select(MessengerIdentity).where(
                MessengerIdentity.channel == "vk",
                MessengerIdentity.external_user_id == "321",
            )
        )
        assert identity is not None
        assert identity.lead_id == lead_id

        funnel_state = await session.scalar(
            select(FunnelState).where(
                FunnelState.lead_id == lead_id,
                FunnelState.funnel_key == "aisu_consultation",
            )
        )
        assert funnel_state is not None


async def test_vk_callback_message_allow_links_identity_and_starts_funnel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VK_GROUP_ACCESS_TOKEN", "")
    get_settings.cache_clear()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            webhook_response = await client.get(
                "/webhooks/getcourse",
                params={"gc_user_id": TEST_GC_ID, "email": TEST_EMAIL},
            )
            token = webhook_response.json()["bot_link_token"]
            response = await client.post(
                "/webhooks/vk",
                json={
                    "type": "message_allow",
                    "secret": get_settings().vk_callback_secret,
                    "group_id": 123,
                    "object": {
                        "user_id": 654,
                        "key": token,
                    },
                },
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200
    assert response.text == "ok"

    lead_id = uuid.UUID(webhook_response.json()["lead_id"])
    async with async_session_maker() as session:
        identity = await session.scalar(
            select(MessengerIdentity).where(
                MessengerIdentity.channel == "vk",
                MessengerIdentity.external_user_id == "654",
            )
        )
        assert identity is not None
        assert identity.lead_id == lead_id

        funnel_state = await session.scalar(
            select(FunnelState).where(
                FunnelState.lead_id == lead_id,
                FunnelState.funnel_key == "aisu_consultation",
            )
        )
        assert funnel_state is not None


async def test_vk_launch_redirect_uses_known_getcourse_vk_id_and_restarts_funnel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    sent_messages: list[dict[str, object]] = []

    class FakeHttpVkMessageClient:
        def __init__(self, **kwargs: object) -> None:
            self.kwargs = kwargs

        async def send_message(
            self,
            peer_id: int | str,
            message: str,
            *,
            keyboard: dict[str, object] | None = None,
        ) -> dict[str, object]:
            sent_messages.append(
                {
                    "peer_id": str(peer_id),
                    "message": message,
                    "keyboard": keyboard,
                }
            )
            return {"response": 889}

    monkeypatch.setenv("VK_GROUP_SCREEN_NAME", "aisu_test_vk")
    monkeypatch.setenv("VK_GROUP_ACCESS_TOKEN", "vk-access-token")
    monkeypatch.setattr("funnelhub.api.messenger.HttpVkMessageClient", FakeHttpVkMessageClient)
    get_settings.cache_clear()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            webhook_response = await client.get(
                "/webhooks/getcourse",
                params={
                    "gc_user_id": TEST_GC_ID,
                    "email": TEST_EMAIL,
                    "VK-ID": "321654",
                },
            )
            token = webhook_response.json()["bot_link_token"]
            lead_id = uuid.UUID(webhook_response.json()["lead_id"])
            async with async_session_maker() as session:
                session.add(
                    FunnelState(
                        id=uuid.uuid4(),
                        lead_id=lead_id,
                        funnel_key="aisu_consultation",
                            channel="vk",
                        status="active",
                        current_step_key="step_02_video",
                        next_run_at=datetime(2026, 6, 6, 5, 49, tzinfo=UTC),
                        metadata_={
                            "answers": {
                                "topic": "all",
                                "experience": "self_practice",
                            },
                            "step_index": 3,
                            "messenger_channel": "vk",
                            "definition_version": 2,
                            "pending_question_key": "topic",
                            "personalized_sent_at": "2026-06-05T13:57:29.947739+00:00",
                            "last_question_sent_at": "2026-06-06T05:19:04.790701+00:00",
                            "questionnaire_waiting_for_step_key": "step_01_video",
                        },
                    )
                )
                await session.commit()
            response = await client.get(f"/join/{token}/vk")
    finally:
        get_settings.cache_clear()

    assert response.status_code == 307
    assert response.headers["location"] == f"https://vk.me/aisu_test_vk?ref={token}"
    assert sent_messages
    assert sent_messages[0]["peer_id"] == "321654"
    assert "Ваша заявка на консультацию принята" in str(sent_messages[0]["message"])

    async with async_session_maker() as session:
        identity = await session.scalar(
            select(MessengerIdentity).where(
                MessengerIdentity.lead_id == lead_id,
                MessengerIdentity.channel == "vk",
                MessengerIdentity.external_user_id == "321654",
            )
        )
        assert identity is not None
        assert identity.is_subscribed is True

        funnel_state = await session.scalar(
            select(FunnelState).where(
                FunnelState.lead_id == lead_id,
                FunnelState.funnel_key == "aisu_consultation",
            )
        )
        assert funnel_state is not None
        assert funnel_state.current_step_key == "question_topic"
        assert funnel_state.metadata_["messenger_channel"] == "vk"
        assert funnel_state.metadata_["last_vk_join_relaunch_reason"] == "vk_launch_link"
        assert "answers" not in funnel_state.metadata_
        assert "pending_question_key" not in funnel_state.metadata_
        assert "questionnaire_waiting_for_step_key" not in funnel_state.metadata_
        assert "last_question_sent_at" not in funnel_state.metadata_
        assert "personalized_sent_at" not in funnel_state.metadata_

        message = await session.scalar(
            select(Message).where(
                Message.lead_id == lead_id,
                Message.channel == "vk",
                Message.direction == "outbound",
            )
        )
        assert message is not None
        assert message.status == "sent"


async def test_vk_callback_token_restarts_existing_funnel_state(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("VK_GROUP_ACCESS_TOKEN", "")
    get_settings.cache_clear()
    try:
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            webhook_response = await client.get(
                "/webhooks/getcourse",
                params={"gc_user_id": TEST_GC_ID, "email": TEST_EMAIL},
            )
            token = webhook_response.json()["bot_link_token"]
            lead_id = uuid.UUID(webhook_response.json()["lead_id"])
            async with async_session_maker() as session:
                session.add(
                    FunnelState(
                        id=uuid.uuid4(),
                        lead_id=lead_id,
                        funnel_key="aisu_consultation",
                            channel="vk",
                        status="active",
                        current_step_key="step_02_video",
                        next_run_at=datetime(2026, 6, 6, 5, 49, tzinfo=UTC),
                        metadata_={
                            "answers": {"topic": "all"},
                            "step_index": 3,
                            "messenger_channel": "vk",
                            "definition_version": 2,
                            "pending_question_key": "topic",
                        },
                    )
                )
                await session.commit()

            response = await client.post(
                "/webhooks/vk",
                json={
                    "type": "message_new",
                    "secret": get_settings().vk_callback_secret,
                    "group_id": 123,
                    "object": {
                        "message": {
                            "from_id": 321,
                            "peer_id": 321,
                            "text": f"/start {token}",
                        }
                    },
                },
            )
    finally:
        get_settings.cache_clear()

    assert response.status_code == 200

    async with async_session_maker() as session:
        funnel_state = await session.scalar(
            select(FunnelState).where(
                FunnelState.lead_id == lead_id,
                FunnelState.funnel_key == "aisu_consultation",
            )
        )
        assert funnel_state is not None
        assert funnel_state.current_step_key == "welcome"
        assert funnel_state.metadata_["messenger_channel"] == "vk"
        assert funnel_state.metadata_["restart_reason"] == "bot_start"
        assert "answers" not in funnel_state.metadata_
        assert "pending_question_key" not in funnel_state.metadata_


async def test_messenger_link_rejects_unknown_token() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/messenger/link",
            json={
                "token": "unknown-token-value",
                "channel": "telegram",
                "external_user_id": "telegram-123",
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Bot link token is invalid or expired."


async def test_messenger_link_rejects_same_telegram_id_for_another_lead() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first_webhook_response = await client.get(
            "/webhooks/getcourse",
            params={"gc_user_id": TEST_GC_ID, "email": TEST_EMAIL},
        )
        await client.post(
            "/api/messenger/link",
            json={
                "token": first_webhook_response.json()["bot_link_token"],
                "channel": "telegram",
                "external_user_id": "telegram-123",
            },
        )
        second_webhook_response = await client.get(
            "/webhooks/getcourse",
            params={"gc_user_id": TEST_GC_ID_SECOND, "email": TEST_EMAIL_SECOND},
        )
        response = await client.post(
            "/api/messenger/link",
            json={
                "token": second_webhook_response.json()["bot_link_token"],
                "channel": "telegram",
                "external_user_id": "telegram-123",
            },
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "Messenger identity is already linked to another lead."


async def test_bot_start_can_relink_messenger_identity_to_new_lead() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        first_webhook_response = await client.get(
            "/webhooks/getcourse",
            params={"gc_user_id": TEST_GC_ID, "email": TEST_EMAIL},
        )
        second_webhook_response = await client.get(
            "/webhooks/getcourse",
            params={"gc_user_id": TEST_GC_ID_SECOND, "email": TEST_EMAIL_SECOND},
        )

    async with async_session_maker() as session:
        first_result = await link_messenger_identity(
            session=session,
            token=first_webhook_response.json()["bot_link_token"],
            channel="vk",
            external_user_id="vk-123",
            username=None,
            display_name=None,
            raw_profile={},
            allow_relink=True,
        )
        second_result = await link_messenger_identity(
            session=session,
            token=second_webhook_response.json()["bot_link_token"],
            channel="vk",
            external_user_id="vk-123",
            username=None,
            display_name=None,
            raw_profile={},
            allow_relink=True,
        )
        await session.commit()

    assert first_result.identity_id == second_result.identity_id
    assert first_result.lead_id != second_result.lead_id

    async with async_session_maker() as session:
        identity = await session.scalar(
            select(MessengerIdentity).where(
                MessengerIdentity.channel == "vk",
                MessengerIdentity.external_user_id == "vk-123",
            )
        )
        assert identity is not None
        assert identity.lead_id == second_result.lead_id


async def test_getcourse_webhook_derives_consents_from_mapped_custom_field() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/webhooks/getcourse",
            params={
                "gc_user_id": TEST_GC_ID,
                "email": TEST_EMAIL,
                "custom_10558670": "Да",
            },
        )
    lead_id = uuid.UUID(response.json()["lead_id"])

    async with async_session_maker() as session:
        consents = (
            await session.scalars(
                select(LeadConsent).where(
                    LeadConsent.lead_id == lead_id,
                    LeadConsent.source == "getcourse",
                )
            )
        ).all()

    consents_by_type = {consent.consent_type: consent for consent in consents}
    assert set(consents_by_type) == {"personal_data", "privacy_policy", "offer_agreement"}
    assert all(consent.is_granted is True for consent in consents)
    assert consents_by_type["personal_data"].metadata_["custom_field_keys"] == [
        "custom_10558670"
    ]
    assert (
        consents_by_type["privacy_policy"].metadata_["privacy_policy_url"]
        == "https://shamanaisu.getcourse.ru/politica"
    )
    assert (
        consents_by_type["offer_agreement"].metadata_["offer_url"]
        == "https://shamanaisu.getcourse.ru/oferta"
    )


async def test_getcourse_webhook_does_not_derive_offer_consent_for_policy_only_field() -> None:
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(
            "/webhooks/getcourse",
            params={
                "gc_user_id": TEST_GC_ID,
                "email": TEST_EMAIL,
                "custom_10616540": "Да",
            },
        )
    lead_id = uuid.UUID(response.json()["lead_id"])

    async with async_session_maker() as session:
        consent_types = set(
            await session.scalars(
                select(LeadConsent.consent_type).where(LeadConsent.lead_id == lead_id)
            )
        )

    assert consent_types == {"personal_data", "privacy_policy"}


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
