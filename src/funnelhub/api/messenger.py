from __future__ import annotations

import html
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.config import Settings, get_settings
from funnelhub.db.session import get_session
from funnelhub.services.bot_linking import (
    build_telegram_deep_link,
    get_active_bot_link_token,
    link_messenger_identity,
)

router = APIRouter(tags=["messenger-linking"])


class MessengerLinkRequest(BaseModel):
    token: str = Field(min_length=16, max_length=255)
    channel: Literal["telegram", "vk"]
    external_user_id: str = Field(min_length=1, max_length=255)
    username: str | None = Field(default=None, max_length=255)
    display_name: str | None = Field(default=None, max_length=512)
    raw_profile: dict[str, Any] = Field(default_factory=dict)


class MessengerLinkResponse(BaseModel):
    status: str
    lead_id: str
    identity_id: str
    created: bool


@router.get("/join/{token}", response_class=HTMLResponse)
async def join_page(
    token: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> HTMLResponse:
    bot_link_token = await get_active_bot_link_token(session, token)
    if bot_link_token is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Join token not found.")

    telegram_link = build_telegram_deep_link(settings, token)
    escaped_token = html.escape(token)
    telegram_markup = (
        f'<a class="button" href="{html.escape(telegram_link)}">Telegram</a>'
        if telegram_link is not None
        else '<span class="button disabled">Telegram</span>'
    )
    return HTMLResponse(
        f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>FunnelHub</title>
  <style>
    body {{
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      font-family: Arial, sans-serif;
      background: #f5f2ec;
      color: #1f2933;
    }}
    main {{
      width: min(420px, calc(100% - 32px));
      padding: 28px;
      border: 1px solid #ddd5c8;
      background: #fffaf2;
    }}
    h1 {{
      margin: 0 0 18px;
      font-size: 28px;
      line-height: 1.1;
      font-weight: 700;
    }}
    .actions {{
      display: grid;
      gap: 10px;
    }}
    .button {{
      display: block;
      padding: 14px 16px;
      border: 1px solid #1f2933;
      color: #fff;
      background: #1f2933;
      text-align: center;
      text-decoration: none;
      font-weight: 700;
    }}
    .disabled {{
      color: #6b7280;
      background: #e5e7eb;
      border-color: #d1d5db;
    }}
    code {{
      display: block;
      margin-top: 16px;
      word-break: break-all;
      font-size: 12px;
      color: #4b5563;
    }}
  </style>
</head>
<body>
  <main>
    <h1>Выберите канал</h1>
    <div class="actions">{telegram_markup}</div>
    <code>{escaped_token}</code>
  </main>
</body>
</html>"""
    )


@router.post(
    "/api/messenger/link",
    status_code=status.HTTP_200_OK,
    response_model=MessengerLinkResponse,
)
async def link_messenger(
    payload: MessengerLinkRequest,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> MessengerLinkResponse:
    try:
        result = await link_messenger_identity(
            session=session,
            token=payload.token,
            channel=payload.channel,
            external_user_id=payload.external_user_id,
            username=payload.username,
            display_name=payload.display_name,
            raw_profile=payload.raw_profile,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(exc),
        ) from exc

    await session.commit()
    return MessengerLinkResponse(
        status="ok",
        lead_id=str(result.lead_id),
        identity_id=str(result.identity_id),
        created=result.created,
    )
