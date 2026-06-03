from __future__ import annotations

import html
import logging
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.config import Settings, get_settings
from funnelhub.db.session import get_session
from funnelhub.services.bot_linking import (
    build_telegram_deep_link,
    build_vk_deep_link,
    get_active_bot_link_token,
    link_messenger_identity,
)
from funnelhub.services.funnel_autostart import start_default_funnel_for_lead
from funnelhub.services.funnel_engine import load_funnel_definition, run_due_funnel_step
from funnelhub.services.funnel_runner import MessengerFunnelStepSender
from funnelhub.services.getcourse_webhook import ingest_getcourse_webhook
from funnelhub.services.vk_messaging import HttpVkMessageClient
from funnelhub.services.vk_oauth import (
    build_vk_oauth_join_url,
    exchange_vk_oauth_code,
    parse_vk_oauth_state,
)

router = APIRouter(tags=["messenger-linking"])
logger = logging.getLogger(__name__)


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


@router.get("/join/getcourse", response_class=HTMLResponse)
async def getcourse_redirect_join_page(
    request: Request,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> HTMLResponse:
    payload = getcourse_redirect_payload(dict(request.query_params))
    if not payload:
        return render_getcourse_join_error()

    try:
        result = await ingest_getcourse_webhook(session, payload)
    except ValueError:
        await session.rollback()
        return render_getcourse_join_error()

    await session.commit()
    return render_join_page(settings=settings, token=result.bot_link_token)


@router.get("/join/{token}", response_class=HTMLResponse)
async def join_page(
    token: str,
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> HTMLResponse:
    bot_link_token = await get_active_bot_link_token(session, token)
    if bot_link_token is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Join token not found.")

    return render_join_page(settings=settings, token=token)


@router.get("/oauth/vk/callback", response_class=HTMLResponse)
async def vk_oauth_callback(
    session: Annotated[AsyncSession, Depends(get_session)],
    settings: Annotated[Settings, Depends(get_settings)],
    code: str | None = None,
    state: str | None = None,
    device_id: str | None = None,
    error: str | None = None,
) -> HTMLResponse:
    if error:
        return render_vk_oauth_error()
    if not code or not state:
        return render_vk_oauth_error()

    try:
        oauth_state = parse_vk_oauth_state(settings, state)
        vk_token = await exchange_vk_oauth_code(
            settings,
            code,
            code_verifier=oauth_state.code_verifier,
            device_id=device_id,
            state=state,
        )
        result = await link_messenger_identity(
            session=session,
            token=oauth_state.token,
            channel="vk",
            external_user_id=vk_token.user_id,
            username=None,
            display_name=None,
            raw_profile={
                "oauth": {
                    "user_id": vk_token.user_id,
                    "token_response_keys": sorted(vk_token.raw_payload.keys()),
                }
            },
            allow_relink=True,
        )
        await start_default_funnel_for_lead(
            session=session,
            settings=settings,
            lead_id=result.lead_id,
            messenger_channel="vk",
        )
        await send_first_due_vk_step(
            session=session,
            settings=settings,
            lead_id=result.lead_id,
        )
    except (ValueError, RuntimeError) as exc:
        logger.warning("VK OAuth callback failed: %s", exc)
        await session.rollback()
        return render_vk_oauth_error()

    await session.commit()
    return render_vk_oauth_success(settings)


def getcourse_redirect_payload(query_params: dict[str, str]) -> dict[str, str]:
    aliases = {
        "id": "gc_user_id",
        "user_id": "gc_user_id",
        "object_id": "gc_user_id",
        "mail": "email",
        "e_mail": "email",
        "fio": "name",
        "full_name": "name",
    }
    payload: dict[str, str] = {}
    for key, value in query_params.items():
        cleaned = clean_redirect_value(value)
        if cleaned is None:
            continue
        payload[aliases.get(key, key)] = cleaned
    return payload


def clean_redirect_value(value: Any) -> str | None:
    if value is None:
        return None
    cleaned = str(value).strip()
    if not cleaned:
        return None
    if cleaned.startswith("{") and cleaned.endswith("}"):
        return None
    return cleaned


def render_getcourse_join_error() -> HTMLResponse:
    return HTMLResponse(
        """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Спасибо за заявку</title>
  <style>
    body {
      margin: 0;
      min-height: 100vh;
      display: grid;
      place-items: center;
      font-family: Arial, sans-serif;
      background: #ffffff;
      color: #111827;
    }
    main {
      width: min(620px, calc(100% - 32px));
      text-align: center;
      padding: 32px 0;
    }
    h1 {
      margin: 0 0 18px;
      font-size: 32px;
      line-height: 1.2;
    }
    p {
      margin: 0 auto;
      max-width: 520px;
      font-size: 18px;
      line-height: 1.5;
    }
  </style>
</head>
<body>
  <main>
    <h1>Спасибо за вашу заявку!</h1>
    <p>
      Не удалось получить данные заявки для выдачи бонусов.
      Пожалуйста, вернитесь на предыдущую страницу и отправьте форму еще раз.
    </p>
  </main>
</body>
</html>""",
        status_code=status.HTTP_400_BAD_REQUEST,
    )


async def send_first_due_vk_step(
    session: AsyncSession,
    settings: Settings,
    lead_id: Any,
) -> None:
    if not settings.vk_group_access_token:
        return

    definition = load_funnel_definition(settings.default_funnel_path)
    state = await start_default_funnel_for_lead(
        session=session,
        settings=settings,
        lead_id=lead_id,
        messenger_channel="vk",
    )
    vk_client = HttpVkMessageClient(
        access_token=settings.vk_group_access_token,
        api_version=settings.vk_api_version,
    )
    sender = MessengerFunnelStepSender(
        session=session,
        telegram_bot=None,
        vk_client=vk_client,
    )
    await run_due_funnel_step(
        session=session,
        state=state,
        definition=definition,
        sender=sender,
    )


def render_vk_oauth_error() -> HTMLResponse:
    return HTMLResponse(
        """<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Вконтакте</title>
</head>
<body>
  <main style="font-family: Arial, sans-serif; max-width: 560px; margin: 40px auto;">
    <h1>Не удалось подключить Вконтакте</h1>
    <p>Пожалуйста, вернитесь на страницу спасибо и попробуйте нажать кнопку Вконтакте еще раз.</p>
  </main>
</body>
</html>""",
        status_code=status.HTTP_400_BAD_REQUEST,
    )


def render_vk_oauth_success(settings: Settings) -> HTMLResponse:
    vk_url = (
        f"https://vk.me/{settings.vk_group_screen_name.strip().lstrip('@')}"
        if settings.vk_group_screen_name
        else "https://vk.com"
    )
    escaped_vk_url = html.escape(vk_url)
    return HTMLResponse(
        f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="refresh" content="0;url={escaped_vk_url}">
  <title>Вконтакте подключен</title>
  <script>
    window.location.replace({vk_url!r});
  </script>
</head>
<body>
  <main style="font-family: Arial, sans-serif; max-width: 560px; margin: 40px auto;">
    <h1>Вконтакте подключен</h1>
    <p>Первое сообщение уже отправляется. Сейчас откроется диалог сообщества во Вконтакте.</p>
    <p><a href="{escaped_vk_url}">Открыть Вконтакте</a></p>
  </main>
</body>
</html>"""
    )


def render_join_page(settings: Settings, token: str) -> HTMLResponse:
    telegram_link = build_telegram_deep_link(settings, token)
    escaped_token = html.escape(token)
    telegram_markup = (
        f'<a class="button telegram" href="{html.escape(telegram_link)}">Телеграм</a>'
        if telegram_link is not None
        else '<span class="button disabled">Телеграм</span>'
    )
    vk_link = build_vk_oauth_join_url(settings, token) or build_vk_deep_link(settings, token)
    vk_markup = (
        f'<a class="button vk" href="{html.escape(vk_link)}">Вконтакте</a>'
        if vk_link is not None
        else '<span class="button disabled">Вконтакте</span>'
    )
    return HTMLResponse(
        f"""<!doctype html>
<html lang="ru">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Спасибо за заявку</title>
  <style>
    :root {{
      --paper: #f8f0df;
      --paper-light: #fffaf0;
      --ink: #21160e;
      --muted: #6f5941;
      --gold: #b07a35;
      --gold-dark: #7d4f1e;
      --maroon: #7b2445;
      --line: rgba(176, 122, 53, 0.28);
      --shadow: 0 22px 60px rgba(78, 48, 20, 0.13);
    }}

    * {{
      box-sizing: border-box;
    }}

    body {{
      margin: 0;
      min-height: 100vh;
      font-family: Georgia, "Times New Roman", serif;
      color: var(--ink);
      background:
        radial-gradient(circle at 72% 18%, rgba(176, 122, 53, 0.16), transparent 28%),
        radial-gradient(circle at 18% 74%, rgba(123, 36, 69, 0.1), transparent 26%),
        linear-gradient(180deg, var(--paper-light) 0%, var(--paper) 58%, #f3e5c9 100%);
    }}

    body::before {{
      content: "";
      position: fixed;
      inset: 0;
      pointer-events: none;
      opacity: 0.24;
      background-image:
        linear-gradient(rgba(125, 79, 30, 0.08) 1px, transparent 1px),
        linear-gradient(90deg, rgba(125, 79, 30, 0.06) 1px, transparent 1px);
      background-size: 72px 72px;
      mask-image: linear-gradient(to bottom, black, transparent 82%);
    }}

    main {{
      position: relative;
      width: min(1080px, calc(100% - 32px));
      margin: 0 auto;
      padding: 54px 0 64px;
    }}

    .hero {{
      display: grid;
      grid-template-columns: minmax(0, 1.08fr) minmax(300px, 0.92fr);
      gap: 42px;
      align-items: center;
      min-height: min(720px, calc(100vh - 80px));
    }}

    .eyebrow {{
      margin: 0 0 18px;
      color: var(--gold-dark);
      font-family: "Trebuchet MS", Verdana, sans-serif;
      font-size: 12px;
      font-weight: 700;
      line-height: 1.4;
      text-transform: uppercase;
    }}

    h1 {{
      max-width: 560px;
      margin: 0 0 22px;
      font-size: 52px;
      line-height: 1.04;
      font-weight: 500;
    }}

    p {{
      margin: 0;
      color: var(--muted);
      font-size: 19px;
      line-height: 1.58;
    }}

    strong {{
      font-weight: 700;
      color: var(--ink);
    }}

    .lead {{
      max-width: 600px;
      margin-bottom: 24px;
    }}

    .gift-list {{
      display: grid;
      gap: 12px;
      max-width: 620px;
      margin: 28px 0 0;
    }}

    .gift {{
      display: grid;
      grid-template-columns: 42px 1fr;
      gap: 14px;
      align-items: start;
      padding: 16px 18px;
      border: 1px solid var(--line);
      border-radius: 8px;
      background: rgba(255, 250, 240, 0.74);
      box-shadow: 0 12px 34px rgba(91, 57, 20, 0.06);
    }}

    .gift-mark {{
      display: grid;
      place-items: center;
      width: 42px;
      height: 42px;
      border: 1px solid rgba(176, 122, 53, 0.45);
      border-radius: 50%;
      color: var(--gold-dark);
      font-family: "Trebuchet MS", Verdana, sans-serif;
      font-size: 12px;
      font-weight: 700;
    }}

    .gift h2 {{
      margin: 0 0 6px;
      font-size: 20px;
      line-height: 1.25;
      font-weight: 600;
    }}

    .gift p {{
      font-size: 15px;
      line-height: 1.45;
    }}

    .visual {{
      position: relative;
      min-height: 460px;
      display: grid;
      place-items: center;
    }}

    .next-card {{
      position: relative;
      width: min(390px, 100%);
      padding: 34px 30px;
      border: 1px solid rgba(176, 122, 53, 0.32);
      border-radius: 8px;
      background:
        linear-gradient(180deg, rgba(255, 250, 240, 0.92), rgba(244, 225, 190, 0.7)),
        radial-gradient(circle at 84% 16%, rgba(176, 122, 53, 0.16), transparent 32%);
      box-shadow: var(--shadow);
      overflow: hidden;
    }}

    .next-card::before {{
      content: "";
      position: absolute;
      inset: 18px;
      border: 1px solid rgba(176, 122, 53, 0.18);
      border-radius: 6px;
      pointer-events: none;
    }}

    .next-card::after {{
      content: "";
      position: absolute;
      right: -42px;
      top: -42px;
      width: 150px;
      height: 150px;
      border-radius: 50%;
      background: radial-gradient(circle, rgba(255, 218, 132, 0.62), transparent 66%);
    }}

    .next-label {{
      position: relative;
      margin: 0 0 14px;
      color: var(--gold-dark);
      font-family: "Trebuchet MS", Verdana, sans-serif;
      font-size: 12px;
      font-weight: 700;
      line-height: 1.4;
      text-transform: uppercase;
    }}

    .next-card h2 {{
      position: relative;
      margin: 0 0 24px;
      max-width: 270px;
      font-size: 31px;
      line-height: 1.08;
      font-weight: 500;
    }}

    .next-steps {{
      position: relative;
      display: grid;
      gap: 14px;
      margin: 0;
      padding: 0;
      list-style: none;
    }}

    .next-step {{
      display: grid;
      grid-template-columns: 34px 1fr;
      gap: 12px;
      align-items: start;
      padding: 0 0 14px;
      border-bottom: 1px solid rgba(176, 122, 53, 0.18);
    }}

    .next-step:last-child {{
      padding-bottom: 0;
      border-bottom: 0;
    }}

    .next-number {{
      display: grid;
      place-items: center;
      width: 34px;
      height: 34px;
      border-radius: 50%;
      background: rgba(176, 122, 53, 0.13);
      color: var(--gold-dark);
      font-family: "Trebuchet MS", Verdana, sans-serif;
      font-size: 11px;
      font-weight: 700;
    }}

    .next-step strong {{
      display: block;
      margin-bottom: 4px;
      font-size: 18px;
      line-height: 1.25;
    }}

    .next-step span {{
      color: var(--muted);
      font-size: 15px;
      line-height: 1.45;
    }}

    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 14px;
      align-items: center;
      margin-top: 32px;
    }}

    .button {{
      display: grid;
      place-items: center;
      min-width: 190px;
      min-height: 58px;
      padding: 0 24px;
      border-radius: 8px;
      color: #fff;
      text-align: center;
      text-decoration: none;
      font-family: "Trebuchet MS", Verdana, sans-serif;
      font-weight: 700;
      font-size: 16px;
      transition: transform 160ms ease, box-shadow 160ms ease, filter 160ms ease;
    }}

    .button:hover {{
      transform: translateY(-2px);
      filter: saturate(1.05);
    }}

    .telegram {{
      background: #5aa6d6;
      box-shadow: 0 14px 26px rgba(90, 166, 214, 0.28);
    }}

    .vk {{
      background: #315f7b;
      box-shadow: 0 14px 26px rgba(49, 95, 123, 0.24);
    }}

    .disabled {{
      color: #6b7280;
      background: #e5e7eb;
    }}

    .note {{
      max-width: 560px;
      margin-top: 18px;
      color: var(--gold-dark);
      font-size: 15px;
      line-height: 1.5;
    }}

    code {{
      position: absolute;
      width: 1px;
      height: 1px;
      overflow: hidden;
      clip: rect(0, 0, 0, 0);
      white-space: nowrap;
    }}

    @media (max-width: 840px) {{
      main {{
        width: min(620px, calc(100% - 28px));
        padding: 34px 0 46px;
      }}

      .hero {{
        grid-template-columns: 1fr;
        gap: 28px;
        min-height: auto;
      }}

      h1 {{
        font-size: 38px;
      }}

      p {{
        font-size: 17px;
      }}

      .visual {{
        min-height: auto;
        order: -1;
      }}

      .next-card {{
        width: 100%;
      }}

      .actions {{
        display: grid;
      }}

      .button {{
        width: 100%;
      }}
    }}

    @media (max-width: 460px) {{
      h1 {{
        font-size: 32px;
      }}

      .gift {{
        grid-template-columns: 1fr;
      }}
    }}
  </style>
</head>
<body>
  <main>
    <section class="hero" aria-labelledby="thanks-title">
      <div>
        <p class="eyebrow">Заявка принята</p>
        <h1 id="thanks-title">Спасибо за вашу заявку!</h1>
        <p class="lead">
          Айсу Кам свяжется с вами по заявке на консультацию.
          А пока заберите подготовленные материалы в удобном мессенджере.
        </p>

        <div class="gift-list" aria-label="Подарки после заявки">
          <article class="gift">
            <span class="gift-mark">01</span>
            <div>
              <h2>Медитация на соединение с Родом и Предками</h2>
              <p>Мягкая практика для внутренней опоры и получения поддержки Рода.</p>
            </div>
          </article>
          <article class="gift">
            <span class="gift-mark">02</span>
            <div>
              <h2>Три видео-шага для знакомства с методом</h2>
              <p>
                Тонкоплановые работы, духовное целительство и методы улучшения
                финансового состояния.
              </p>
            </div>
          </article>
        </div>

        <div class="actions" aria-label="Выберите мессенджер">
          {telegram_markup}
          {vk_markup}
        </div>
        <p class="note">
          Подпишитесь, чтобы получить бонусы и не пропустить сообщение по консультации.
        </p>
      </div>

      <div class="visual">
        <div class="next-card">
          <p class="next-label">Что дальше</p>
          <h2>Материалы уже ждут вас</h2>
          <ol class="next-steps">
            <li class="next-step">
              <span class="next-number">01</span>
              <span>
                <strong>Выберите мессенджер</strong>
                Нажмите Telegram или Вконтакте на этой странице.
              </span>
            </li>
            <li class="next-step">
              <span class="next-number">02</span>
              <span>
                <strong>Получите подарки</strong>
                Бот отправит медитацию и три видео-шага после подписки.
              </span>
            </li>
            <li class="next-step">
              <span class="next-number">03</span>
              <span>
                <strong>Дождитесь сообщения</strong>
                Мы напишем по заявке на консультацию и подскажем следующий шаг.
              </span>
            </li>
          </ol>
        </div>
      </div>
    </section>
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
    settings: Annotated[Settings, Depends(get_settings)],
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
        if payload.channel in {"telegram", "vk"}:
            await start_default_funnel_for_lead(
                session=session,
                settings=settings,
                lead_id=result.lead_id,
                messenger_channel=payload.channel,
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
