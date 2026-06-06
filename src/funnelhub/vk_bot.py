from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.config import Settings
from funnelhub.services.bot_linking import link_messenger_identity
from funnelhub.services.funnel_answers import handle_funnel_text_reply
from funnelhub.services.funnel_autostart import restart_default_funnel_for_lead
from funnelhub.services.funnel_engine import load_funnel_definition, run_due_funnel_step
from funnelhub.services.funnel_runner import MessengerFunnelStepSender
from funnelhub.services.inbox import (
    mark_conversation_auto_handled,
    record_inbound_messenger_message,
)
from funnelhub.services.inbox_notifications import notify_admin_about_inbound_message
from funnelhub.services.vk_messaging import HttpVkMessageClient, unsubscribe_vk_identity


async def handle_vk_message_new(
    session: AsyncSession,
    settings: Settings,
    event: dict[str, Any],
) -> str:
    message = extract_vk_message(event)
    external_user_id = extract_vk_user_id(message)
    text = str(message.get("text") or "").strip()

    if is_stop_command(text):
        await unsubscribe_vk_identity(session, external_user_id)
        return "ok"

    token = extract_vk_start_token(message)
    if token is None:
        inbound_message = await record_inbound_messenger_message(
            session=session,
            channel="vk",
            external_user_id=external_user_id,
            body=text,
            external_message_id=extract_vk_message_id(message),
            metadata={"source": "vk_message_new"},
        )
        if settings.vk_group_access_token:
            definition = load_funnel_definition(settings.default_funnel_path)
            vk_client = HttpVkMessageClient(
                access_token=settings.vk_group_access_token,
                api_version=settings.vk_api_version,
            )
            sender = MessengerFunnelStepSender(
                session=session,
                telegram_bot=None,
                vk_client=vk_client,
            )
            handled = await handle_funnel_text_reply(
                session=session,
                definition=definition,
                channel="vk",
                external_user_id=external_user_id,
                text=text,
                sender=sender,
            )
            if handled:
                await mark_conversation_auto_handled(
                    session=session,
                    channel="vk",
                    external_user_id=external_user_id,
                )
            elif inbound_message is not None:
                await notify_admin_about_inbound_message(
                    session=session,
                    settings=settings,
                    message=inbound_message,
                )
        elif inbound_message is not None:
            await notify_admin_about_inbound_message(
                session=session,
                settings=settings,
                message=inbound_message,
            )
        if inbound_message is not None:
            await session.flush()
        return "ok"

    await link_vk_identity_and_start_funnel(
        session=session,
        settings=settings,
        token=token,
        external_user_id=external_user_id,
        raw_profile=message,
    )
    return "ok"


async def handle_vk_message_allow(
    session: AsyncSession,
    settings: Settings,
    event: dict[str, Any],
) -> str:
    obj = event.get("object")
    if not isinstance(obj, dict):
        return "ok"

    external_user_id = extract_vk_user_id(obj)
    token = extract_vk_start_token(obj)
    if token is None:
        return "ok"

    await link_vk_identity_and_start_funnel(
        session=session,
        settings=settings,
        token=token,
        external_user_id=external_user_id,
        raw_profile=obj,
    )
    return "ok"


async def link_vk_identity_and_start_funnel(
    session: AsyncSession,
    settings: Settings,
    token: str,
    external_user_id: str,
    raw_profile: dict[str, Any],
) -> None:
    result = await link_messenger_identity(
        session=session,
        token=token,
        channel="vk",
        external_user_id=external_user_id,
        username=None,
        display_name=None,
        raw_profile=raw_profile,
        allow_relink=True,
    )
    state = await restart_default_funnel_for_lead(
        session=session,
        settings=settings,
        lead_id=result.lead_id,
        messenger_channel="vk",
    )
    if not settings.vk_group_access_token:
        return

    definition = load_funnel_definition(settings.default_funnel_path)
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


def extract_vk_message(event: dict[str, Any]) -> dict[str, Any]:
    obj = event.get("object")
    if not isinstance(obj, dict):
        return {}

    message = obj.get("message")
    if isinstance(message, dict):
        return message
    return obj


def extract_vk_user_id(message: dict[str, Any]) -> str:
    user_id = message.get("from_id") or message.get("user_id")
    if user_id is None:
        raise ValueError("VK message has no sender id.")
    return str(user_id)


def extract_vk_message_id(message: dict[str, Any]) -> str | None:
    message_id = message.get("id") or message.get("conversation_message_id")
    if message_id is None:
        return None
    return str(message_id)


def extract_vk_start_token(message: dict[str, Any]) -> str | None:
    token = normalize_token(message.get("ref"))
    if token is not None:
        return token

    token = normalize_token(message.get("key"))
    if token is not None:
        return token

    token = normalize_token(message.get("access_key"))
    if token is not None:
        return token

    token = normalize_token(message.get("start"))
    if token is not None:
        return token

    payload_token = extract_token_from_payload(message.get("payload"))
    if payload_token is not None:
        return payload_token

    return extract_token_from_text(str(message.get("text") or ""))


def extract_token_from_payload(raw_payload: Any) -> str | None:
    if not raw_payload:
        return None
    if isinstance(raw_payload, dict):
        payload = raw_payload
    elif isinstance(raw_payload, str):
        try:
            decoded = json.loads(raw_payload)
        except json.JSONDecodeError:
            return normalize_token(raw_payload)
        if not isinstance(decoded, dict):
            return None
        payload = decoded
    else:
        return None

    for key in ("token", "start", "ref", "key", "access_key", "bot_link_token"):
        token = normalize_token(payload.get(key))
        if token is not None:
            return token
    return None


def extract_token_from_text(text: str) -> str | None:
    parts = text.strip().split(maxsplit=1)
    if len(parts) != 2:
        return None
    command, token = parts
    if command.lower() not in {"/start", "start", "начать"}:
        return None
    return normalize_token(token)


def normalize_token(value: Any) -> str | None:
    if value is None:
        return None
    token = str(value).strip()
    return token or None


def is_stop_command(text: str) -> bool:
    return text.strip().lower() in {"/stop", "stop", "стоп", "отписаться"}
