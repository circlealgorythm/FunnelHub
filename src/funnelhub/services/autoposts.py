from __future__ import annotations

import hashlib
import uuid
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from funnelhub.db.models import Autopost, AutopostPublication
from funnelhub.services.followup_posts import (
    SUPPORTED_FOLLOWUP_CHANNELS,
    create_followup_post,
    strip_followup_marker,
)

SUPPORTED_AUTOPOST_CHANNELS = ("telegram", "vk")
SUPPORTED_SOURCE_TYPES = ("manual", "youtube", "telegram", "vk", "other")


@dataclass(frozen=True)
class AutopostPublicationView:
    id: uuid.UUID
    channel: str
    status: str
    external_post_id: str | None
    attempted_at: datetime | None
    published_at: datetime | None
    error: str | None


@dataclass(frozen=True)
class AutopostDetail:
    autopost: Autopost
    publications: list[AutopostPublicationView]


async def create_autopost(
    session: AsyncSession,
    *,
    title: str,
    body: str,
    channels: Sequence[str],
    scheduled_at: datetime | None = None,
    source_type: str = "manual",
    source_url: str | None = None,
    dedupe_key: str | None = None,
    metadata: dict[str, Any] | None = None,
    followup_marker: str | None = None,
    strip_marker_for_followup: bool = True,
) -> Autopost:
    clean_title = title.strip()
    clean_body = body.strip()
    clean_channels = normalize_channels(channels)
    clean_source_type = source_type.strip() or "manual"
    clean_source_url = source_url.strip() if source_url and source_url.strip() else None

    if not clean_title:
        raise ValueError("Title is required.")
    if not clean_body:
        raise ValueError("Post body is required.")
    if clean_source_type not in SUPPORTED_SOURCE_TYPES:
        raise ValueError(f"Unsupported source type: {clean_source_type}.")

    publish_at = normalize_schedule(scheduled_at)
    status = "queued" if publish_at <= datetime.now(UTC) else "scheduled"
    key = dedupe_key.strip() if dedupe_key and dedupe_key.strip() else build_dedupe_key(
        body=clean_body,
        channels=clean_channels,
        scheduled_at=publish_at,
        source_type=clean_source_type,
        source_url=clean_source_url,
    )
    existing = await session.scalar(select(Autopost).where(Autopost.dedupe_key == key))
    if existing is not None:
        await create_followup_from_marked_autopost(
            session,
            existing,
            marker=followup_marker,
            strip_marker=strip_marker_for_followup,
        )
        return existing

    autopost = Autopost(
        id=uuid.uuid4(),
        title=clean_title,
        body=clean_body,
        channels=list(clean_channels),
        status=status,
        source_type=clean_source_type,
        source_url=clean_source_url,
        dedupe_key=key,
        scheduled_at=publish_at,
        metadata_=metadata or {},
    )
    session.add(autopost)
    await session.flush()

    for channel in clean_channels:
        session.add(
            AutopostPublication(
                id=uuid.uuid4(),
                autopost_id=autopost.id,
                channel=channel,
                status="pending",
                payload={},
            )
        )
    await session.flush()
    await create_followup_from_marked_autopost(
        session,
        autopost,
        marker=followup_marker,
        strip_marker=strip_marker_for_followup,
    )
    await session.refresh(autopost)
    return autopost


async def list_autoposts(
    session: AsyncSession,
    *,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
) -> tuple[list[Autopost], int]:
    stmt = select(Autopost).order_by(Autopost.scheduled_at.desc()).limit(limit).offset(offset)
    count_stmt = select(func.count()).select_from(Autopost)
    if status:
        stmt = stmt.where(Autopost.status == status)
        count_stmt = count_stmt.where(Autopost.status == status)
    items = list((await session.scalars(stmt)).all())
    total = int(await session.scalar(count_stmt) or 0)
    return items, total


async def get_autopost_detail(
    session: AsyncSession,
    autopost_id: uuid.UUID,
) -> AutopostDetail | None:
    autopost = await session.get(Autopost, autopost_id)
    if autopost is None:
        return None
    rows = (
        await session.scalars(
            select(AutopostPublication)
            .where(AutopostPublication.autopost_id == autopost_id)
            .order_by(AutopostPublication.created_at.asc())
        )
    ).all()
    return AutopostDetail(
        autopost=autopost,
        publications=[
            AutopostPublicationView(
                id=row.id,
                channel=row.channel,
                status=row.status,
                external_post_id=row.external_post_id,
                attempted_at=row.attempted_at,
                published_at=row.published_at,
                error=row.error,
            )
            for row in rows
        ],
    )


async def cancel_autopost(session: AsyncSession, autopost_id: uuid.UUID) -> Autopost:
    autopost = await session.get(Autopost, autopost_id)
    if autopost is None:
        raise ValueError("Autopost not found.")
    if autopost.status in {"published", "publishing"}:
        raise ValueError("Published autopost cannot be cancelled.")
    autopost.status = "cancelled"
    publications = (
        await session.scalars(
            select(AutopostPublication).where(AutopostPublication.autopost_id == autopost_id)
        )
    ).all()
    for publication in publications:
        if publication.status == "pending":
            publication.status = "cancelled"
    await session.flush()
    return autopost


def normalize_channels(channels: Sequence[str]) -> tuple[str, ...]:
    result: list[str] = []
    for channel in channels:
        clean_channel = channel.strip()
        if not clean_channel:
            continue
        if clean_channel not in SUPPORTED_AUTOPOST_CHANNELS:
            raise ValueError(f"Unsupported autopost channel: {clean_channel}.")
        if clean_channel not in result:
            result.append(clean_channel)
    if not result:
        raise ValueError("At least one autopost channel is required.")
    return tuple(result)


def normalize_schedule(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def build_dedupe_key(
    *,
    body: str,
    channels: Sequence[str],
    scheduled_at: datetime,
    source_type: str,
    source_url: str | None,
) -> str:
    channel_part = ",".join(sorted(channels))
    if source_url:
        basis = f"source:{source_type}:{source_url.strip().lower()}:{channel_part}"
    else:
        scheduled_minute = scheduled_at.replace(second=0, microsecond=0).isoformat()
        basis = f"manual:{body}:{channel_part}:{scheduled_minute}"
    digest = hashlib.sha256(basis.encode("utf-8")).hexdigest()
    return f"autopost:{digest}"


async def create_followup_from_marked_autopost(
    session: AsyncSession,
    autopost: Autopost,
    *,
    marker: str | None,
    strip_marker: bool,
) -> None:
    clean_marker = marker.strip() if marker and marker.strip() else None
    if clean_marker is None:
        return
    if clean_marker.casefold() not in autopost.body.casefold():
        return

    body = (
        strip_followup_marker(autopost.body, clean_marker)
        if strip_marker
        else autopost.body.strip()
    )
    if not body:
        body = autopost.body.strip()
    followup_channels = [
        channel for channel in autopost.channels if channel in SUPPORTED_FOLLOWUP_CHANNELS
    ]
    if not followup_channels:
        followup_channels = list(SUPPORTED_FOLLOWUP_CHANNELS)

    await create_followup_post(
        session,
        title=autopost.title,
        body=body,
        channels=followup_channels,
        scheduled_at=autopost.scheduled_at,
        source_type="autopost",
        source_autopost_id=autopost.id,
        metadata={
            "source": "public_autopost_marker",
            "source_autopost_id": str(autopost.id),
            "marker": clean_marker,
            "marker_stripped": strip_marker,
        },
    )


def mark_metadata(autopost: Autopost, key: str, value: Any) -> None:
    metadata = dict(autopost.metadata_ or {})
    metadata[key] = value
    autopost.metadata_ = metadata
    flag_modified(autopost, "metadata_")
