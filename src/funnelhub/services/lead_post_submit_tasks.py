from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.config import Settings
from funnelhub.db.models import LeadPostSubmitTask
from funnelhub.services.email_messaging import EmailProviderClient
from funnelhub.services.getcourse_api import enrich_lead_from_getcourse_api
from funnelhub.services.lead_notifications import send_lead_application_notification

logger = logging.getLogger(__name__)

TASK_GETCOURSE_PROFILE_ENRICHMENT = "getcourse_profile_enrichment"
TASK_LEAD_APPLICATION_NOTIFICATION = "lead_application_notification"


@dataclass(frozen=True)
class LeadPostSubmitTaskStats:
    due: int = 0
    completed: int = 0
    failed: int = 0


async def enqueue_lead_post_submit_tasks(
    *,
    session: AsyncSession,
    settings: Settings,
    lead_id: uuid.UUID,
    created: bool,
    source: str,
    notify_admin: bool,
) -> None:
    if settings.getcourse_api_base_url and settings.getcourse_api_key:
        await enqueue_lead_post_submit_task(
            session=session,
            lead_id=lead_id,
            task_type=TASK_GETCOURSE_PROFILE_ENRICHMENT,
            dedupe_key=f"{TASK_GETCOURSE_PROFILE_ENRICHMENT}:{lead_id}",
        )

    if notify_admin and settings.lead_notification_email_to:
        await enqueue_lead_post_submit_task(
            session=session,
            lead_id=lead_id,
            task_type=TASK_LEAD_APPLICATION_NOTIFICATION,
            payload={"created": created, "source": source},
            max_attempts=3,
        )


async def enqueue_lead_post_submit_task(
    *,
    session: AsyncSession,
    lead_id: uuid.UUID,
    task_type: str,
    payload: dict[str, Any] | None = None,
    dedupe_key: str | None = None,
    max_attempts: int = 5,
) -> LeadPostSubmitTask:
    now = datetime.now(UTC)
    if dedupe_key is not None:
        existing = await session.scalar(
            select(LeadPostSubmitTask).where(LeadPostSubmitTask.dedupe_key == dedupe_key)
        )
        if existing is not None:
            if existing.status != "completed":
                existing.status = "pending"
                existing.not_before = now
                existing.error = None
                existing.attempts = 0
                existing.payload = payload or existing.payload or {}
                existing.max_attempts = max(existing.max_attempts, max_attempts)
                await session.flush()
            return existing

    task = LeadPostSubmitTask(
        id=uuid.uuid4(),
        lead_id=lead_id,
        task_type=task_type,
        status="pending",
        attempts=0,
        max_attempts=max_attempts,
        not_before=now,
        dedupe_key=dedupe_key,
        payload=payload or {},
    )
    session.add(task)
    await session.flush()
    return task


async def run_due_lead_post_submit_tasks_once(
    session: AsyncSession,
    *,
    settings: Settings,
    email_client: EmailProviderClient | None,
    limit: int = 25,
) -> LeadPostSubmitTaskStats:
    now = datetime.now(UTC)
    tasks = list(
        (
            await session.scalars(
                select(LeadPostSubmitTask)
                .where(
                    LeadPostSubmitTask.status.in_(["pending", "failed"]),
                    LeadPostSubmitTask.not_before <= now,
                    LeadPostSubmitTask.attempts < LeadPostSubmitTask.max_attempts,
                )
                .order_by(
                    LeadPostSubmitTask.not_before.asc(),
                    LeadPostSubmitTask.created_at.asc(),
                )
                .limit(limit)
            )
        ).all()
    )
    if not tasks:
        return LeadPostSubmitTaskStats()

    completed = 0
    failed = 0
    for task in tasks:
        task.status = "processing"
        task.attempts += 1
        task.error = None
        await session.flush()

        try:
            await process_lead_post_submit_task(
                session=session,
                settings=settings,
                task=task,
                email_client=email_client,
            )
        except Exception as exc:
            failed += 1
            task.status = "failed"
            task.error = str(exc)
            if task.attempts < task.max_attempts:
                task.not_before = datetime.now(UTC) + retry_delay(task.attempts)
            logger.warning(
                "Lead post-submit task %s failed for lead %s: %s",
                task.task_type,
                task.lead_id,
                exc,
            )
        else:
            completed += 1
            task.status = "completed"
            task.processed_at = datetime.now(UTC)
            task.error = None

        await session.flush()
        await session.commit()

    return LeadPostSubmitTaskStats(due=len(tasks), completed=completed, failed=failed)


async def process_lead_post_submit_task(
    *,
    session: AsyncSession,
    settings: Settings,
    task: LeadPostSubmitTask,
    email_client: EmailProviderClient | None,
) -> None:
    if task.task_type == TASK_GETCOURSE_PROFILE_ENRICHMENT:
        result = await enrich_lead_from_getcourse_api(
            session=session,
            settings=settings,
            lead_id=task.lead_id,
        )
        if result.updated or not result.attempted or result.reason in {
            "lead_not_found",
            "no_supported_filter",
        }:
            return
        raise RuntimeError(result.reason or "getcourse_profile_enrichment_failed")

    if task.task_type == TASK_LEAD_APPLICATION_NOTIFICATION:
        await send_lead_application_notification(
            session=session,
            settings=settings,
            lead_id=task.lead_id,
            created=bool(task.payload.get("created")),
            source=str(task.payload.get("source") or "post_submit_task"),
            client=email_client,
        )
        return

    raise ValueError(f"Unsupported lead post-submit task type: {task.task_type}.")


def retry_delay(attempts: int) -> timedelta:
    seconds = min(30 * (2 ** max(attempts - 1, 0)), 15 * 60)
    return timedelta(seconds=seconds)
