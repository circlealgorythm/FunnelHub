from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.db.models import MessengerIdentity
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
    ) -> None:
        self._session = session
        self._telegram_bot = telegram_bot
        self._vk_client = vk_client

    async def send(self, payload: FunnelStepSend) -> None:
        step = payload.step
        if step.channel == "email":
            raise ValueError("Email funnel steps are not supported by the messenger runner.")
        if step.channel == "telegram":
            await self._send_telegram(payload)
            return
        if step.channel == "vk":
            await self._send_vk(payload)
            return
        if step.channel == "messenger":
            identity = await self._get_latest_supported_identity(payload.lead_id)
            if identity is None:
                raise ValueError("Lead has no subscribed messenger identity.")
            if identity.channel == "telegram":
                await self._send_telegram(payload)
                return
            if identity.channel == "vk":
                await self._send_vk(payload)
                return

        raise ValueError(f"Unsupported funnel step channel: {step.channel}")

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

    async def _get_latest_supported_identity(self, lead_id: uuid.UUID) -> MessengerIdentity | None:
        identity = await self._session.scalar(
            select(MessengerIdentity)
            .where(
                MessengerIdentity.lead_id == lead_id,
                MessengerIdentity.is_subscribed.is_(True),
                MessengerIdentity.channel.in_(self._configured_channels()),
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
    )
    sent = 0
    skipped = 0
    failed = 0

    for state in states:
        try:
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
                await send_pending_question_reminder(
                    session=session,
                    state=state,
                    definition=definition,
                    sender=sender,
                    now=now,
                )
            await session.commit()
        except Exception:
            failed += 1
            await session.rollback()
            logger.exception(
                "Failed to run funnel step",
                extra={"funnel_key": definition.key, "funnel_state_id": str(state.id)},
            )

    return FunnelRunnerStats(
        due=len(states),
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
