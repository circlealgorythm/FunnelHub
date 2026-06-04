from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from html import escape
from typing import Any, Protocol, cast
from urllib.parse import quote

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.config import Settings
from funnelhub.db.models import EmailSubscription, Event, Message


class EmailProviderClient(Protocol):
    async def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        text: str,
        html: str | None = None,
        from_email: str | None = None,
        from_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EmailProviderSendResult: ...


@dataclass(frozen=True)
class EmailProviderSendResult:
    external_message_id: str | None = None
    raw_response: dict[str, Any] | None = None


class DebugEmailProviderClient:
    async def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        text: str,
        html: str | None = None,
        from_email: str | None = None,
        from_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EmailProviderSendResult:
        return EmailProviderSendResult(
            external_message_id=f"debug-{secrets.token_hex(8)}",
            raw_response={
                "provider": "debug",
                "to_email": to_email,
                "subject": subject,
            },
        )


class UnisenderGoEmailProviderClient:
    def __init__(
        self,
        *,
        api_key: str,
        api_url: str,
        default_from_email: str | None = None,
        default_from_name: str | None = None,
        default_reply_to_email: str | None = None,
        default_reply_to_name: str | None = None,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self._api_key = api_key
        self._api_url = api_url
        self._default_from_email = default_from_email
        self._default_from_name = default_from_name
        self._default_reply_to_email = default_reply_to_email
        self._default_reply_to_name = default_reply_to_name
        self._http_client = http_client

    async def send_email(
        self,
        *,
        to_email: str,
        subject: str,
        text: str,
        html: str | None = None,
        from_email: str | None = None,
        from_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> EmailProviderSendResult:
        sender_email = from_email or self._default_from_email
        if not sender_email:
            raise ValueError("EMAIL_FROM_EMAIL is required for Unisender Go sends.")

        payload = build_unisender_go_payload(
            to_email=to_email,
            subject=subject,
            text=text,
            html=html,
            from_email=sender_email,
            from_name=from_name or self._default_from_name,
            reply_to_email=self._default_reply_to_email or sender_email,
            reply_to_name=self._default_reply_to_name or from_name or self._default_from_name,
            metadata=metadata or {},
        )
        response = await self._post_payload(payload)
        response_data = parse_unisender_go_response(response)
        failed_emails = response_data.get("failed_emails")
        if isinstance(failed_emails, list) and failed_emails:
            raise RuntimeError(f"Unisender Go rejected email: {failed_emails!r}")

        return EmailProviderSendResult(
            external_message_id=extract_unisender_go_message_id(response_data),
            raw_response={"provider": "unisender_go", "response": response_data},
        )

    async def _post_payload(self, payload: dict[str, Any]) -> httpx.Response:
        headers = {"Accept": "application/json", "X-API-KEY": self._api_key}
        if self._http_client is not None:
            return await self._http_client.post(self._api_url, json=payload, headers=headers)

        async with httpx.AsyncClient(timeout=20.0) as client:
            return await client.post(self._api_url, json=payload, headers=headers)


@dataclass(frozen=True)
class EmailSendResult:
    message_id: uuid.UUID
    external_message_id: str | None


def build_email_provider_client(settings: Settings) -> EmailProviderClient | None:
    if settings.email_provider == "debug":
        return DebugEmailProviderClient()
    if settings.email_provider == "unisender_go":
        if not settings.email_unisender_go_api_key:
            raise ValueError("EMAIL_UNISENDER_GO_API_KEY is required.")
        return UnisenderGoEmailProviderClient(
            api_key=settings.email_unisender_go_api_key,
            api_url=settings.email_unisender_go_api_url,
            default_from_email=settings.email_from_email,
            default_from_name=settings.email_from_name,
            default_reply_to_email=settings.email_reply_to_email or settings.email_from_email,
            default_reply_to_name=settings.email_reply_to_name or settings.email_from_name,
        )
    if settings.email_provider == "disabled":
        return None
    raise ValueError(f"Unsupported EMAIL_PROVIDER: {settings.email_provider}")


async def send_email_text_message(
    *,
    session: AsyncSession,
    client: EmailProviderClient,
    lead_id: uuid.UUID,
    subject: str,
    text: str,
    public_base_url: str,
    from_email: str | None = None,
    from_name: str | None = None,
    signature_image_url: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> EmailSendResult:
    subscription = await get_subscribed_email_subscription(session, lead_id)
    if subscription is None:
        raise ValueError("Lead has no subscribed email subscription.")

    await ensure_email_unsubscribe_token(session, subscription)
    unsubscribe_url = build_unsubscribe_url(public_base_url, subscription.unsubscribe_token)
    buttons = extract_email_buttons(metadata or {})
    body = append_unsubscribe_footer(
        append_email_button_links(text, buttons),
        unsubscribe_url,
    )
    html_body = build_html_email_body(
        text=text,
        buttons=buttons,
        unsubscribe_url=unsubscribe_url,
        signature_image_url=signature_image_url,
    )
    message_metadata = {
        **(metadata or {}),
        "subject": subject,
        "to_email": subscription.email,
        "unsubscribe_url": unsubscribe_url,
    }
    now = datetime.now(UTC)
    message = Message(
        id=uuid.uuid4(),
        lead_id=lead_id,
        channel="email",
        direction="outbound",
        message_type="text",
        body=body,
        status="created",
        metadata_=message_metadata,
    )
    session.add(message)
    await session.flush()

    try:
        sent_message = await client.send_email(
            to_email=subscription.email,
            subject=subject,
            text=body,
            html=html_body,
            from_email=from_email,
            from_name=from_name,
            metadata={
                "lead_id": str(lead_id),
                "message_id": str(message.id),
                "unsubscribe_url": unsubscribe_url,
                **(metadata or {}),
            },
        )
    except Exception as exc:
        message.status = "failed"
        message.metadata_ = {**message_metadata, "error": str(exc)}
        await session.flush()
        raise

    message.external_message_id = sent_message.external_message_id
    message.status = "sent"
    message.sent_at = now
    if sent_message.raw_response:
        message.metadata_ = {
            **message_metadata,
            "provider_response": sent_message.raw_response,
        }
    await session.flush()
    return EmailSendResult(
        message_id=message.id,
        external_message_id=sent_message.external_message_id,
    )


async def get_subscribed_email_subscription(
    session: AsyncSession,
    lead_id: uuid.UUID,
) -> EmailSubscription | None:
    return cast(
        EmailSubscription | None,
        await session.scalar(
            select(EmailSubscription)
            .where(
                EmailSubscription.lead_id == lead_id,
                EmailSubscription.status == "subscribed",
                EmailSubscription.unsubscribed_at.is_(None),
            )
            .order_by(EmailSubscription.created_at.desc())
        )
    )


async def ensure_email_unsubscribe_token(
    session: AsyncSession,
    subscription: EmailSubscription,
) -> str:
    if subscription.unsubscribe_token:
        return subscription.unsubscribe_token

    subscription.unsubscribe_token = await generate_unique_unsubscribe_token(session)
    await session.flush()
    return subscription.unsubscribe_token


async def generate_unique_unsubscribe_token(session: AsyncSession) -> str:
    for _ in range(5):
        token = secrets.token_urlsafe(32)
        existing = await session.scalar(
            select(EmailSubscription.id).where(EmailSubscription.unsubscribe_token == token)
        )
        if existing is None:
            return token
    raise RuntimeError("Could not generate a unique email unsubscribe token.")


async def unsubscribe_email_by_token(
    session: AsyncSession,
    token: str,
) -> EmailSubscription | None:
    subscription = await session.scalar(
        select(EmailSubscription).where(EmailSubscription.unsubscribe_token == token)
    )
    if subscription is None:
        return None

    was_subscribed = subscription.status != "unsubscribed"
    now = datetime.now(UTC)
    subscription.status = "unsubscribed"
    subscription.unsubscribed_at = subscription.unsubscribed_at or now
    if was_subscribed:
        session.add(
            Event(
                id=uuid.uuid4(),
                lead_id=subscription.lead_id,
                event_type="email.unsubscribed",
                source="email",
                occurred_at=now,
                payload={
                    "email_subscription_id": str(subscription.id),
                    "email": subscription.email,
                },
                dedupe_key=f"email.unsubscribed:{subscription.id}",
            )
        )
    await session.flush()
    return subscription


def build_unsubscribe_url(public_base_url: str, token: str | None) -> str:
    if not token:
        raise ValueError("Email unsubscribe token is missing.")
    return f"{public_base_url.rstrip('/')}/email/unsubscribe/{quote(token, safe='')}"


def append_unsubscribe_footer(text: str, unsubscribe_url: str) -> str:
    return (
        f"{text.rstrip()}\n\n"
        "---\n"
        "Если вы больше не хотите получать письма, можно отписаться здесь:\n"
        f"{unsubscribe_url}"
    )


def append_email_button_links(text: str, buttons: list[dict[str, str]]) -> str:
    url_lines = [
        f"{button['text']}: {button['url']}"
        for button in buttons
        if button.get("url")
    ]
    if not url_lines:
        return text
    return f"{text.rstrip()}\n\n" + "\n".join(url_lines)


def extract_email_buttons(metadata: dict[str, Any]) -> list[dict[str, str]]:
    raw_buttons = metadata.get("buttons")
    if not isinstance(raw_buttons, list):
        return []

    buttons: list[dict[str, str]] = []
    for raw_button in raw_buttons:
        if not isinstance(raw_button, dict):
            continue
        text = raw_button.get("text")
        url = raw_button.get("url")
        if isinstance(text, str) and isinstance(url, str) and text and url:
            buttons.append({"text": text, "url": url})
    return buttons


def build_html_email_body(
    *,
    text: str,
    buttons: list[dict[str, str]],
    unsubscribe_url: str,
    signature_image_url: str | None,
) -> str:
    paragraphs = [
        paragraph.strip()
        for paragraph in text.strip().split("\n\n")
        if paragraph.strip()
    ]
    paragraph_html = "\n".join(
        f'<p style="margin:0 0 18px;line-height:1.55;">'
        f"{escape(paragraph).replace(chr(10), '<br>')}"
        "</p>"
        for paragraph in paragraphs
    )
    button_html = "\n".join(
        '<p style="margin:10px 0;text-align:center;">'
        f'<a href="{escape(button["url"], quote=True)}" '
        'style="display:inline-block;background:#0b5d1e;color:#ffffff;'
        'text-decoration:none;border-radius:6px;padding:12px 22px;'
        'font-size:16px;line-height:1.2;">'
        f'{escape(button["text"])}</a></p>'
        for button in buttons
    )
    signature_photo = ""
    if signature_image_url:
        signature_photo = (
            '<td style="width:132px;padding:0 24px 0 0;vertical-align:middle;">'
            f'<img src="{escape(signature_image_url, quote=True)}" width="120" height="120" '
            'alt="Айсу Кам" style="display:block;width:120px;height:120px;'
            'border-radius:50%;object-fit:cover;border:1px solid #e5e7eb;">'
            "</td>"
        )

    return f"""<!doctype html>
<html>
  <body style="margin:0;padding:0;background:#ffffff;color:#1f2933;">
    <div style="max-width:620px;margin:0 auto;padding:28px 20px 24px;
      font-family:Arial,Helvetica,sans-serif;font-size:16px;">
      {paragraph_html}
      <div style="margin:24px 0 32px;">{button_html}</div>
      <table role="presentation" cellpadding="0" cellspacing="0" style="margin-top:42px;">
        <tr>
          {signature_photo}
          <td style="vertical-align:middle;color:#1f2933;font-size:15px;line-height:1.5;">
            <p style="margin:0 0 8px;font-weight:700;">С любовью, Айсу Кам.</p>
            <p style="margin:0;">Школа искусства преображения жизни &quot;Сатья-Юга&quot;</p>
          </td>
        </tr>
      </table>
      <p style="margin:34px 0 0;color:#6b7280;font-size:12px;line-height:1.4;">
        Если вы больше не хотите получать письма, можно
        <a href="{escape(unsubscribe_url, quote=True)}" style="color:#6b7280;">отписаться здесь</a>.
      </p>
    </div>
  </body>
</html>"""


def build_unisender_go_payload(
    *,
    to_email: str,
    subject: str,
    text: str,
    html: str | None,
    from_email: str,
    from_name: str | None,
    reply_to_email: str | None,
    reply_to_name: str | None,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    body: dict[str, str] = {"plaintext": text}
    if html is not None:
        body["html"] = html

    message: dict[str, Any] = {
        "recipients": [{"email": to_email}],
        "subject": subject,
        "from_email": from_email,
        "body": body,
        "global_metadata": build_unisender_go_metadata(metadata),
    }
    if from_name is not None:
        message["from_name"] = from_name
    if reply_to_email is not None:
        message["reply_to"] = reply_to_email
    if reply_to_name is not None:
        message["reply_to_name"] = reply_to_name
    if isinstance(metadata.get("message_id"), str):
        message["idempotence_key"] = metadata["message_id"]
    if isinstance(metadata.get("unsubscribe_url"), str):
        message["options"] = {"unsubscribe_url": metadata["unsubscribe_url"]}

    return {"message": message}


def build_unisender_go_metadata(metadata: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in metadata.items():
        if value is None:
            continue
        if isinstance(value, str):
            result[key] = value
        elif isinstance(value, int | float | bool):
            result[key] = str(value)
    return result


def parse_unisender_go_response(response: httpx.Response) -> dict[str, Any]:
    try:
        raw_data = response.json()
    except ValueError:
        raw_data = {"raw_text": response.text}

    data = cast(dict[str, Any], raw_data if isinstance(raw_data, dict) else {"response": raw_data})
    if response.is_error:
        raise RuntimeError(f"Unisender Go email send failed: HTTP {response.status_code} {data!r}")
    if "error" in data or "errors" in data:
        raise RuntimeError(f"Unisender Go email send failed: {data!r}")
    return data


def extract_unisender_go_message_id(response_data: dict[str, Any]) -> str | None:
    for key in ("message_id", "email_id", "id", "job_id"):
        value = response_data.get(key)
        if isinstance(value, str | int):
            return str(value)

    result = response_data.get("result")
    if isinstance(result, dict):
        for key in ("message_id", "email_id", "id", "job_id"):
            value = result.get(key)
            if isinstance(value, str | int):
                return str(value)
    return None
