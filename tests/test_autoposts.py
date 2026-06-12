from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete, select

from funnelhub.config import Settings, get_settings
from funnelhub.db.base import Base
from funnelhub.db.models import (
    Autopost,
    AutopostPublication,
    FunnelFollowupDelivery,
    FunnelFollowupPost,
    FunnelState,
    Lead,
    MessengerIdentity,
)
from funnelhub.db.session import async_session_maker, engine
from funnelhub.main import app
from funnelhub.services.auth import hash_password
from funnelhub.services.autopost_runner import (
    AutopostClients,
    run_due_autoposts_once,
)
from funnelhub.services.autoposts import create_autopost

TEST_TITLE_PREFIX = "Autopost pytest"
TEST_FOLLOWUP_GC_ID = 987658000


class FakeTelegramMessage:
    message_id = 501


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


class FakeVkWallClient:
    def __init__(self) -> None:
        self.calls: list[tuple[int, str]] = []

    async def publish_wall_post(
        self,
        *,
        owner_id: int,
        message: str,
    ) -> dict[str, Any]:
        self.calls.append((owner_id, message))
        return {"response": {"post_id": 777}}


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
        followup_post_ids = set(
            await session.scalars(
                select(FunnelFollowupPost.id).where(
                    FunnelFollowupPost.title.startswith(TEST_TITLE_PREFIX)
                )
            )
        )
        if followup_post_ids:
            await session.execute(
                delete(FunnelFollowupDelivery).where(
                    FunnelFollowupDelivery.followup_post_id.in_(followup_post_ids)
                )
            )
            await session.execute(
                delete(FunnelFollowupPost).where(FunnelFollowupPost.id.in_(followup_post_ids))
            )

        post_ids = set(
            await session.scalars(
                select(Autopost.id).where(Autopost.title.startswith(TEST_TITLE_PREFIX))
            )
        )
        if post_ids:
            await session.execute(
                delete(AutopostPublication).where(AutopostPublication.autopost_id.in_(post_ids))
            )
            await session.execute(delete(Autopost).where(Autopost.id.in_(post_ids)))
        lead_ids = set(
            await session.scalars(
                select(Lead.id).where(Lead.getcourse_user_id == TEST_FOLLOWUP_GC_ID)
            )
        )
        if lead_ids:
            await session.execute(delete(Lead).where(Lead.id.in_(lead_ids)))
        await session.commit()


def configure_auth(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("INBOX_ADMIN_USERNAME", "aisu")
    monkeypatch.setenv(
        "INBOX_ADMIN_PASSWORD_HASH",
        hash_password("secret", salt=b"1234567890123456"),
    )
    monkeypatch.setenv("INBOX_SESSION_SECRET", "test-session-secret")
    monkeypatch.setenv("AUTOPOST_FOLLOWUP_MARKER", "#followup")
    monkeypatch.setenv("AUTOPOST_FOLLOWUP_STRIP_MARKER", "true")
    get_settings.cache_clear()


async def create_completed_followup_lead() -> None:
    async with async_session_maker() as session:
        lead = Lead(
            id=uuid.uuid4(),
            getcourse_user_id=TEST_FOLLOWUP_GC_ID,
            full_name="Autopost Followup Lead",
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
                status="completed",
                current_step_key="day_18",
                completed_at=datetime.now(UTC) - timedelta(days=1),
                metadata_={},
            )
        )
        for channel in ("telegram", "vk"):
            session.add(
                MessengerIdentity(
                    id=uuid.uuid4(),
                    lead_id=lead.id,
                    channel=channel,
                    external_user_id=f"autopost-followup-{channel}",
                    is_subscribed=True,
                    raw_profile={},
                )
            )
        await session.commit()


async def test_autopost_api_creates_lists_dedupes_and_cancels(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_auth(monkeypatch)
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
            payload = {
                "title": f"{TEST_TITLE_PREFIX} API",
                "body": "Запланированный пост",
                "channels": ["telegram", "telegram", "vk"],
                "scheduled_at": schedule.isoformat(),
                "source_type": "youtube",
                "source_url": "https://youtube.test/video-1",
            }
            first_response = await client.post("/api/inbox/autoposts", json=payload)
            second_response = await client.post("/api/inbox/autoposts", json=payload)
            blank_response = await client.post(
                "/api/inbox/autoposts",
                json={**payload, "body": "   "},
            )
            list_response = await client.get("/api/inbox/autoposts")
    finally:
        get_settings.cache_clear()

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    assert blank_response.status_code == 422
    created = first_response.json()
    duplicated = second_response.json()
    assert duplicated["id"] == created["id"]
    assert created["channels"] == ["telegram", "vk"]
    assert created["status"] == "scheduled"
    assert {item["channel"] for item in created["publications"]} == {"telegram", "vk"}
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
            detail_response = await client.get(f"/api/inbox/autoposts/{created['id']}")
            cancel_response = await client.patch(
                f"/api/inbox/autoposts/{created['id']}/cancel"
            )
    finally:
        get_settings.cache_clear()

    assert detail_response.status_code == 200
    assert cancel_response.status_code == 200
    cancelled = cancel_response.json()
    assert cancelled["status"] == "cancelled"
    assert {item["status"] for item in cancelled["publications"]} == {"cancelled"}


async def test_marked_autopost_creates_one_followup_post(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    configure_auth(monkeypatch)
    await create_completed_followup_lead()
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
            payload = {
                "title": f"{TEST_TITLE_PREFIX} marked followup",
                "body": "Текст для публичного поста\n#followup",
                "channels": ["telegram", "vk"],
                "scheduled_at": schedule.isoformat(),
            }
            first_response = await client.post("/api/inbox/autoposts", json=payload)
            second_response = await client.post("/api/inbox/autoposts", json=payload)
    finally:
        get_settings.cache_clear()

    assert first_response.status_code == 200
    assert second_response.status_code == 200
    autopost_id = first_response.json()["id"]
    assert second_response.json()["id"] == autopost_id

    async with async_session_maker() as session:
        followups = list(
            (
                await session.scalars(
                    select(FunnelFollowupPost).where(
                        FunnelFollowupPost.source_autopost_id == uuid.UUID(autopost_id)
                    )
                )
            ).all()
        )
        assert len(followups) == 1
        followup = followups[0]
        deliveries = list(
            (
                await session.scalars(
                    select(FunnelFollowupDelivery).where(
                        FunnelFollowupDelivery.followup_post_id == followup.id
                    )
                )
            ).all()
        )

    assert followup.title == f"{TEST_TITLE_PREFIX} marked followup"
    assert followup.body == "Текст для публичного поста"
    assert followup.channels == ["telegram", "vk"]
    assert followup.status == "scheduled"
    assert followup.source_type == "autopost"
    assert len(deliveries) == 2
    assert {delivery.channel for delivery in deliveries} == {"telegram", "vk"}


async def test_autopost_runner_publishes_to_telegram_and_vk_once() -> None:
    bot = FakeTelegramBot()
    vk_client = FakeVkWallClient()

    async with async_session_maker() as session:
        post = await create_autopost(
            session,
            title=f"{TEST_TITLE_PREFIX} runner",
            body="Текст для каналов",
            channels=["telegram", "vk"],
        )
        await session.commit()
        post_id = post.id

    settings = Settings(
        AUTOPOST_TELEGRAM_CHAT_ID="@channel",
        VK_GROUP_ID=12345,
    )
    async with async_session_maker() as session:
        stats = await run_due_autoposts_once(
            session,
            clients=AutopostClients(telegram_bot=bot, vk_client=vk_client),
            settings=settings,
        )
        second_stats = await run_due_autoposts_once(
            session,
            clients=AutopostClients(telegram_bot=bot, vk_client=vk_client),
            settings=settings,
        )

    assert stats.due == 1
    assert stats.published == 1
    assert second_stats.due == 0
    assert bot.calls == [("@channel", "Текст для каналов")]
    assert vk_client.calls == [(-12345, "Текст для каналов")]

    async with async_session_maker() as session:
        stored = await session.get(Autopost, post_id)
        publications = list(
            (
                await session.scalars(
                    select(AutopostPublication).where(
                        AutopostPublication.autopost_id == post_id
                    )
                )
            ).all()
        )

    assert stored is not None
    assert stored.status == "published"
    assert {item.status for item in publications} == {"published"}
    assert {item.external_post_id for item in publications} == {"501", "777"}


async def test_autopost_runner_marks_missing_channel_config_failed() -> None:
    async with async_session_maker() as session:
        post = await create_autopost(
            session,
            title=f"{TEST_TITLE_PREFIX} missing config",
            body="Текст без настроенного канала",
            channels=["telegram"],
        )
        await session.commit()
        post_id = post.id

    async with async_session_maker() as session:
        stats = await run_due_autoposts_once(
            session,
            clients=AutopostClients(telegram_bot=None, vk_client=None),
            settings=Settings(),
        )

    assert stats.due == 1
    assert stats.failed == 1
    async with async_session_maker() as session:
        stored = await session.get(Autopost, post_id)
        publication = await session.scalar(
            select(AutopostPublication).where(AutopostPublication.autopost_id == post_id)
        )

    assert stored is not None
    assert stored.status == "failed"
    assert publication is not None
    assert publication.status == "failed"
    assert publication.error is not None
    assert "Telegram client is not configured" in publication.error
