from __future__ import annotations

import uuid
from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
from sqlalchemy import delete, select

from funnelhub.db.base import Base
from funnelhub.db.models import FunnelState, Lead
from funnelhub.db.session import async_session_maker, engine
from funnelhub.services.funnel_engine import (
    DryRunFunnelStepSender,
    FunnelDefinition,
    get_due_funnel_states,
    load_funnel_definition,
    parse_delay,
    run_due_funnel_step,
    start_funnel_for_lead,
)

TEST_GC_ID = 987654600


@pytest.fixture
async def prepare_database() -> AsyncGenerator[None]:
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    await cleanup_test_leads()
    yield
    await cleanup_test_leads()
    await engine.dispose()


async def cleanup_test_leads() -> None:
    async with async_session_maker() as session:
        lead_ids = set(
            await session.scalars(select(Lead.id).where(Lead.getcourse_user_id == TEST_GC_ID))
        )
        if lead_ids:
            await session.execute(delete(Lead).where(Lead.id.in_(lead_ids)))
        await session.commit()


async def create_test_lead() -> uuid.UUID:
    async with async_session_maker() as session:
        lead = Lead(id=uuid.uuid4(), getcourse_user_id=TEST_GC_ID, raw_getcourse_data={})
        session.add(lead)
        await session.commit()
        return lead.id


def build_definition() -> FunnelDefinition:
    return FunnelDefinition.model_validate(
        {
            "key": "test_funnel",
            "version": 1,
            "steps": [
                {
                    "key": "welcome",
                    "delay": "0m",
                    "channel": "telegram",
                    "text": "Welcome",
                },
                {
                    "key": "day_1",
                    "delay": "1d",
                    "channel": "telegram",
                    "text": "Day 1",
                },
            ],
        }
    )


def test_parse_delay() -> None:
    assert parse_delay("0m") == timedelta(minutes=0)
    assert parse_delay("15m") == timedelta(minutes=15)
    assert parse_delay("2h") == timedelta(hours=2)
    assert parse_delay("3d") == timedelta(days=3)

    with pytest.raises(ValueError, match="Delay unit"):
        parse_delay("1w")


def test_load_funnel_definition_from_yaml() -> None:
    definition = load_funnel_definition(Path("content/funnels/example.yml"))

    assert definition.key == "example_onboarding"
    assert definition.version == 1
    assert [step.key for step in definition.steps] == ["welcome", "follow_up"]


async def test_start_funnel_for_lead_creates_state(
    prepare_database: None,
) -> None:
    lead_id = await create_test_lead()
    definition = build_definition()
    now = datetime(2026, 5, 28, 10, 0, tzinfo=UTC)

    async with async_session_maker() as session:
        state = await start_funnel_for_lead(session, lead_id, definition, now=now)
        await session.commit()

    assert state.lead_id == lead_id
    assert state.funnel_key == "test_funnel"
    assert state.status == "active"
    assert state.current_step_key == "welcome"
    assert state.next_run_at == now
    assert state.metadata_ == {"definition_version": 1, "step_index": 0}


async def test_start_funnel_for_lead_reuses_existing_state(
    prepare_database: None,
) -> None:
    lead_id = await create_test_lead()
    definition = build_definition()
    now = datetime(2026, 5, 28, 10, 0, tzinfo=UTC)

    async with async_session_maker() as session:
        first_state = await start_funnel_for_lead(session, lead_id, definition, now=now)
        second_state = await start_funnel_for_lead(
            session,
            lead_id,
            definition,
            now=now + timedelta(hours=1),
        )
        await session.commit()

    assert first_state.id == second_state.id


async def test_get_due_funnel_states(
    prepare_database: None,
) -> None:
    lead_id = await create_test_lead()
    definition = build_definition()
    now = datetime(2026, 5, 28, 10, 0, tzinfo=UTC)

    async with async_session_maker() as session:
        await start_funnel_for_lead(session, lead_id, definition, now=now)
        due_states = await get_due_funnel_states(session, now=now)

    assert len(due_states) == 1
    assert due_states[0].lead_id == lead_id


async def test_run_due_funnel_step_advances_state(
    prepare_database: None,
) -> None:
    lead_id = await create_test_lead()
    definition = build_definition()
    now = datetime(2026, 5, 28, 10, 0, tzinfo=UTC)
    sender = DryRunFunnelStepSender()

    async with async_session_maker() as session:
        state = await start_funnel_for_lead(session, lead_id, definition, now=now)
        result = await run_due_funnel_step(session, state, definition, sender, now=now)
        await session.commit()

    assert result is not None
    assert result.sent_step_key == "welcome"
    assert result.next_step_key == "day_1"
    assert result.next_run_at == now + timedelta(days=1)
    assert [sent.step.key for sent in sender.sent] == ["welcome"]

    async with async_session_maker() as session:
        persisted_state = await session.get(FunnelState, state.id)
        assert persisted_state is not None
        assert persisted_state.current_step_key == "day_1"
        assert persisted_state.status == "active"


async def test_run_due_funnel_step_completes_after_last_step(
    prepare_database: None,
) -> None:
    lead_id = await create_test_lead()
    definition = build_definition()
    now = datetime(2026, 5, 28, 10, 0, tzinfo=UTC)
    sender = DryRunFunnelStepSender()

    async with async_session_maker() as session:
        state = await start_funnel_for_lead(session, lead_id, definition, now=now)
        await run_due_funnel_step(session, state, definition, sender, now=now)
        second_run_at = now + timedelta(days=1)
        result = await run_due_funnel_step(session, state, definition, sender, now=second_run_at)
        await session.commit()

    assert result is not None
    assert result.sent_step_key == "day_1"
    assert result.status == "completed"
    assert result.next_step_key is None
    assert [sent.step.key for sent in sender.sent] == ["welcome", "day_1"]

    async with async_session_maker() as session:
        persisted_state = await session.get(FunnelState, state.id)
        assert persisted_state is not None
        assert persisted_state.status == "completed"
        assert persisted_state.current_step_key is None
        assert persisted_state.next_run_at is None
