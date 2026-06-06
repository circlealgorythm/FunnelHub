from __future__ import annotations

import logging
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.config import Settings, get_settings
from funnelhub.db.session import get_session
from funnelhub.services.bot_linking import build_join_url
from funnelhub.services.email_provider_webhooks import (
    load_unisender_go_webhook_payload,
    process_unisender_go_webhook,
    verify_unisender_go_webhook_auth,
)
from funnelhub.services.funnel_autostart import start_default_email_funnel_for_lead
from funnelhub.services.getcourse_webhook import ingest_getcourse_webhook
from funnelhub.services.ingestion_guard import (
    enforce_getcourse_ingestion_guard,
    strip_getcourse_webhook_secret_fields,
)
from funnelhub.services.lead_notifications import send_lead_application_notification
from funnelhub.vk_bot import handle_vk_message_allow, handle_vk_message_new

router = APIRouter(prefix="/webhooks", tags=["webhooks"])
logger = logging.getLogger(__name__)


class GetCourseWebhookResponse(BaseModel):
    status: str
    lead_id: str
    created: bool
    bot_link_token: str
    join_url: str


class VkCallbackEvent(BaseModel):
    type: str = Field(min_length=1)
    group_id: int | None = None
    secret: str | None = None
    object: dict[str, Any] = Field(default_factory=dict)


class EmailProviderWebhookResponse(BaseModel):
    status: str
    processed: int
    matched_messages: int
    updated_subscriptions: int
    skipped: int


class EmailProviderWebhookHealthResponse(BaseModel):
    status: str


@router.api_route(
    "/getcourse",
    methods=["GET", "POST"],
    status_code=status.HTTP_200_OK,
    response_model=GetCourseWebhookResponse,
)
async def getcourse_webhook(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> GetCourseWebhookResponse:
    payload = await _extract_payload(request)
    enforce_getcourse_ingestion_guard(
        request=request,
        payload=payload,
        settings=settings,
        endpoint="webhooks/getcourse",
    )
    payload = strip_getcourse_webhook_secret_fields(payload)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook payload is empty.",
        )

    try:
        result = await ingest_getcourse_webhook(session, payload)
        await start_default_email_funnel_for_lead(
            session=session,
            settings=settings,
            lead_id=result.lead_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    if "form_type" not in payload:
        await session.commit()
        await send_lead_application_notification(
            session=session,
            settings=settings,
            lead_id=result.lead_id,
            created=result.created,
            source="webhooks/getcourse",
        )
    await session.commit()
    return GetCourseWebhookResponse(
        status="ok",
        lead_id=str(result.lead_id),
        created=result.created,
        bot_link_token=result.bot_link_token,
        join_url=build_join_url(settings, result.bot_link_token),
    )


@router.get(
    "/email/unisender-go",
    status_code=status.HTTP_200_OK,
    response_model=EmailProviderWebhookHealthResponse,
)
async def unisender_go_email_webhook_health() -> EmailProviderWebhookHealthResponse:
    return EmailProviderWebhookHealthResponse(status="ok")


@router.post(
    "/email/unisender-go",
    status_code=status.HTTP_200_OK,
    response_model=EmailProviderWebhookResponse,
)
async def unisender_go_email_webhook(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> EmailProviderWebhookResponse:
    if not settings.email_unisender_go_api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Unisender Go webhook auth is not configured.",
        )

    raw_body = await request.body()
    try:
        payload = load_unisender_go_webhook_payload(raw_body)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

    received_auth = payload.get("auth")
    if not isinstance(received_auth, str) or not verify_unisender_go_webhook_auth(
        raw_body=raw_body,
        payload=payload,
        api_key=settings.email_unisender_go_api_key,
        received_auth=received_auth,
    ):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid Unisender Go webhook auth.",
        )

    try:
        result = await process_unisender_go_webhook(session, payload)
    except ValueError as exc:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    await session.commit()
    return EmailProviderWebhookResponse(
        status="ok",
        processed=result.processed,
        matched_messages=result.matched_messages,
        updated_subscriptions=result.updated_subscriptions,
        skipped=result.skipped,
    )


@router.post("/vk", status_code=status.HTTP_200_OK)
async def vk_callback_webhook(
    event: VkCallbackEvent,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> Response:
    validate_vk_secret(event.secret, settings)
    log_vk_callback_event(event)

    if event.type == "confirmation":
        if not settings.vk_confirmation_code:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="VK_CONFIRMATION_CODE is not configured.",
            )
        return Response(content=settings.vk_confirmation_code, media_type="text/plain")

    if event.type in {"message_new", "message_allow"}:
        try:
            event_payload = event.model_dump()
            if event.type == "message_allow":
                await handle_vk_message_allow(
                    session=session,
                    settings=settings,
                    event=event_payload,
                )
            else:
                await handle_vk_message_new(
                    session=session,
                    settings=settings,
                    event=event_payload,
                )
        except ValueError:
            await session.rollback()
            return Response(content="ok", media_type="text/plain")

        await session.commit()
        return Response(content="ok", media_type="text/plain")

    return Response(content="ok", media_type="text/plain")


def log_vk_callback_event(event: VkCallbackEvent) -> None:
    object_keys = sorted(event.object.keys())
    message = event.object.get("message")
    message_keys = sorted(message.keys()) if isinstance(message, dict) else []
    token_sources = [
        key
        for key in ("ref", "key", "access_key", "start", "payload")
        if key in event.object
    ]
    if isinstance(message, dict):
        token_sources.extend(
            f"message.{key}"
            for key in ("ref", "key", "access_key", "start", "payload", "text")
            if key in message
        )
    has_user_id = any(key in event.object for key in ("user_id", "from_id"))
    has_message_user_id = isinstance(message, dict) and any(
        key in message for key in ("user_id", "from_id")
    )
    logger.info(
        "VK callback received",
        extra={
            "vk_event_type": event.type,
            "vk_group_id": event.group_id,
            "vk_object_keys": object_keys,
            "vk_message_keys": message_keys,
            "vk_token_sources": token_sources,
            "vk_has_user_id": has_user_id or has_message_user_id,
        },
    )


def validate_vk_secret(secret: str | None, settings: Settings) -> None:
    if settings.vk_callback_secret and secret != settings.vk_callback_secret:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Invalid VK secret.")


async def _extract_payload(request: Request) -> dict[str, Any]:
    payload: dict[str, Any] = dict(request.query_params)

    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        body = await request.json()
        if isinstance(body, dict):
            payload.update(body)
    elif (
        "application/x-www-form-urlencoded" in content_type
        or "multipart/form-data" in content_type
    ):
        form = await request.form()
        payload.update(dict(form))

    return payload
