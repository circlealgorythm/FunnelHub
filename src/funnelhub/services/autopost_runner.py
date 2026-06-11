from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol, cast

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.config import Settings
from funnelhub.db.models import Autopost, AutopostPublication
from funnelhub.services.telegram_messaging import TelegramMessageClient, extract_external_message_id

logger = logging.getLogger(__name__)


class AutopostVkClient(Protocol):
    async def publish_wall_post(
        self,
        *,
        owner_id: int,
        message: str,
    ) -> Any: ...


@dataclass(frozen=True)
class AutopostClients:
    telegram_bot: TelegramMessageClient | None
    vk_client: AutopostVkClient | None


@dataclass(frozen=True)
class AutopostRunStats:
    due: int = 0
    published: int = 0
    failed: int = 0
    partial_failed: int = 0


async def run_due_autoposts_once(
    session: AsyncSession,
    *,
    clients: AutopostClients,
    settings: Settings,
    limit: int = 25,
) -> AutopostRunStats:
    now = datetime.now(UTC)
    posts = list(
        (
            await session.scalars(
                select(Autopost)
                .where(
                    Autopost.status.in_(["queued", "scheduled", "partial_failed", "failed"]),
                    Autopost.scheduled_at <= now,
                )
                .order_by(Autopost.scheduled_at.asc(), Autopost.created_at.asc())
                .limit(limit)
            )
        ).all()
    )
    if not posts:
        return AutopostRunStats()

    stats = AutopostRunStats(due=len(posts))
    published_count = 0
    failed_count = 0
    partial_count = 0

    for post in posts:
        post.status = "publishing"
        await session.flush()

        publications = list(
            (
                await session.scalars(
                    select(AutopostPublication)
                    .where(
                        AutopostPublication.autopost_id == post.id,
                        AutopostPublication.status.in_(["pending", "failed"]),
                    )
                    .order_by(AutopostPublication.created_at.asc())
                )
            ).all()
        )

        if publications:
            for publication in publications:
                await publish_one_channel(
                    post=post,
                    publication=publication,
                    clients=clients,
                    settings=settings,
                )

        all_publications = list(
            (
                await session.scalars(
                    select(AutopostPublication).where(
                        AutopostPublication.autopost_id == post.id,
                    )
                )
            ).all()
        )
        published = [row for row in all_publications if row.status == "published"]
        failed = [row for row in all_publications if row.status == "failed"]

        if all_publications and len(published) == len(all_publications):
            post.status = "published"
            post.published_at = max(row.published_at for row in published if row.published_at)
            published_count += 1
        elif published and failed:
            post.status = "partial_failed"
            partial_count += 1
        else:
            post.status = "failed"
            failed_count += 1

        await session.flush()
        await session.commit()

    return AutopostRunStats(
        due=stats.due,
        published=published_count,
        failed=failed_count,
        partial_failed=partial_count,
    )


async def publish_one_channel(
    *,
    post: Autopost,
    publication: AutopostPublication,
    clients: AutopostClients,
    settings: Settings,
) -> None:
    now = datetime.now(UTC)
    publication.attempted_at = now
    publication.error = None
    publication.status = "publishing"

    try:
        if publication.channel == "telegram":
            external_id, payload = await publish_telegram_post(
                bot=clients.telegram_bot,
                chat_id=settings.autopost_telegram_chat_id,
                text=post.body,
            )
        elif publication.channel == "vk":
            external_id, payload = await publish_vk_post(
                client=clients.vk_client,
                owner_id=resolve_vk_owner_id(settings),
                text=post.body,
            )
        else:
            raise ValueError(f"Unsupported autopost channel: {publication.channel}.")
    except Exception as exc:
        publication.status = "failed"
        publication.error = str(exc)
        publication.payload = {}
        logger.warning(
            "Autopost %s failed in %s: %s",
            post.id,
            publication.channel,
            exc,
        )
        return

    publication.status = "published"
    publication.external_post_id = external_id
    publication.published_at = now
    publication.payload = payload


async def publish_telegram_post(
    *,
    bot: TelegramMessageClient | None,
    chat_id: str | None,
    text: str,
) -> tuple[str | None, dict[str, Any]]:
    if bot is None:
        raise ValueError("Telegram client is not configured.")
    if not chat_id:
        raise ValueError("AUTOPOST_TELEGRAM_CHAT_ID is not configured.")

    sent_message = await bot.send_message(chat_id=chat_id, text=text)
    return extract_external_message_id(sent_message), {"chat_id": chat_id}


async def publish_vk_post(
    *,
    client: AutopostVkClient | None,
    owner_id: int | None,
    text: str,
) -> tuple[str | None, dict[str, Any]]:
    if client is None:
        raise ValueError("VK client is not configured.")
    if owner_id is None:
        raise ValueError("AUTOPOST_VK_OWNER_ID or VK_GROUP_ID is not configured.")

    payload = cast(dict[str, Any], await client.publish_wall_post(owner_id=owner_id, message=text))
    return extract_vk_post_id(payload), payload


def resolve_vk_owner_id(settings: Settings) -> int | None:
    if settings.autopost_vk_owner_id is not None:
        return settings.autopost_vk_owner_id
    if settings.vk_group_id is not None:
        return -abs(settings.vk_group_id)
    return None


def extract_vk_post_id(payload: dict[str, Any]) -> str | None:
    response = payload.get("response")
    if isinstance(response, dict):
        post_id = response.get("post_id")
        if post_id is not None:
            return str(post_id)
    if isinstance(response, int | str):
        return str(response)
    return None
