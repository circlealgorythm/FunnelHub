import uuid
from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.db.session import get_session
from funnelhub.services.auth import require_admin_session
from funnelhub.services.broadcasts import create_broadcast, get_broadcast_detail, list_broadcasts

router = APIRouter(
    prefix="/api/inbox/broadcasts",
    tags=["broadcasts"],
    dependencies=[Depends(require_admin_session)],
)

SessionDep = Annotated[AsyncSession, Depends(get_session)]

class BroadcastCreateRequest(BaseModel):
    segment_query: str | None = None
    channels: list[str] = Field(min_length=1)
    message_text: str = Field(min_length=1)

class BroadcastResponse(BaseModel):
    id: uuid.UUID
    segment_query: str | None
    channels: list[str]
    status: str
    total_leads: int
    processed_leads: int
    failed_leads: int
    skipped_leads: int
    created_at: datetime
    updated_at: datetime

class BroadcastListResponse(BaseModel):
    items: list[BroadcastResponse]
    total: int
    limit: int
    offset: int


@router.post("", response_model=BroadcastResponse)
async def create_new_broadcast(
    request: BroadcastCreateRequest,
    session: SessionDep,
) -> BroadcastResponse:
    valid_channels = {"telegram", "vk", "email"}
    for ch in request.channels:
        if ch not in valid_channels:
            raise HTTPException(status_code=422, detail=f"Invalid channel: {ch}")
            
    broadcast = await create_broadcast(
        session=session,
        segment_query=request.segment_query,
        channels=request.channels,
        message_text=request.message_text,
    )
    return BroadcastResponse(
        id=broadcast.id,
        segment_query=broadcast.segment_query,
        channels=broadcast.channels,
        status=broadcast.status,
        total_leads=broadcast.total_leads,
        processed_leads=broadcast.processed_leads,
        failed_leads=broadcast.failed_leads,
        skipped_leads=broadcast.skipped_leads,
        created_at=broadcast.created_at,
        updated_at=broadcast.updated_at,
    )

@router.get("", response_model=BroadcastListResponse)
async def get_broadcast_list(
    session: SessionDep,
    limit: int = 50,
    offset: int = 0,
) -> BroadcastListResponse:
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="Limit must be between 1 and 100")
        
    broadcasts, total = await list_broadcasts(session, limit=limit, offset=offset)
    return BroadcastListResponse(
        items=[
            BroadcastResponse(
                id=b.id,
                segment_query=b.segment_query,
                channels=b.channels,
                status=b.status,
                total_leads=b.total_leads,
                processed_leads=b.processed_leads,
                failed_leads=b.failed_leads,
                skipped_leads=b.skipped_leads,
                created_at=b.created_at,
                updated_at=b.updated_at,
            ) for b in broadcasts
        ],
        total=total,
        limit=limit,
        offset=offset,
    )

@router.get("/{broadcast_id}", response_model=BroadcastResponse)
async def get_broadcast(
    broadcast_id: uuid.UUID,
    session: SessionDep,
) -> BroadcastResponse:
    b = await get_broadcast_detail(session, broadcast_id)
    if not b:
        raise HTTPException(status_code=404, detail="Broadcast not found")
        
    return BroadcastResponse(
        id=b.id,
        segment_query=b.segment_query,
        channels=b.channels,
        status=b.status,
        total_leads=b.total_leads,
        processed_leads=b.processed_leads,
        failed_leads=b.failed_leads,
        skipped_leads=b.skipped_leads,
        created_at=b.created_at,
        updated_at=b.updated_at,
    )

class BroadcastTargetResponse(BaseModel):
    id: uuid.UUID
    lead_id: uuid.UUID
    lead_name: str | None
    lead_contact: str | None
    status: str
    error: str | None

class BroadcastTargetListResponse(BaseModel):
    items: list[BroadcastTargetResponse]
    total: int

@router.get("/{broadcast_id}/targets", response_model=BroadcastTargetListResponse)
async def get_broadcast_targets(
    broadcast_id: uuid.UUID,
    session: SessionDep,
    limit: int = 100,
    offset: int = 0,
) -> BroadcastTargetListResponse:
    from sqlalchemy import func, select

    from funnelhub.db.models import BroadcastTarget, Lead

    count_stmt = select(func.count()).select_from(BroadcastTarget).where(BroadcastTarget.broadcast_id == broadcast_id)
    total = int(await session.scalar(count_stmt) or 0)

    stmt = select(BroadcastTarget, Lead).join(Lead).where(BroadcastTarget.broadcast_id == broadcast_id).order_by(BroadcastTarget.created_at.asc()).limit(limit).offset(offset)
    rows = (await session.execute(stmt)).all()

    items = []
    for target, lead in rows:
        items.append(BroadcastTargetResponse(
            id=target.id,
            lead_id=target.lead_id,
            lead_name=lead.name or lead.first_name,
            lead_contact=lead.email or lead.phone or lead.telegram,
            status=target.status,
            error=target.error,
        ))

    return BroadcastTargetListResponse(items=items, total=total)
