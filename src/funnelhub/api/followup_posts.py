from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.db.session import get_session
from funnelhub.services.auth import require_admin_session
from funnelhub.services.followup_posts import (
    FollowupDetail,
    cancel_followup_post,
    create_followup_post,
    delete_followup_post,
    get_followup_detail,
    list_followup_posts,
    preview_followup_recipients,
    update_followup_post,
)

router = APIRouter(
    prefix="/api/inbox/followup-posts",
    tags=["followup-posts"],
    dependencies=[Depends(require_admin_session)],
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class FollowupPostCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    body: str = Field(min_length=1)
    channels: list[str] = Field(min_length=1)
    scheduled_at: datetime | None = None
    delivery_mode: Literal["queued", "immediate"] = "queued"
    metadata: dict[str, Any] | None = None


class FollowupDeliveryResponse(BaseModel):
    id: uuid.UUID
    lead_id: uuid.UUID
    lead_name: str | None
    channel: str
    status: str
    available_at: datetime
    external_message_id: str | None
    attempted_at: datetime | None
    sent_at: datetime | None
    error: str | None


class FollowupPostResponse(BaseModel):
    id: uuid.UUID
    title: str
    body: str
    channels: list[str]
    status: str
    delivery_mode: str
    source_type: str
    source_autopost_id: uuid.UUID | None
    scheduled_at: datetime
    completed_at: datetime | None
    total_deliveries: int
    sent_deliveries: int
    failed_deliveries: int
    skipped_deliveries: int
    created_at: datetime
    updated_at: datetime
    deliveries: list[FollowupDeliveryResponse] = []


class FollowupPostListResponse(BaseModel):
    items: list[FollowupPostResponse]
    total: int
    limit: int
    offset: int


class FollowupRecipientPreviewResponse(BaseModel):
    total: int
    by_channel: dict[str, int]


@router.post("", response_model=FollowupPostResponse)
async def create_new_followup_post(
    request: FollowupPostCreateRequest,
    session: SessionDep,
) -> FollowupPostResponse:
    try:
        post = await create_followup_post(
            session=session,
            title=request.title,
            body=request.body,
            channels=request.channels,
            scheduled_at=request.scheduled_at,
            delivery_mode=request.delivery_mode,
            metadata=request.metadata,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await session.commit()
    detail = await get_followup_detail(session, post.id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Follow-up post not found")
    return serialize_followup_detail(detail)


@router.get("", response_model=FollowupPostListResponse)
async def get_followup_post_list(
    session: SessionDep,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
) -> FollowupPostListResponse:
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="Limit must be between 1 and 100")
    if offset < 0:
        raise HTTPException(status_code=422, detail="Offset must be non-negative")

    posts, total = await list_followup_posts(
        session,
        limit=limit,
        offset=offset,
        status=status.strip() if status else None,
    )
    return FollowupPostListResponse(
        items=[serialize_followup_summary(post) for post in posts],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/recipient-preview", response_model=FollowupRecipientPreviewResponse)
async def get_followup_recipient_preview(
    session: SessionDep,
    channels: Annotated[list[str] | None, Query()] = None,
) -> FollowupRecipientPreviewResponse:
    try:
        preview = await preview_followup_recipients(session, channels or ["telegram", "vk"])
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return FollowupRecipientPreviewResponse(total=preview.total, by_channel=preview.by_channel)


@router.get("/{post_id}", response_model=FollowupPostResponse)
async def get_followup_post(
    post_id: uuid.UUID,
    session: SessionDep,
) -> FollowupPostResponse:
    detail = await get_followup_detail(session, post_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Follow-up post not found")
    return serialize_followup_detail(detail)


@router.put("/{post_id}", response_model=FollowupPostResponse)
async def update_existing_followup_post(
    post_id: uuid.UUID,
    request: FollowupPostCreateRequest,
    session: SessionDep,
) -> FollowupPostResponse:
    try:
        post = await update_followup_post(
            session=session,
            post_id=post_id,
            title=request.title,
            body=request.body,
            channels=request.channels,
            scheduled_at=request.scheduled_at,
            delivery_mode=request.delivery_mode,
        )
    except ValueError as exc:
        error_detail = str(exc)
        status_code = 404 if error_detail == "Follow-up post not found." else 409
        if error_detail in {
            "Title is required.",
            "Post body is required.",
            "At least one follow-up channel is required.",
        } or error_detail.startswith("Unsupported follow-up"):
            status_code = 422
        raise HTTPException(status_code=status_code, detail=error_detail) from exc

    await session.commit()
    detail = await get_followup_detail(session, post.id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Follow-up post not found")
    return serialize_followup_detail(detail)


@router.patch("/{post_id}/cancel", response_model=FollowupPostResponse)
async def cancel_existing_followup_post(
    post_id: uuid.UUID,
    session: SessionDep,
) -> FollowupPostResponse:
    try:
        post = await cancel_followup_post(session, post_id)
    except ValueError as exc:
        error_detail = str(exc)
        raise HTTPException(
            status_code=404 if error_detail == "Follow-up post not found." else 409,
            detail=error_detail,
        ) from exc

    await session.commit()
    detail = await get_followup_detail(session, post.id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Follow-up post not found")
    return serialize_followup_detail(detail)


@router.delete("/{post_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_existing_followup_post(
    post_id: uuid.UUID,
    session: SessionDep,
) -> Response:
    try:
        await delete_followup_post(session, post_id)
    except ValueError as exc:
        error_detail = str(exc)
        raise HTTPException(
            status_code=404 if error_detail == "Follow-up post not found." else 409,
            detail=error_detail,
        ) from exc

    await session.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


def serialize_followup_summary(post: Any) -> FollowupPostResponse:
    return FollowupPostResponse(
        id=post.id,
        title=post.title,
        body=post.body,
        channels=post.channels,
        status=post.status,
        delivery_mode=post.delivery_mode,
        source_type=post.source_type,
        source_autopost_id=post.source_autopost_id,
        scheduled_at=post.scheduled_at,
        completed_at=post.completed_at,
        total_deliveries=post.total_deliveries,
        sent_deliveries=post.sent_deliveries,
        failed_deliveries=post.failed_deliveries,
        skipped_deliveries=post.skipped_deliveries,
        created_at=post.created_at,
        updated_at=post.updated_at,
        deliveries=[],
    )


def serialize_followup_detail(detail: FollowupDetail) -> FollowupPostResponse:
    response = serialize_followup_summary(detail.post)
    response.deliveries = [
        FollowupDeliveryResponse(
            id=delivery.id,
            lead_id=delivery.lead_id,
            lead_name=delivery.lead_name,
            channel=delivery.channel,
            status=delivery.status,
            available_at=delivery.available_at,
            external_message_id=delivery.external_message_id,
            attempted_at=delivery.attempted_at,
            sent_at=delivery.sent_at,
            error=delivery.error,
        )
        for delivery in detail.deliveries
    ]
    return response
