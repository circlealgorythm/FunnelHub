from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.config import Settings
from funnelhub.most_telegram_bot import (
    handle_button,
    load_most_vk_definition,
)
from funnelhub.services.bot_linking import link_messenger_identity
from funnelhub.services.funnel_autostart import restart_funnel_for_lead
from funnelhub.services.funnel_engine import run_due_funnel_step
from funnelhub.services.funnel_runner import MessengerFunnelStepSender
from funnelhub.services.inbox import (
    mark_conversation_auto_handled,
    record_inbound_messenger_message,
)
from funnelhub.services.inbox_notifications import notify_admin_about_inbound_message
from funnelhub.services.vk_messaging import HttpVkMessageClient, unsubscribe_vk_identity
from funnelhub.vk_bot import (
    extract_vk_message,
    extract_vk_message_id,
    extract_vk_start_token,
    extract_vk_user_id,
    is_stop_command,
)

MOST_VK_CHANNEL = "vk_most"
MOST_VK_FUNNEL_KEY = "most_tsennostey_vk"


async def handle_most_vk_message_new(
    session: AsyncSession,
    settings: Settings,
    event: dict[str, Any],
) -> str:
    message = extract_vk_message(event)
    external_user_id = extract_vk_user_id(message)
    text = str(message.get("text") or "").strip()

    if is_stop_command(text):
        await unsubscribe_vk_identity(session, external_user_id, channel=MOST_VK_CHANNEL)
        return "ok"

    token = extract_vk_start_token(message)
    if token is not None:
        await link_most_vk_identity_and_start_funnel(
            session=session,
            settings=settings,
            token=token,
            external_user_id=external_user_id,
            raw_profile=message,
        )
        return "ok"

    inbound_message = await record_inbound_messenger_message(
        session=session,
        channel=MOST_VK_CHANNEL,
        external_user_id=external_user_id,
        body=text,
        external_message_id=extract_vk_message_id(message),
        metadata={"source": "most_vk_message_new"},
    )
    if not settings.most_vk_group_access_token:
        if inbound_message is not None:
            await notify_admin_about_inbound_message(
                session=session,
                settings=settings,
                message=inbound_message,
            )
        return "ok"

    sender = build_sender(session, settings)
    handled = await handle_button(
        session=session,
        settings=settings,
        user_id=external_user_id,
        value=text,
        sender=sender,
        channel=MOST_VK_CHANNEL,
        funnel_key=MOST_VK_FUNNEL_KEY,
    )
    if handled:
        await mark_conversation_auto_handled(
            session=session,
            channel=MOST_VK_CHANNEL,
            external_user_id=external_user_id,
        )
    elif inbound_message is not None:
        await notify_admin_about_inbound_message(
            session=session,
            settings=settings,
            message=inbound_message,
        )
    return "ok"


async def handle_most_vk_message_allow(
    session: AsyncSession,
    settings: Settings,
    event: dict[str, Any],
) -> str:
    raw_profile = event.get("object")
    if not isinstance(raw_profile, dict):
        return "ok"
    token = extract_vk_start_token(raw_profile)
    if token is None:
        return "ok"
    await link_most_vk_identity_and_start_funnel(
        session=session,
        settings=settings,
        token=token,
        external_user_id=extract_vk_user_id(raw_profile),
        raw_profile=raw_profile,
    )
    return "ok"


async def link_most_vk_identity_and_start_funnel(
    *,
    session: AsyncSession,
    settings: Settings,
    token: str,
    external_user_id: str,
    raw_profile: dict[str, Any],
) -> None:
    result = await link_messenger_identity(
        session=session,
        token=token,
        channel=MOST_VK_CHANNEL,
        external_user_id=external_user_id,
        username=None,
        display_name=None,
        raw_profile=raw_profile,
        allow_relink=True,
    )
    definition = load_most_vk_definition(settings)
    state = await restart_funnel_for_lead(
        session=session,
        lead_id=result.lead_id,
        definition=definition,
        messenger_channel=MOST_VK_CHANNEL,
    )
    if not settings.most_vk_group_access_token:
        return
    await run_due_funnel_step(
        session=session,
        state=state,
        definition=definition,
        sender=build_sender(session, settings),
    )


def build_sender(session: AsyncSession, settings: Settings) -> MessengerFunnelStepSender:
    if not settings.most_vk_group_access_token:
        raise ValueError("MOST_VK_GROUP_ACCESS_TOKEN is not configured.")
    return MessengerFunnelStepSender(
        session=session,
        telegram_bot=None,
        vk_client=HttpVkMessageClient(
            access_token=settings.most_vk_group_access_token,
            api_version=settings.vk_api_version,
        ),
        vk_channel=MOST_VK_CHANNEL,
    )
