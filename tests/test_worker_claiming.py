import uuid
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
from sqlalchemy.dialects import postgresql, sqlite

from funnelhub.db.models import FunnelState
from funnelhub.services.funnel_engine import (
    DryRunFunnelStepSender,
    FunnelDefinition,
    FunnelStep,
    run_due_funnel_step,
)


def sample_definition() -> FunnelDefinition:
    return FunnelDefinition(
        key="test_funnel",
        steps=[
            FunnelStep(key="step_1", channel="telegram", text="Hello 1"),
            FunnelStep(key="step_2", channel="telegram", text="Hello 2", delay="1h"),
        ],
    )


def sample_state(now: datetime) -> FunnelState:
    return FunnelState(
        id=uuid.uuid4(),
        lead_id=uuid.uuid4(),
        funnel_key="test_funnel",
        channel="telegram",
        status="active",
        current_step_key="step_1",
        next_run_at=now - timedelta(minutes=1),
        metadata_={},
    )


@pytest.mark.anyio
async def test_funnel_step_idempotency_prevents_duplicate_send() -> None:
    now = datetime.now(UTC)
    definition = sample_definition()
    state = sample_state(now)
    state.metadata_ = {"last_sent_step_key": "step_1"}

    sender = DryRunFunnelStepSender()
    mock_session = AsyncMock()

    result = await run_due_funnel_step(
        session=mock_session,
        state=state,
        definition=definition,
        sender=sender,
        now=now,
    )

    assert result is None
    assert len(sender.sent) == 0


@pytest.mark.anyio
async def test_funnel_step_in_flight_claim_prevents_concurrent_send() -> None:
    now = datetime.now(UTC)
    definition = sample_definition()
    state = sample_state(now)
    # Claimed 30 seconds ago (well within 300s TTL)
    claimed_at = (now - timedelta(seconds=30)).isoformat()
    state.metadata_ = {"in_flight_send_attempts": {"step_1": claimed_at}}

    sender = DryRunFunnelStepSender()
    mock_session = AsyncMock()

    result = await run_due_funnel_step(
        session=mock_session,
        state=state,
        definition=definition,
        sender=sender,
        now=now,
    )

    assert result is None
    assert len(sender.sent) == 0


@pytest.mark.anyio
async def test_funnel_step_in_flight_claim_expires_after_ttl_and_allows_send() -> None:
    now = datetime.now(UTC)
    definition = sample_definition()
    state = sample_state(now)
    # Claimed 400 seconds ago (expired claim, worker crashed previously)
    expired_at = (now - timedelta(seconds=400)).isoformat()
    state.metadata_ = {"in_flight_send_attempts": {"step_1": expired_at}}

    sender = DryRunFunnelStepSender()
    mock_session = AsyncMock()

    result = await run_due_funnel_step(
        session=mock_session,
        state=state,
        definition=definition,
        sender=sender,
        now=now,
    )

    assert result is not None
    assert result.sent_step_key == "step_1"
    assert len(sender.sent) == 1
    assert state.metadata_["last_sent_step_key"] == "step_1"
    assert "step_1" not in state.metadata_.get("in_flight_send_attempts", {})


def test_get_due_funnel_states_query_compilation() -> None:
    from sqlalchemy import select

    now = datetime.now(UTC)
    q = (
        select(FunnelState)
        .where(
            FunnelState.status == "active",
            FunnelState.next_run_at <= now,
        )
        .with_for_update(skip_locked=True)
    )

    pg_sql = str(q.compile(dialect=postgresql.dialect()))
    assert "FOR UPDATE SKIP LOCKED" in pg_sql

    sqlite_sql = str(q.compile(dialect=sqlite.dialect()))
    assert "FROM funnel_states" in sqlite_sql
