from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from funnelhub.api.inbox import ApiInboxSendClients
from funnelhub.config import get_settings
from funnelhub.db.base import Base
from funnelhub.db.models import (
    Conversation,
    FunnelFollowupDelivery,
    FunnelFollowupPost,
    FunnelState,
    Lead,
    Message,
    MessengerIdentity,
)
from funnelhub.db.session import async_session_maker, engine
from funnelhub.main import app
from funnelhub.services.auth import hash_password
from funnelhub.services.followup_posts import create_followup_post
from funnelhub.services.followup_runner import run_due_followup_posts_once

TEST_GC_ID = 987660000
TEST_TITLE_PREFIX = "Followup pytest"


class FakeTelegramMessage:
    message_id = 601


class FakeTelegramBot:
    def __init__(self) -> None:
        self.calls: list[tuple[str | int, str]] = []

    async def send_message(
        self,
        chat_id: int | str,
        text: str,
        *,
        reply_markup: Any | None = None,
    ) -> FakeTelegramMessage:
        self.calls.append((chat_id, text))
        return FakeTelegramMessage()


class FakeVkClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str | int, str]] = []

    async def send_message(
        self,
        peer_id: int | str,
        message: str,
        *,
        keyboard: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self.calls.append((peer_id, message))
        return {"response": 902}


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
        post_ids = set(
            await session.scalars(
                select(FunnelFollowupPost.id).where(
                    FunnelFollowupPost.title.startswith(TEST_TITLE_PREFIX)
                )
            )
        )
        if post_ids:
            await session.execute(
                delete(FunnelFollowupDelivery).where(
                    FunnelFollowupDelivery.followup_post_id.in_(post_ids)
                )
            )
            await session.execute(
                delete(FunnelFollowupPost).where(FunnelFollowupPost.id.in_(post_ids))
            )

        lead_ids = set(
            await session.scalars(
                select(Lead.id).where(
                    Lead.getcourse_user_id >= TEST_GC_ID,
                    Lead.getcourse_user_id < TEST_GC_ID + 100,
                )
            )
        )
        if lead_ids:
            await session.execute(delete(Message).where(Message.lead_id.in_(lead_ids)))
            await session.execute(delete(Conversation).where(Conversation.lead_id.in_(lead_ids)))
            await session.execute(delete(Lead).where(Lead.id.in_(lead_ids)))
        await session.commit()


def configure_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INBOX_ADMIN_USERNAME", "aisu")
    monkeypatch.setenv(
        "INBOX_ADMIN_PASSWORD_HASH",
        hash_password("secret", salt=b"1234567890123456"),
    )
    monkeypatch.setenv("INBOX_SESSION_SECRET", "test-session-secret")
    get_settings.cache_clear()


async def create_completed_followup_lead(
    *,
    gc_id: int = TEST_GC_ID,
    telegram: bool = True,
    vk: bool = True,
    vk_subscribed: bool = True,
    completed: bool = True,
) -> uuid.UUID:
    async with async_session_maker() as session:
        lead = Lead(
            id=uuid.uuid4(),
            getcourse_user_id=gc_id,
            full_name=f"Followup Lead {gc_id}",
            raw_getcourse_data={},
        )
        session.add(lead)
        await session.flush()
        session.add(
            FunnelState(
                id=uuid.uuid4(),
                lead_id=lead.id,
                funnel_key="aisu_consultation",
                channel="telegram",
                status="completed" if completed else "active",
                current_step_key="day_18" if completed else "day_05",
                completed_at=datetime.now(UTC) - timedelta(days=1) if completed else None,
                metadata_={},
            )
        )
        if telegram:
            session.add(
                MessengerIdentity(
                    id=uuid.uuid4(),
                    lead_id=lead.id,
                    channel="telegram",
                    external_user_id=f"followup-tg-{gc_id}",
                    is_subscribed=True,
                    raw_profile={},
                )
            )
        if vk:
            session.add(
                MessengerIdentity(
                    id=uuid.uuid4(),
                    lead_id=lead.id,
                    channel="vk",
                    external_user_id=f"followup-vk-{gc_id}",
                    is_subscribed=vk_subscribed,
                    raw_profile={},
                )
            )
        await session.commit()
        return lead.id


async def test_followup_api_previews_creates_dedupes_and_cancels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_auth(monkeypatch)
    lead_id = await create_completed_followup_lead()
    await create_completed_followup_lead(gc_id=TEST_GC_ID + 1, telegram=False, vk=True)
    await create_completed_followup_lead(gc_id=TEST_GC_ID + 2, completed=False)
    schedule = datetime.now(UTC) + timedelta(hours=2)

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
        ) as client:
            await client.post(
                "/api/auth/login",
                json={"username": "aisu", "password": "secret"},
            )
            preview_response = await client.get(
                "/api/inbox/followup-posts/recipient-preview?channels=telegram&channels=vk"
            )
            payload = {
                "title": f"{TEST_TITLE_PREFIX} API",
                "body": "  Текст follow-up  ",
                "channels": ["telegram", "telegram", "vk"],
                "scheduled_at": schedule.isoformat(),
            }
            first_response = await client.post("/api/inbox/followup-posts", json=payload)
            second_response = await client.post("/api/inbox/followup-posts", json=payload)
            blank_response = await client.post(
                "/api/inbox/followup-posts",
                json={**payload, "body": "   "},
            )
            list_response = await client.get("/api/inbox/followup-posts")
    finally:
        get_settings.cache_clear()

    assert preview_response.status_code == 200
    assert preview_response.json() == {
        "total": 3,
        "by_channel": {"telegram": 1, "vk": 2},
    }
    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert blank_response.status_code == 422
    created = first_response.json()
    duplicated = second_response.json()
    assert duplicated["id"] == created["id"]
    assert created["channels"] == ["telegram", "vk"]
    assert created["status"] == "scheduled"
    assert created["total_deliveries"] == 3
    assert {item["status"] for item in created["deliveries"]} == {"pending"}
    assert any(item["lead_id"] == str(lead_id) for item in created["deliveries"])
    assert list_response.status_code == 200
    assert any(item["id"] == created["id"] for item in list_response.json()["items"])

    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
        ) as client:
            await client.post(
                "/api/auth/login",
                json={"username": "aisu", "password": "secret"},
            )
            cancel_response = await client.patch(
                f"/api/inbox/followup-posts/{created['id']}/cancel"
            )
    finally:
        get_settings.cache_clear()

    assert cancel_response.status_code == 200
    cancelled = cancel_response.json()
    assert cancelled["status"] == "cancelled"
    assert {item["status"] for item in cancelled["deliveries"]} == {"cancelled"}


async def test_followup_runner_sends_each_delivery_once() -> None:
    await create_completed_followup_lead()
    bot = FakeTelegramBot()
    vk_client = FakeVkClient()

    async with async_session_maker() as session:
        post = await create_followup_post(
            session,
            title=f"{TEST_TITLE_PREFIX} runner",
            body="Сообщение после 18 дня",
            channels=["telegram", "vk"],
        )
        await session.commit()
        post_id = post.id

    clients = ApiInboxSendClients(
        telegram_bot=bot,
        vk_client=vk_client,
        email_client=None,
        email_subject="",
        public_base_url="http://127.0.0.1:8000",
        email_from_email=None,
        email_from_name=None,
        email_signature_image_url=None,
    )
    async with async_session_maker() as session:
        stats = await run_due_followup_posts_once(session, clients=clients)
        second_stats = await run_due_followup_posts_once(session, clients=clients)

    assert stats.due == 1
    assert stats.completed == 1
    assert second_stats.due == 0
    assert bot.calls == [(f"followup-tg-{TEST_GC_ID}", "Сообщение после 18 дня")]
    assert vk_client.calls == [(f"followup-vk-{TEST_GC_ID}", "Сообщение после 18 дня")]

    async with async_session_maker() as session:
        stored = await session.get(FunnelFollowupPost, post_id)
        deliveries = list(
            (
                await session.scalars(
                    select(FunnelFollowupDelivery).where(
                        FunnelFollowupDelivery.followup_post_id == post_id
                    )
                )
            ).all()
        )

    assert stored is not None
    assert stored.status == "completed"
    assert stored.sent_deliveries == 2
    assert {delivery.status for delivery in deliveries} == {"sent"}
    assert {delivery.external_message_id for delivery in deliveries} == {"601", "902"}


async def test_followup_runner_skips_unsubscribed_identity_at_send_time() -> None:
    lead_id = await create_completed_followup_lead(telegram=False, vk=True)

    async with async_session_maker() as session:
        post = await create_followup_post(
            session,
            title=f"{TEST_TITLE_PREFIX} unsubscribed",
            body="Сообщение только VK",
            channels=["vk"],
        )
        identity = await session.scalar(
            select(MessengerIdentity).where(
                MessengerIdentity.lead_id == lead_id,
                MessengerIdentity.channel == "vk",
            )
        )
        assert identity is not None
        identity.is_subscribed = False
        await session.commit()
        post_id = post.id

    clients = ApiInboxSendClients(
        telegram_bot=None,
        vk_client=FakeVkClient(),
        email_client=None,
        email_subject="",
        public_base_url="http://127.0.0.1:8000",
        email_from_email=None,
        email_from_name=None,
        email_signature_image_url=None,
    )
    async with async_session_maker() as session:
        stats = await run_due_followup_posts_once(session, clients=clients)
        stored = await session.get(FunnelFollowupPost, post_id)
        delivery = await session.scalar(
            select(FunnelFollowupDelivery).where(
                FunnelFollowupDelivery.followup_post_id == post_id
            )
        )

    assert stats.due == 1
    assert stats.completed == 1
    assert stored is not None
    assert stored.status == "completed"
    assert stored.total_deliveries == 1
    assert stored.skipped_deliveries == 1
    assert delivery is not None
    assert delivery.status == "skipped_unsubscribed"
