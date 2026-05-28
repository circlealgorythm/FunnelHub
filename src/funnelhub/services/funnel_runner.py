from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.services.funnel_engine import (
    FunnelDefinition,
    FunnelStepSend,
    get_due_funnel_states,
    run_due_funnel_step,
)
from funnelhub.services.telegram_messaging import (
    TelegramMessageClient,
    TelegramUrlButton,
    send_telegram_text_message,
)

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class FunnelRunnerStats:
    due: int
    sent: int
    skipped: int
    failed: int


class TelegramFunnelStepSender:
    def __init__(self, session: AsyncSession, bot: TelegramMessageClient) -> None:
        self._session = session
        self._bot = bot

    async def send(self, payload: FunnelStepSend) -> None:
        step = payload.step
        if step.channel != "telegram":
            raise ValueError(f"Unsupported funnel step channel for Telegram runner: {step.channel}")

        await send_telegram_text_message(
            session=self._session,
            bot=self._bot,
            lead_id=payload.lead_id,
            text=step.text,
            url_buttons=[
                TelegramUrlButton(text=button.text, url=button.url) for button in step.buttons
            ],
        )


async def run_due_funnel_once(
    session: AsyncSession,
    definition: FunnelDefinition,
    bot: TelegramMessageClient,
    now: datetime | None = None,
    limit: int = 100,
) -> FunnelRunnerStats:
    states = await get_due_funnel_states(
        session=session,
        now=now,
        limit=limit,
        funnel_key=definition.key,
    )
    sender = TelegramFunnelStepSender(session=session, bot=bot)
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
