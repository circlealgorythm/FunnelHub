from __future__ import annotations

import uuid
from datetime import datetime
from typing import Annotated, Any

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.config import get_settings
from funnelhub.db.session import get_session
from funnelhub.services.auth import require_admin_session
from funnelhub.services.autopost_media import get_autopost_image_metadata, save_autopost_image
from funnelhub.services.autopost_runner import resolve_vk_owner_id
from funnelhub.services.autoposts import (
    AutopostDetail,
    cancel_autopost,
    create_autopost,
    get_autopost_detail,
    list_autoposts,
)

router = APIRouter(
    prefix="/api/inbox/autoposts",
    tags=["autoposts"],
    dependencies=[Depends(require_admin_session)],
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]


class AutopostCreateRequest(BaseModel):
    title: str = Field(min_length=1, max_length=512)
    body: str = Field(min_length=1)
    channels: list[str] = Field(min_length=1)
    scheduled_at: datetime | None = None
    source_type: str = "manual"
    source_url: str | None = None
    dedupe_key: str | None = None
    metadata: dict[str, Any] | None = None


class AutopostPublicationResponse(BaseModel):
    id: uuid.UUID
    channel: str
    status: str
    external_post_id: str | None
    external_post_url: str | None = None
    attempted_at: datetime | None
    published_at: datetime | None
    error: str | None


class AutopostResponse(BaseModel):
    id: uuid.UUID
    title: str
    body: str
    channels: list[str]
    status: str
    source_type: str
    source_url: str | None
    scheduled_at: datetime
    published_at: datetime | None
    created_at: datetime
    updated_at: datetime
    has_image: bool = False
    image_file_name: str | None = None
    publications: list[AutopostPublicationResponse] = []


class AutopostListResponse(BaseModel):
    items: list[AutopostResponse]
    total: int
    limit: int
    offset: int


@router.post("", response_model=AutopostResponse)
async def create_new_autopost(
    request: AutopostCreateRequest,
    session: SessionDep,
) -> AutopostResponse:
    settings = get_settings()
    try:
        autopost = await create_autopost(
            session=session,
            title=request.title,
            body=request.body,
            channels=request.channels,
            scheduled_at=request.scheduled_at,
            source_type=request.source_type,
            source_url=request.source_url,
            dedupe_key=request.dedupe_key,
            metadata=request.metadata,
            followup_marker=settings.autopost_followup_marker,
            strip_marker_for_followup=settings.autopost_followup_strip_marker,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await session.commit()
    detail = await get_autopost_detail(session, autopost.id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Autopost not found")
    return serialize_autopost_detail(detail)


@router.post("/with-media", response_model=AutopostResponse)
async def create_new_autopost_with_media(
    session: SessionDep,
    title: Annotated[str, Form()],
    body: Annotated[str, Form()],
    channels: Annotated[list[str], Form()],
    scheduled_at: Annotated[str | None, Form()] = None,
    source_type: Annotated[str, Form()] = "manual",
    source_url: Annotated[str | None, Form()] = None,
    image: Annotated[UploadFile | None, File()] = None,
) -> AutopostResponse:
    settings = get_settings()
    metadata: dict[str, Any] = {}
    if image is not None and image.filename:
        try:
            metadata = await save_autopost_image(image, settings)
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    try:
        autopost = await create_autopost(
            session=session,
            title=title,
            body=body,
            channels=channels,
            scheduled_at=parse_optional_datetime(scheduled_at),
            source_type=source_type,
            source_url=source_url,
            metadata=metadata,
            followup_marker=settings.autopost_followup_marker,
            strip_marker_for_followup=settings.autopost_followup_strip_marker,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await session.commit()
    detail = await get_autopost_detail(session, autopost.id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Autopost not found")
    return serialize_autopost_detail(detail)


@router.get("", response_model=AutopostListResponse)
async def get_autopost_list(
    session: SessionDep,
    limit: int = 50,
    offset: int = 0,
    status: str | None = None,
) -> AutopostListResponse:
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="Limit must be between 1 and 100")
    if offset < 0:
        raise HTTPException(status_code=422, detail="Offset must be non-negative")

    autoposts, total = await list_autoposts(
        session,
        limit=limit,
        offset=offset,
        status=status.strip() if status else None,
    )
    return AutopostListResponse(
        items=[serialize_autopost_summary(autopost) for autopost in autoposts],
        total=total,
        limit=limit,
        offset=offset,
    )


@router.get("/{autopost_id}", response_model=AutopostResponse)
async def get_autopost(
    autopost_id: uuid.UUID,
    session: SessionDep,
) -> AutopostResponse:
    detail = await get_autopost_detail(session, autopost_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Autopost not found")
    return serialize_autopost_detail(detail)


@router.patch("/{autopost_id}/cancel", response_model=AutopostResponse)
async def cancel_existing_autopost(
    autopost_id: uuid.UUID,
    session: SessionDep,
) -> AutopostResponse:
    try:
        autopost = await cancel_autopost(session, autopost_id)
    except ValueError as exc:
        error_detail = str(exc)
        raise HTTPException(
            status_code=404 if error_detail == "Autopost not found." else 409,
            detail=error_detail,
        ) from exc

    await session.commit()
    detail = await get_autopost_detail(session, autopost.id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Autopost not found")
    return serialize_autopost_detail(detail)


def serialize_autopost_summary(autopost: Any) -> AutopostResponse:
    image = get_autopost_image_metadata(autopost)
    return AutopostResponse(
        id=autopost.id,
        title=autopost.title,
        body=autopost.body,
        channels=autopost.channels,
        status=autopost.status,
        source_type=autopost.source_type,
        source_url=autopost.source_url,
        scheduled_at=autopost.scheduled_at,
        published_at=autopost.published_at,
        created_at=autopost.created_at,
        updated_at=autopost.updated_at,
        has_image=image is not None,
        image_file_name=(
            str(image["original_file_name"])
            if image and isinstance(image.get("original_file_name"), str)
            else None
        ),
        publications=[],
    )


def serialize_autopost_detail(detail: AutopostDetail) -> AutopostResponse:
    autopost = detail.autopost
    response = serialize_autopost_summary(autopost)
    settings = get_settings()
    response.publications = [
        AutopostPublicationResponse(
            id=publication.id,
            channel=publication.channel,
            status=publication.status,
            external_post_id=publication.external_post_id,
            external_post_url=build_external_post_url(
                channel=publication.channel,
                external_post_id=publication.external_post_id,
                vk_owner_id=resolve_vk_owner_id(settings),
            ),
            attempted_at=publication.attempted_at,
            published_at=publication.published_at,
            error=publication.error,
        )
        for publication in detail.publications
    ]
    return response


def build_external_post_url(
    *,
    channel: str,
    external_post_id: str | None,
    vk_owner_id: int | None,
) -> str | None:
    if not external_post_id:
        return None
    if channel == "vk" and vk_owner_id is not None:
        return f"https://vk.com/wall{vk_owner_id}_{external_post_id}"
    return None


def parse_optional_datetime(value: str | None) -> datetime | None:
    if value is None or not value.strip():
        return None
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
