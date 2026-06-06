from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime

import pytest
from sqlalchemy import delete, select

from funnelhub.config import Settings
from funnelhub.db.base import Base
from funnelhub.db.models import FunnelState, Lead
from funnelhub.db.session import async_session_maker, engine
from funnelhub.services.funnel_autostart import restart_default_funnel_for_lead

TEST_GC_ID = 987654900


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"


@pytest.fixture
async def prepare_database() -> AsyncGenerator[None]:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    await cleanup()
    yield
    await cleanup()
    await engine.dispose()


async def cleanup() -> None:
    async with async_session_maker() as session:
        await session.execute(delete(Lead).where(Lead.getcourse_user_id == TEST_GC_ID))
        await session.commit()


async def test_restart_default_funnel_resets_existing_state(
    prepare_database: None,
) -> None:
    now = datetime(2026, 6, 6, 9, 0, tzinfo=UTC)
    async with async_session_maker() as session:
        lead = Lead(id=uuid.uuid4(), getcourse_user_id=TEST_GC_ID, raw_getcourse_data={})
        session.add(lead)
        await session.flush()
        session.add(
            FunnelState(
                id=uuid.uuid4(),
                lead_id=lead.id,
                funnel_key="aisu_consultation",
                status="active",
                current_step_key="step_02_video",
                next_run_at=now,
                metadata_={
                    "answers": {"topic": "money"},
                    "pending_question_key": "experience",
                    "step_index": 3,
                    "definition_version": 2,
                },
            )
        )
        await session.commit()
        lead_id = lead.id

    async with async_session_maker() as session:
        state = await restart_default_funnel_for_lead(
            session=session,
            settings=Settings(),
            lead_id=lead_id,
            now=now,
            messenger_channel="telegram",
        )
        await session.commit()

    assert state.current_step_key == "welcome"
    assert state.next_run_at == now
    assert state.metadata_["messenger_channel"] == "telegram"
    assert state.metadata_["restart_reason"] == "bot_start"
    assert "answers" not in state.metadata_
    assert "pending_question_key" not in state.metadata_

    async with async_session_maker() as session:
        count = await session.scalar(
            select(FunnelState).where(
                FunnelState.lead_id == lead_id,
                FunnelState.funnel_key == "aisu_consultation",
            )
        )
    assert count is not None
