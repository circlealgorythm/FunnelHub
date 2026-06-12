from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.config import Settings
from funnelhub.db.models import FunnelState, Lead, MessengerIdentity
from funnelhub.services.bot_linking import (
    build_telegram_deep_link,
    build_vk_launch_link,
    create_or_get_active_bot_link_token,
)
from funnelhub.services.email_messaging import EmailProviderClient, send_email_text_message
from funnelhub.services.funnel_answers import send_pending_question_reminder
from funnelhub.services.funnel_engine import (
    FunnelButton,
    FunnelDefinition,
    FunnelStepSend,
    get_due_funnel_states,
    run_due_funnel_step,
)
from funnelhub.services.telegram_messaging import (
    TelegramMessageClient,
    TelegramTextButton,
    TelegramUrlButton,
    send_telegram_text_message,
)
from funnelhub.services.vk_messaging import (
    VkMessageClient,
    VkTextButton,
    VkUrlButton,
    send_vk_text_message,
)

logger = logging.getLogger(__name__)
BOT_BUTTON_URLS = {
    "funnelhub://bot/telegram": "telegram",
    "funnelhub://bot/vk": "vk",
}
PERMANENT_DELIVERY_ERROR_MARKERS = (
    "Lead has no subscribed email subscription.",
    "Lead has no subscribed VK identity.",
    "Can't send messages for users without permission",
    "No valid recipients",
)


@dataclass(frozen=True)
class FunnelRunnerStats:
    due: int
    sent: int
    skipped: int
    failed: int


class MessengerFunnelStepSender:
    def __init__(
        self,
        session: AsyncSession,
        telegram_bot: TelegramMessageClient | None,
        vk_client: VkMessageClient | None,
        email_client: EmailProviderClient | None = None,
        public_base_url: str = "http://localhost:8000",
        email_from_email: str | None = None,
        email_from_name: str | None = None,
        email_signature_image_url: str | None = None,
        email_default_subject: str = "Сообщение от Aisu Kam",
        settings: Settings | None = None,
    ) -> None:
        self._session = session
        self._telegram_bot = telegram_bot
        self._vk_client = vk_client
        self._email_client = email_client
        self._public_base_url = public_base_url
        self._email_from_email = email_from_email
        self._email_from_name = email_from_name
        self._email_signature_image_url = email_signature_image_url
        self._email_default_subject = email_default_subject
        self._settings = settings

    async def send(self, payload: FunnelStepSend) -> None:
        step = payload.step
        if step.channel == "email":
            await self._send_email(payload)
            return
        if step.channel == "telegram":
            await self._send_telegram(payload)
            return
        if step.channel == "vk":
            await self._send_vk(payload)
            return
        if step.channel == "messenger":
            identity = await self._get_supported_identity(
                payload.lead_id,
                payload.channel,
            )
            if identity is None:
                raise ValueError("Lead has no subscribed messenger identity.")
            if identity.channel == "telegram":
                await self._send_telegram(payload)
                return
            if identity.channel == "vk":
                await self._send_vk(payload)
                return

        raise ValueError(f"Unsupported funnel step channel: {step.channel}")

    async def _send_email(self, payload: FunnelStepSend) -> None:
        if self._email_client is None:
            raise ValueError("Email client is not configured.")

        buttons = await resolve_email_buttons(
            session=self._session,
            lead_id=payload.lead_id,
            settings=self._settings,
            buttons=payload.step.buttons,
        )
        await send_email_text_message(
            session=self._session,
            client=self._email_client,
            lead_id=payload.lead_id,
            subject=payload.step.subject or self._email_default_subject,
            text=payload.step.text,
            public_base_url=self._public_base_url,
            from_email=self._email_from_email,
            from_name=self._email_from_name,
            signature_image_url=self._email_signature_image_url,
            metadata={
                "funnel_key": payload.funnel_key,
                "step_key": payload.step.key,
                **build_email_button_metadata(buttons),
            },
        )

    async def _send_telegram(self, payload: FunnelStepSend) -> None:
        await self.send_text(
            lead_id=payload.lead_id,
            channel="telegram",
            text=payload.step.text,
            buttons=payload.step.buttons,
        )

    async def _send_vk(self, payload: FunnelStepSend) -> None:
        await self.send_text(
            lead_id=payload.lead_id,
            channel="vk",
            text=payload.step.text,
            buttons=payload.step.buttons,
        )

    async def send_text(
        self,
        lead_id: uuid.UUID,
        channel: str,
        text: str,
        buttons: list[FunnelButton] | None = None,
    ) -> None:
        if channel == "telegram":
            await self._send_telegram_text(lead_id=lead_id, text=text, buttons=buttons or [])
            return
        if channel == "vk":
            await self._send_vk_text(lead_id=lead_id, text=text, buttons=buttons or [])
            return
        raise ValueError(f"Unsupported messenger channel: {channel}")

    async def _send_telegram_text(
        self,
        lead_id: uuid.UUID,
        text: str,
        buttons: list[FunnelButton],
    ) -> None:
        if self._telegram_bot is None:
            raise ValueError("Telegram client is not configured.")

        await send_telegram_text_message(
            session=self._session,
            bot=self._telegram_bot,
            lead_id=lead_id,
            text=text,
            url_buttons=build_telegram_buttons(buttons),
        )

    async def _send_vk_text(
        self,
        lead_id: uuid.UUID,
        text: str,
        buttons: list[FunnelButton],
    ) -> None:
        if self._vk_client is None:
            raise ValueError("VK client is not configured.")

        await send_vk_text_message(
            session=self._session,
            client=self._vk_client,
            lead_id=lead_id,
            text=text,
            url_buttons=build_vk_buttons(buttons),
        )

    async def _get_supported_identity(
        self,
        lead_id: uuid.UUID,
        preferred_channel: str | None,
    ) -> MessengerIdentity | None:
        configured_channels = self._configured_channels()
        if preferred_channel is not None:
            if preferred_channel not in configured_channels:
                raise ValueError(
                    f"Preferred messenger channel is not configured: {preferred_channel}"
                )
            preferred_identity = await self._session.scalar(
                select(MessengerIdentity)
                .where(
                    MessengerIdentity.lead_id == lead_id,
                    MessengerIdentity.is_subscribed.is_(True),
                    MessengerIdentity.channel == preferred_channel,
                )
                .order_by(MessengerIdentity.created_at.desc())
            )
            return preferred_identity

        identity = await self._session.scalar(
            select(MessengerIdentity)
            .where(
                MessengerIdentity.lead_id == lead_id,
                MessengerIdentity.is_subscribed.is_(True),
                MessengerIdentity.channel.in_(configured_channels),
            )
            .order_by(MessengerIdentity.created_at.desc())
        )
        return identity

    def _configured_channels(self) -> list[str]:
        channels: list[str] = []
        if self._telegram_bot is not None:
            channels.append("telegram")
        if self._vk_client is not None:
            channels.append("vk")
        return channels


async def run_due_funnel_once(
    session: AsyncSession,
    definition: FunnelDefinition,
    bot: TelegramMessageClient | None = None,
    vk_client: VkMessageClient | None = None,
    email_client: EmailProviderClient | None = None,
    public_base_url: str = "http://localhost:8000",
    email_from_email: str | None = None,
    email_from_name: str | None = None,
    email_signature_image_url: str | None = None,
    email_default_subject: str = "Сообщение от Aisu Kam",
    settings: Settings | None = None,
    now: datetime | None = None,
    limit: int = 100,
) -> FunnelRunnerStats:
    states = await get_due_funnel_states(
        session=session,
        now=now,
        limit=limit,
        funnel_key=definition.key,
    )
    sender = MessengerFunnelStepSender(
        session=session,
        telegram_bot=bot,
        vk_client=vk_client,
        email_client=email_client,
        public_base_url=public_base_url,
        email_from_email=email_from_email,
        email_from_name=email_from_name,
        email_signature_image_url=email_signature_image_url,
        email_default_subject=email_default_subject,
        settings=settings,
    )
    sent = 0
    skipped = 0
    failed = 0
    state_ids = [state.id for state in states]

    for state_id in state_ids:
        try:
            state = await session.get(FunnelState, state_id)
            if state is None:
                skipped += 1
                continue
            result = await run_due_funnel_step(
                session=session,
                state=state,
                definition=definition,
                sender=sender,
                now=now,
            )
            if result is None:
                skipped += 1
            else:
                sent += 1
                sent_step = definition.steps[definition.step_index(result.sent_step_key)]
                if sent_step.kind != "question":
                    await send_pending_question_reminder(
                        session=session,
                        state=state,
                        definition=definition,
                        sender=sender,
                        now=now,
                    )
            await session.commit()
        except Exception as exc:
            await session.rollback()
            if is_permanent_delivery_error(exc):
                try:
                    paused = await pause_funnel_state_after_permanent_delivery_error(
                        session=session,
                        state_id=state_id,
                        error=exc,
                        now=now,
                    )
                    await session.commit()
                except Exception:
                    failed += 1
                    await session.rollback()
                    logger.exception(
                        "Failed to pause funnel state after permanent delivery error",
                        extra={
                            "funnel_key": definition.key,
                            "funnel_state_id": str(state_id),
                        },
                    )
                    continue

                if paused:
                    skipped += 1
                    logger.warning(
                        "Paused funnel state after permanent delivery error",
                        extra={
                            "funnel_key": definition.key,
                            "funnel_state_id": str(state_id),
                            "error": str(exc),
                        },
                    )
                    continue

            failed += 1
            logger.exception(
                "Failed to run funnel step",
                extra={"funnel_key": definition.key, "funnel_state_id": str(state_id)},
            )

    return FunnelRunnerStats(
        due=len(state_ids),
        sent=sent,
        skipped=skipped,
        failed=failed,
    )


def build_telegram_buttons(
    buttons: list[FunnelButton],
) -> list[TelegramUrlButton | TelegramTextButton]:
    result: list[TelegramUrlButton | TelegramTextButton] = []
    for button in buttons:
        if button.url is None:
            result.append(TelegramTextButton(text=button.text))
        else:
            result.append(TelegramUrlButton(text=button.text, url=button.url))
    return result


def build_vk_buttons(buttons: list[FunnelButton]) -> list[VkUrlButton | VkTextButton]:
    result: list[VkUrlButton | VkTextButton] = []
    for button in buttons:
        if button.url is None:
            result.append(VkTextButton(text=button.text))
        else:
            result.append(VkUrlButton(text=button.text, url=button.url))
    return result


def is_permanent_delivery_error(error: Exception) -> bool:
    message = str(error)
    return any(marker in message for marker in PERMANENT_DELIVERY_ERROR_MARKERS)


async def pause_funnel_state_after_permanent_delivery_error(
    *,
    session: AsyncSession,
    state_id: uuid.UUID,
    error: Exception,
    now: datetime | None,
) -> bool:
    state = await session.get(FunnelState, state_id)
    if state is None or state.status != "active":
        return False

    paused_at = now or datetime.now(UTC)
    state.status = "paused"
    state.paused_at = paused_at
    state.next_run_at = None
    state.metadata_ = {
        **(state.metadata_ or {}),
        "paused_reason": "permanent_delivery_error",
        "paused_error": str(error)[:1000],
        "paused_at": paused_at.isoformat(),
    }
    if "Can't send messages for users without permission" in str(error):
        await unsubscribe_latest_vk_identity_for_lead(session, state.lead_id, paused_at)

    await session.flush()
    return True


async def unsubscribe_latest_vk_identity_for_lead(
    session: AsyncSession,
    lead_id: uuid.UUID,
    unsubscribed_at: datetime,
) -> None:
    identity = await session.scalar(
        select(MessengerIdentity)
        .where(
            MessengerIdentity.lead_id == lead_id,
            MessengerIdentity.channel == "vk",
            MessengerIdentity.is_subscribed.is_(True),
        )
        .order_by(MessengerIdentity.created_at.desc())
    )
    if identity is None:
        return

    identity.is_subscribed = False
    identity.unsubscribed_at = unsubscribed_at
    await session.flush()


def build_email_body(text: str, buttons: list[FunnelButton]) -> str:
    url_lines = [
        f"{button.text}: {button.url}"
        for button in buttons
        if button.url is not None
    ]
    if not url_lines:
        return text
    return f"{text.rstrip()}\n\n" + "\n".join(url_lines)


def build_email_button_metadata(buttons: list[FunnelButton]) -> dict[str, object]:
    if not buttons:
        return {}
    return {
        "buttons": [
            {
                "type": "url" if button.url is not None else "text",
                "text": button.text,
                "url": button.url,
            }
            for button in buttons
        ]
    }


async def resolve_email_buttons(
    *,
    session: AsyncSession,
    lead_id: uuid.UUID,
    settings: Settings | None,
    buttons: list[FunnelButton],
) -> list[FunnelButton]:
    result: list[FunnelButton] = []
    for button in buttons:
        channel = BOT_BUTTON_URLS.get(button.url or "")
        if channel is None:
            result.append(button)
            continue
        if settings is None:
            continue

        link = await build_lead_bot_link(
            session=session,
            lead_id=lead_id,
            settings=settings,
            channel=channel,
        )
        if link is not None:
            result.append(button.model_copy(update={"url": link}))
    return result


async def build_lead_bot_link(
    *,
    session: AsyncSession,
    lead_id: uuid.UUID,
    settings: Settings,
    channel: str,
) -> str | None:
    lead = await session.get(Lead, lead_id)
    if lead is None:
        return None

    bot_link_token = await create_or_get_active_bot_link_token(session, lead)
    if channel == "telegram":
        return build_telegram_deep_link(settings, bot_link_token.token)
    if channel == "vk":
        return build_vk_launch_link(settings, bot_link_token.token)
    return None
