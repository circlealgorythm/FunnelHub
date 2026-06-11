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
    schedule_after_delay,
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


def build_question_definition() -> FunnelDefinition:
    return FunnelDefinition.model_validate(
        {
            "key": "test_funnel",
            "version": 1,
            "questionnaire": {
                "questions": {
                    "topic": {
                        "key": "topic",
                        "text": "Что актуальнее?",
                        "reminder_delay": "5m",
                        "options": [{"key": "money", "text": "Деньги"}],
                    }
                }
            },
            "steps": [
                {
                    "key": "question_topic",
                    "delay": "0m",
                    "channel": "telegram",
                    "kind": "question",
                    "question_key": "topic",
                    "text": "Что актуальнее?",
                },
                {
                    "key": "social",
                    "delay": "1m",
                    "channel": "telegram",
                    "text": "Соцсети",
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


def test_schedule_day_delay_uses_next_local_morning() -> None:
    current_time = datetime(2026, 5, 28, 14, 30, tzinfo=UTC)

    assert schedule_after_delay(current_time, "1d") == datetime(2026, 5, 29, 6, 0, tzinfo=UTC)


def test_schedule_day_delay_uses_next_calendar_day_even_before_morning() -> None:
    current_time = datetime(2026, 5, 28, 5, 30, tzinfo=UTC)

    assert schedule_after_delay(current_time, "1d") == datetime(2026, 5, 29, 6, 0, tzinfo=UTC)


def test_schedule_short_delay_stays_relative() -> None:
    current_time = datetime(2026, 5, 28, 14, 30, tzinfo=UTC)

    assert schedule_after_delay(current_time, "0m") == current_time
    assert schedule_after_delay(current_time, "30m") == current_time + timedelta(minutes=30)


def test_load_funnel_definition_from_yaml() -> None:
    definition = load_funnel_definition(Path("content/funnels/aisu_consultation.yml"))

    assert definition.key == "aisu_consultation"
    assert definition.version == 2
    assert definition.questionnaire is not None
    assert definition.questionnaire.questions["topic"].options[0].text == "Деньги"
    assert definition.steps[0].key == "welcome"
    assert definition.steps[1].kind == "question"


def test_aisu_consultation_uses_day_02_through_day_18_buttons_only() -> None:
    definition = load_funnel_definition(Path("content/funnels/aisu_consultation.yml"))

    day_steps = [step for step in definition.steps if step.key.startswith("day_")]
    button_steps = [step for step in day_steps if step.buttons]

    assert [step.key for step in button_steps] == [
        "day_02",
        "day_03",
        "day_04",
        "day_05",
        "day_06",
        "day_07_part_2",
        "day_08",
        "day_09",
        "day_10",
        "day_11",
        "day_12",
        "day_13",
        "day_14",
        "day_15",
        "day_16",
        "day_17",
        "day_18",
    ]
    assert definition.steps[-1].key == "day_18"
    assert {
        button.url
        for step in button_steps
        for button in step.buttons
    } == {"https://aisukam.ru/courses"}


async def test_start_funnel_for_lead_creates_state(
    prepare_database: None,
) -> None:
    lead_id = await create_test_lead()
    definition = build_definition()
    now = datetime(2026, 5, 28, 10, 0, tzinfo=UTC)

    async with async_session_maker() as session:
        state = await start_funnel_for_lead(
            session,
            lead_id,
            definition,
            channel="telegram",
            now=now,
        )
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
        first_state = await start_funnel_for_lead(
            session,
            lead_id,
            definition,
            channel="telegram",
            now=now,
        )
        second_state = await start_funnel_for_lead(
            session,
            lead_id,
            definition,
            channel="telegram",
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
        await start_funnel_for_lead(
            session,
            lead_id,
            definition,
            channel="telegram",
            now=now,
        )
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
        state = await start_funnel_for_lead(
            session,
            lead_id,
            definition,
            channel="telegram",
            now=now,
        )
        result = await run_due_funnel_step(session, state, definition, sender, now=now)
        await session.commit()

    assert result is not None
    assert result.sent_step_key == "welcome"
    assert result.next_step_key == "day_1"
    assert result.next_run_at == datetime(2026, 5, 29, 6, 0, tzinfo=UTC)
    assert [sent.step.key for sent in sender.sent] == ["welcome"]

    async with async_session_maker() as session:
        persisted_state = await session.get(FunnelState, state.id)
        assert persisted_state is not None
        assert persisted_state.current_step_key == "day_1"
        assert persisted_state.status == "active"


async def test_question_step_waits_for_reminder_delay_before_next_content(
    prepare_database: None,
) -> None:
    lead_id = await create_test_lead()
    definition = build_question_definition()
    now = datetime(2026, 5, 28, 10, 0, tzinfo=UTC)
    sender = DryRunFunnelStepSender()

    async with async_session_maker() as session:
        state = await start_funnel_for_lead(
            session,
            lead_id,
            definition,
            channel="telegram",
            now=now,
        )
        result = await run_due_funnel_step(session, state, definition, sender, now=now)
        await session.commit()

    assert result is not None
    assert result.sent_step_key == "question_topic"
    assert result.next_step_key == "social"
    assert result.next_run_at == now + timedelta(minutes=5)
    assert [button.text for button in sender.sent[0].step.buttons] == ["Деньги"]

    async with async_session_maker() as session:
        persisted_state = await session.get(FunnelState, state.id)
        assert persisted_state is not None
        assert persisted_state.current_step_key == "social"
        assert persisted_state.next_run_at == now + timedelta(minutes=5)
        assert persisted_state.metadata_["pending_question_key"] == "topic"
        assert persisted_state.metadata_["questionnaire_waiting_for_step_key"] == "social"


async def test_run_due_funnel_step_completes_after_last_step(
    prepare_database: None,
) -> None:
    lead_id = await create_test_lead()
    definition = build_definition()
    now = datetime(2026, 5, 28, 10, 0, tzinfo=UTC)
    sender = DryRunFunnelStepSender()

    async with async_session_maker() as session:
        state = await start_funnel_for_lead(
            session,
            lead_id,
            definition,
            channel="telegram",
            now=now,
        )
        await run_due_funnel_step(session, state, definition, sender, now=now)
        second_run_at = datetime(2026, 5, 29, 6, 0, tzinfo=UTC)
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
