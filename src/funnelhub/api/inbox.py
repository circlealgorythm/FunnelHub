from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, Literal

from aiogram import Bot
from fastapi import APIRouter, Depends, File, HTTPException, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.config import Settings, get_settings
from funnelhub.db.models import Conversation
from funnelhub.db.session import get_session
from funnelhub.services.auth import require_admin_session
from funnelhub.services.inbox import (
    InboxConversationDetail,
    InboxConversationSummary,
    InboxMessageView,
    get_inbox_conversation_detail,
    list_inbox_conversations,
    send_inbox_reply,
)
from funnelhub.services.inbox_database import (
    DatabaseImportResult,
    DatabaseLeadDetail,
    DatabaseLeadList,
    DatabaseLeadSummary,
    export_database_leads_csv,
    get_database_lead_detail,
    import_database_leads_csv,
    list_database_leads,
)
from funnelhub.services.telegram_messaging import TelegramMessageClient
from funnelhub.services.vk_messaging import HttpVkMessageClient, VkMessageClient

router = APIRouter(
    prefix="/api/inbox",
    tags=["inbox"],
    dependencies=[Depends(require_admin_session)],
)
ConversationStatus = Literal["open", "needs_reply", "replied", "closed"]
SessionDep = Annotated[AsyncSession, Depends(get_session)]
SettingsDep = Annotated[Settings, Depends(get_settings)]
UploadCsvFile = Annotated[UploadFile, File(...)]


class InboxConversationResponse(BaseModel):
    id: uuid.UUID
    lead_id: uuid.UUID
    channel: str
    status: str
    last_message_at: datetime | None
    lead_name: str | None
    lead_status: str
    email: str | None
    phone: str | None
    identity_display_name: str | None
    identity_username: str | None
    is_subscribed: bool | None
    last_message_body: str | None
    last_message_direction: str | None
    unread_count: int


class InboxMessageResponse(BaseModel):
    id: uuid.UUID
    channel: str
    direction: str
    message_type: str
    body: str | None
    status: str
    created_at: datetime
    sent_at: datetime | None
    metadata: dict[str, object]


class InboxConversationDetailResponse(BaseModel):
    conversation: InboxConversationResponse
    messages: list[InboxMessageResponse]


class InboxReplyRequest(BaseModel):
    text: str = Field(min_length=1, max_length=4000)


class InboxStatusRequest(BaseModel):
    status: ConversationStatus


class DatabaseLeadResponse(BaseModel):
    id: uuid.UUID
    getcourse_user_id: int | None
    name: str | None
    email: str | None
    phone: str | None
    city: str | None
    country: str | None
    source: str | None
    status: str
    created_at: datetime
    updated_at: datetime
    telegram: str | None
    vk: str | None
    conversations_count: int
    messages_count: int


class DatabaseLeadListResponse(BaseModel):
    items: list[DatabaseLeadResponse]
    total: int
    limit: int
    offset: int


class DatabaseLeadDetailResponse(BaseModel):
    lead: DatabaseLeadResponse
    contacts: list[dict[str, object]]
    identities: list[dict[str, object]]
    funnel_states: list[dict[str, object]]
    recent_messages: list[dict[str, object]]
    raw_getcourse_data: dict[str, object]


class DatabaseImportResponse(BaseModel):
    batch_id: uuid.UUID
    total_rows: int
    processed_rows: int
    failed_rows: int
    created_rows: int
    updated_rows: int
    errors: list[dict[str, object]]


@dataclass
class ApiInboxSendClients:
    telegram_bot: TelegramMessageClient | None
    vk_client: VkMessageClient | None


@router.get("/conversations", response_model=list[InboxConversationResponse])
async def get_conversations(
    session: SessionDep,
    status: ConversationStatus | None = None,
) -> list[InboxConversationResponse]:
    summaries = await list_inbox_conversations(session, status=status)
    return [conversation_response(summary) for summary in summaries]


@router.get(
    "/conversations/{conversation_id}",
    response_model=InboxConversationDetailResponse,
)
async def get_conversation(
    conversation_id: uuid.UUID,
    session: SessionDep,
) -> InboxConversationDetailResponse:
    detail = await get_inbox_conversation_detail(session, conversation_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conversation_detail_response(detail)


@router.post(
    "/conversations/{conversation_id}/reply",
    response_model=InboxMessageResponse,
)
async def post_conversation_reply(
    conversation_id: uuid.UUID,
    request: InboxReplyRequest,
    session: SessionDep,
    settings: SettingsDep,
) -> InboxMessageResponse:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    telegram_bot: Bot | None = None
    try:
        telegram_client: TelegramMessageClient | None = None
        vk_client: VkMessageClient | None = None
        if conversation.channel == "telegram":
            if not settings.telegram_bot_token:
                raise HTTPException(status_code=503, detail="Telegram client is not configured.")
            telegram_bot = Bot(token=settings.telegram_bot_token)
            telegram_client = telegram_bot
        elif conversation.channel == "vk":
            if not settings.vk_group_access_token:
                raise HTTPException(status_code=503, detail="VK client is not configured.")
            vk_client = HttpVkMessageClient(
                access_token=settings.vk_group_access_token,
                api_version=settings.vk_api_version,
            )

        message = await send_inbox_reply(
            session=session,
            conversation_id=conversation_id,
            text=request.text,
            clients=ApiInboxSendClients(
                telegram_bot=telegram_client,
                vk_client=vk_client,
            ),
        )
        await session.commit()
        return message_response(
            InboxMessageView(
                id=message.id,
                channel=message.channel,
                direction=message.direction,
                message_type=message.message_type,
                body=message.body,
                status=message.status,
                created_at=message.created_at,
                sent_at=message.sent_at,
                metadata=message.metadata_ or {},
            )
        )
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        if telegram_bot is not None:
            await telegram_bot.session.close()


@router.patch(
    "/conversations/{conversation_id}",
    response_model=InboxConversationResponse,
)
async def patch_conversation_status(
    conversation_id: uuid.UUID,
    request: InboxStatusRequest,
    session: SessionDep,
) -> InboxConversationResponse:
    conversation = await session.get(Conversation, conversation_id)
    if conversation is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")

    conversation.status = request.status
    await session.commit()
    detail = await get_inbox_conversation_detail(session, conversation_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Conversation not found.")
    return conversation_response(detail.conversation)


@router.get("/database/leads", response_model=DatabaseLeadListResponse)
async def get_database_leads(
    session: SessionDep,
    q: str | None = None,
    limit: int = 50,
    offset: int = 0,
) -> DatabaseLeadListResponse:
    if limit < 1 or limit > 200:
        raise HTTPException(status_code=422, detail="Limit must be between 1 and 200.")
    if offset < 0:
        raise HTTPException(status_code=422, detail="Offset must be non-negative.")
    lead_list = await list_database_leads(session, query=q, limit=limit, offset=offset)
    return database_lead_list_response(lead_list)


@router.get("/database/leads/export")
async def export_database_leads(
    session: SessionDep,
    q: str | None = None,
) -> Response:
    content = await export_database_leads_csv(session, query=q)
    file_name = f"funnelhub-leads-{datetime.now().date().isoformat()}.csv"
    return Response(
        content=content.encode("utf-8-sig"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{file_name}"'},
    )


@router.post("/database/leads/import", response_model=DatabaseImportResponse)
async def import_database_leads(
    session: SessionDep,
    file: UploadCsvFile,
) -> DatabaseImportResponse:
    file_name = file.filename or "leads.csv"
    if not file_name.lower().endswith(".csv"):
        raise HTTPException(status_code=422, detail="Only CSV files are supported.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=422, detail="CSV file is empty.")
    try:
        result = await import_database_leads_csv(
            session,
            file_name=file_name,
            content=content,
        )
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await session.commit()
    return database_import_response(result)


@router.get("/database/leads/{lead_id}", response_model=DatabaseLeadDetailResponse)
async def get_database_lead(
    lead_id: uuid.UUID,
    session: SessionDep,
) -> DatabaseLeadDetailResponse:
    detail = await get_database_lead_detail(session, lead_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Lead not found.")
    return database_lead_detail_response(detail)


def conversation_response(summary: InboxConversationSummary) -> InboxConversationResponse:
    return InboxConversationResponse(
        id=summary.id,
        lead_id=summary.lead_id,
        channel=summary.channel,
        status=summary.status,
        last_message_at=summary.last_message_at,
        lead_name=summary.lead_name,
        lead_status=summary.lead_status,
        email=summary.email,
        phone=summary.phone,
        identity_display_name=summary.identity_display_name,
        identity_username=summary.identity_username,
        is_subscribed=summary.is_subscribed,
        last_message_body=summary.last_message_body,
        last_message_direction=summary.last_message_direction,
        unread_count=summary.unread_count,
    )


def message_response(message: InboxMessageView) -> InboxMessageResponse:
    return InboxMessageResponse(
        id=message.id,
        channel=message.channel,
        direction=message.direction,
        message_type=message.message_type,
        body=message.body,
        status=message.status,
        created_at=message.created_at,
        sent_at=message.sent_at,
        metadata=message.metadata,
    )


def conversation_detail_response(
    detail: InboxConversationDetail,
) -> InboxConversationDetailResponse:
    return InboxConversationDetailResponse(
        conversation=conversation_response(detail.conversation),
        messages=[message_response(message) for message in detail.messages],
    )


def database_lead_response(lead: DatabaseLeadSummary) -> DatabaseLeadResponse:
    return DatabaseLeadResponse(
        id=lead.id,
        getcourse_user_id=lead.getcourse_user_id,
        name=lead.name,
        email=lead.email,
        phone=lead.phone,
        city=lead.city,
        country=lead.country,
        source=lead.source,
        status=lead.status,
        created_at=lead.created_at,
        updated_at=lead.updated_at,
        telegram=lead.telegram,
        vk=lead.vk,
        conversations_count=lead.conversations_count,
        messages_count=lead.messages_count,
    )


def database_lead_list_response(lead_list: DatabaseLeadList) -> DatabaseLeadListResponse:
    return DatabaseLeadListResponse(
        items=[database_lead_response(item) for item in lead_list.items],
        total=lead_list.total,
        limit=lead_list.limit,
        offset=lead_list.offset,
    )


def database_lead_detail_response(detail: DatabaseLeadDetail) -> DatabaseLeadDetailResponse:
    return DatabaseLeadDetailResponse(
        lead=database_lead_response(detail.lead),
        contacts=detail.contacts,
        identities=detail.identities,
        funnel_states=detail.funnel_states,
        recent_messages=detail.recent_messages,
        raw_getcourse_data=detail.raw_getcourse_data,
    )


def database_import_response(result: DatabaseImportResult) -> DatabaseImportResponse:
    return DatabaseImportResponse(
        batch_id=result.batch_id,
        total_rows=result.total_rows,
        processed_rows=result.processed_rows,
        failed_rows=result.failed_rows,
        created_rows=result.created_rows,
        updated_rows=result.updated_rows,
        errors=result.errors,
    )
