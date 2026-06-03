from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, func, select

from funnelhub.config import get_settings
from funnelhub.db.base import Base
from funnelhub.db.models import (
    BotLinkToken,
    FunnelState,
    Lead,
    LeadConsent,
    LeadContact,
    LeadCustomField,
    LeadExternalId,
    MessengerIdentity,
)
from funnelhub.db.session import async_session_maker, engine
from funnelhub.main import app
from funnelhub.services.bot_linking import link_messenger_identity

TEST_EMAIL = "webhook-test@example.com"
TEST_PHONE = "79990000000"
TEST_GC_ID = "987654321"
TEST_GC_ID_UPDATED = "987654322"
TEST_EMAIL_SECOND = "webhook-test-second@example.com"
TEST_GC_ID_SECOND = "987654323"


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
    assert "Телеграм" in join_response.text
    assert "Вконтакте" in join_response.text
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
    assert "Телеграм" in response.text
    assert "Вконтакте" in response.text

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
