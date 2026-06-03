from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import HTMLResponse
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.db.session import get_session
from funnelhub.services.email_messaging import unsubscribe_email_by_token

router = APIRouter(prefix="/email", tags=["email"])


@router.get("/unsubscribe/{token}", response_class=HTMLResponse)
async def unsubscribe_email(
    token: str,
    session: Annotated[AsyncSession, Depends(get_session)],
) -> HTMLResponse:
    if len(token) < 16:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email subscription was not found.",
        )

    subscription = await unsubscribe_email_by_token(session, token)
    if subscription is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Email subscription was not found.",
        )

    await session.commit()
    return HTMLResponse(
        """
        <!doctype html>
        <html lang="ru">
          <head>
            <meta charset="utf-8">
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <title>Вы отписаны</title>
            <style>
              body {
                margin: 0;
                min-height: 100vh;
                display: grid;
                place-items: center;
                font-family: Arial, sans-serif;
                background: #f8f4ec;
                color: #2e261d;
              }
              main {
                width: min(90vw, 520px);
                padding: 32px;
                background: #fffaf1;
                border: 1px solid #e2d4bd;
                border-radius: 8px;
              }
              h1 { margin: 0 0 12px; font-size: 28px; }
              p { margin: 0; line-height: 1.5; }
            </style>
          </head>
          <body>
            <main>
              <h1>Вы отписаны от email-рассылки</h1>
              <p>Мы больше не будем отправлять письма на этот адрес.</p>
            </main>
          </body>
        </html>
        """
    )
