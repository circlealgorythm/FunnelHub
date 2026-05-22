from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.db.session import get_session
from funnelhub.services.getcourse_webhook import ingest_getcourse_webhook

router = APIRouter(prefix="/webhooks", tags=["webhooks"])


class GetCourseWebhookResponse(BaseModel):
    status: str
    lead_id: str
    created: bool


@router.api_route(
    "/getcourse",
    methods=["GET", "POST"],
    status_code=status.HTTP_200_OK,
    response_model=GetCourseWebhookResponse,
)
async def getcourse_webhook(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> GetCourseWebhookResponse:
    payload = await _extract_payload(request)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Webhook payload is empty.",
        )

    try:
        result = await ingest_getcourse_webhook(session, payload)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    await session.commit()
    return GetCourseWebhookResponse(
        status="ok",
        lead_id=str(result.lead_id),
        created=result.created,
    )


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
