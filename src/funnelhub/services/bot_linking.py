from __future__ import annotations

import secrets
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.config import Settings
from funnelhub.db.models import BotLinkToken, Lead, MessengerIdentity

BOT_LINK_TOKEN_TTL = timedelta(days=30)


@dataclass(frozen=True)
class MessengerLinkResult:
    lead_id: uuid.UUID
    identity_id: uuid.UUID
    created: bool


async def create_or_get_active_bot_link_token(
    session: AsyncSession,
    lead: Lead,
) -> BotLinkToken:
    now = datetime.now(UTC)
    existing = await session.scalar(
        select(BotLinkToken)
        .where(
            BotLinkToken.lead_id == lead.id,
            BotLinkToken.status == "active",
        )
        .order_by(BotLinkToken.created_at.desc())
    )
    if existing is not None and (existing.expires_at is None or existing.expires_at > now):
        return existing

    token = BotLinkToken(
        id=uuid.uuid4(),
        lead_id=lead.id,
        token=generate_bot_link_token(),
        status="active",
        expires_at=now + BOT_LINK_TOKEN_TTL,
        metadata_={"ttl_days": BOT_LINK_TOKEN_TTL.days},
    )
    session.add(token)
    await session.flush()
    return token


async def link_messenger_identity(
    session: AsyncSession,
    token: str,
    channel: str,
    external_user_id: str,
    username: str | None,
    display_name: str | None,
    raw_profile: dict[str, Any],
) -> MessengerLinkResult:
    bot_link_token = await get_active_bot_link_token(session, token)
    if bot_link_token is None:
        raise ValueError("Bot link token is invalid or expired.")

    existing_identity = await session.scalar(
        select(MessengerIdentity).where(
            MessengerIdentity.channel == channel,
            MessengerIdentity.external_user_id == external_user_id,
        )
    )
    created = existing_identity is None
    if existing_identity is not None and existing_identity.lead_id != bot_link_token.lead_id:
        raise ValueError("Messenger identity is already linked to another lead.")

    now = datetime.now(UTC)
    if existing_identity is None:
        existing_identity = MessengerIdentity(
            id=uuid.uuid4(),
            lead_id=bot_link_token.lead_id,
            channel=channel,
            external_user_id=external_user_id,
            username=username,
            display_name=display_name,
            is_subscribed=True,
            subscribed_at=now,
            raw_profile=raw_profile,
        )
        session.add(existing_identity)
    else:
        existing_identity.username = username or existing_identity.username
        existing_identity.display_name = display_name or existing_identity.display_name
        existing_identity.is_subscribed = True
        existing_identity.unsubscribed_at = None
        existing_identity.raw_profile = {**existing_identity.raw_profile, **raw_profile}

    bot_link_token.used_at = bot_link_token.used_at or now
    await session.flush()
    return MessengerLinkResult(
        lead_id=bot_link_token.lead_id,
        identity_id=existing_identity.id,
        created=created,
    )


async def get_active_bot_link_token(
    session: AsyncSession,
    token: str,
) -> BotLinkToken | None:
    bot_link_token = await session.scalar(
        select(BotLinkToken).where(
            BotLinkToken.token == token,
            BotLinkToken.status == "active",
        )
    )
    if bot_link_token is None:
        return None

    now = datetime.now(UTC)
    if bot_link_token.expires_at is not None and bot_link_token.expires_at <= now:
        bot_link_token.status = "expired"
        return None

    return bot_link_token


def build_join_url(settings: Settings, token: str) -> str:
    return f"{settings.public_base_url.rstrip('/')}/join/{token}"


def build_telegram_deep_link(settings: Settings, token: str) -> str | None:
    if not settings.telegram_bot_username:
        return None
    username = settings.telegram_bot_username.strip().lstrip("@")
    if not username:
        return None
    return f"https://t.me/{username}?start={token}"


def build_vk_deep_link(settings: Settings, token: str) -> str | None:
    if not settings.vk_group_screen_name:
        return None
    screen_name = settings.vk_group_screen_name.strip().lstrip("@")
    if not screen_name:
        return None
    return f"https://vk.me/{screen_name}?ref={token}"


def generate_bot_link_token() -> str:
    return secrets.token_urlsafe(24)
