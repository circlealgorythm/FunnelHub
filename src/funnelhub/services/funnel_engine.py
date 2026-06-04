from __future__ import annotations

import json
import uuid
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Any, Literal, Protocol

import yaml
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.db.models import FunnelState

SUPPORTED_CHANNELS = {"messenger", "telegram", "vk", "email"}
FUNNEL_LOCAL_TIMEZONE = timezone(timedelta(hours=3), name="Europe/Moscow")
DAILY_FUNNEL_SEND_TIME = time(hour=9)


class FunnelButton(BaseModel):
    text: str = Field(min_length=1, max_length=255)
    url: str | None = Field(default=None, min_length=1, max_length=2048)


class FunnelQuestionOption(BaseModel):
    key: str = Field(min_length=1, max_length=255)
    text: str = Field(min_length=1, max_length=255)


class FunnelQuestion(BaseModel):
    key: str = Field(min_length=1, max_length=255)
    text: str = Field(min_length=1)
    options: list[FunnelQuestionOption] = Field(min_length=1)
    reminder_delay: str = Field(default="5m")

    @field_validator("reminder_delay")
    @classmethod
    def validate_reminder_delay(cls, value: str) -> str:
        parse_delay(value)
        return value


class FunnelQuestionnaire(BaseModel):
    questions: dict[str, FunnelQuestion] = Field(default_factory=dict)
    personalized_responses: dict[str, dict[str, str]] = Field(default_factory=dict)


class FunnelStep(BaseModel):
    key: str = Field(min_length=1, max_length=255)
    delay: str = Field(default="0m")
    channel: Literal["messenger", "telegram", "vk", "email"]
    kind: Literal["message", "question"] = "message"
    question_key: str | None = Field(default=None, min_length=1, max_length=255)
    subject: str | None = Field(default=None, min_length=1, max_length=255)
    text: str = Field(min_length=1)
    buttons: list[FunnelButton] = Field(default_factory=list)

    @field_validator("delay")
    @classmethod
    def validate_delay(cls, value: str) -> str:
        parse_delay(value)
        return value


class FunnelDefinition(BaseModel):
    key: str = Field(min_length=1, max_length=255)
    version: int = Field(default=1, ge=1)
    title: str | None = Field(default=None, max_length=512)
    questionnaire: FunnelQuestionnaire | None = None
    steps: list[FunnelStep] = Field(min_length=1)

    @field_validator("steps")
    @classmethod
    def validate_unique_step_keys(cls, value: list[FunnelStep]) -> list[FunnelStep]:
        keys = [step.key for step in value]
        if len(keys) != len(set(keys)):
            raise ValueError("Funnel step keys must be unique.")
        return value

    def step_index(self, step_key: str) -> int:
        for index, step in enumerate(self.steps):
            if step.key == step_key:
                return index
        raise ValueError(f"Unknown funnel step: {step_key}")


@dataclass(frozen=True)
class FunnelStepSend:
    lead_id: uuid.UUID
    funnel_key: str
    step: FunnelStep
    state_metadata: dict[str, Any] = field(default_factory=dict)


class FunnelStepSender(Protocol):
    async def send(self, payload: FunnelStepSend) -> None: ...


@dataclass
class DryRunFunnelStepSender:
    sent: list[FunnelStepSend] = field(default_factory=list)

    async def send(self, payload: FunnelStepSend) -> None:
        self.sent.append(payload)


@dataclass(frozen=True)
class FunnelRunResult:
    lead_id: uuid.UUID
    funnel_key: str
    sent_step_key: str
    status: str
    next_step_key: str | None
    next_run_at: datetime | None


def load_funnel_definition(path: str | Path) -> FunnelDefinition:
    file_path = Path(path)
    raw_text = file_path.read_text(encoding="utf-8")
    if file_path.suffix.lower() == ".json":
        raw_data = json.loads(raw_text)
    elif file_path.suffix.lower() in {".yml", ".yaml"}:
        raw_data = yaml.safe_load(raw_text)
    else:
        raise ValueError("Funnel definition must be a .json, .yml, or .yaml file.")

    if not isinstance(raw_data, dict):
        raise ValueError("Funnel definition must contain an object at the top level.")
    return FunnelDefinition.model_validate(raw_data)


async def start_funnel_for_lead(
    session: AsyncSession,
    lead_id: uuid.UUID,
    definition: FunnelDefinition,
    now: datetime | None = None,
) -> FunnelState:
    current_time = normalize_datetime(now)
    existing = await session.scalar(
        select(FunnelState).where(
            FunnelState.lead_id == lead_id,
            FunnelState.funnel_key == definition.key,
        )
    )
    if existing is not None:
        return existing

    first_step = definition.steps[0]
    state = FunnelState(
        id=uuid.uuid4(),
        lead_id=lead_id,
        funnel_key=definition.key,
        status="active",
        current_step_key=first_step.key,
        next_run_at=schedule_after_delay(current_time, first_step.delay),
        metadata_=build_state_metadata(definition=definition, step_index=0),
    )
    session.add(state)
    await session.flush()
    return state


async def get_due_funnel_states(
    session: AsyncSession,
    now: datetime | None = None,
    limit: int = 100,
    funnel_key: str | None = None,
) -> Sequence[FunnelState]:
    current_time = normalize_datetime(now)
    query = (
        select(FunnelState)
        .where(
            FunnelState.status == "active",
            FunnelState.next_run_at.is_not(None),
            FunnelState.next_run_at <= current_time,
        )
        .order_by(FunnelState.next_run_at.asc())
        .limit(limit)
    )
    if funnel_key is not None:
        query = query.where(FunnelState.funnel_key == funnel_key)

    result = await session.scalars(
        query,
    )
    return result.all()


async def run_due_funnel_step(
    session: AsyncSession,
    state: FunnelState,
    definition: FunnelDefinition,
    sender: FunnelStepSender,
    now: datetime | None = None,
) -> FunnelRunResult | None:
    current_time = normalize_datetime(now)
    if state.status != "active" or state.next_run_at is None or state.next_run_at > current_time:
        return None
    if state.current_step_key is None:
        complete_state(state, current_time)
        return None

    step_index = definition.step_index(state.current_step_key)
    step = definition.steps[step_index]
    send_step = step_with_question_option_buttons(definition, step)
    await sender.send(
        FunnelStepSend(
            lead_id=state.lead_id,
            funnel_key=definition.key,
            step=send_step,
            state_metadata=dict(state.metadata_ or {}),
        )
    )
    metadata = dict(state.metadata_ or {})
    if step.kind == "question" and step.question_key is not None:
        metadata["pending_question_key"] = step.question_key
        metadata["last_question_sent_at"] = current_time.isoformat()

    next_index = step_index + 1
    if next_index >= len(definition.steps):
        state.metadata_ = build_state_metadata(
            definition=definition,
            step_index=step_index,
            existing_metadata=metadata,
        )
        complete_state(state, current_time)
        await session.flush()
        return FunnelRunResult(
            lead_id=state.lead_id,
            funnel_key=state.funnel_key,
            sent_step_key=step.key,
            status=state.status,
            next_step_key=None,
            next_run_at=None,
        )

    next_step = definition.steps[next_index]
    state.current_step_key = next_step.key
    next_delay = next_step.delay
    if step.kind == "question" and step.question_key is not None:
        question = (
            definition.questionnaire.questions.get(step.question_key)
            if definition.questionnaire is not None
            else None
        )
        if question is not None:
            next_delay = question.reminder_delay
            metadata["questionnaire_waiting_for_step_key"] = next_step.key

    state.next_run_at = schedule_after_delay(current_time, next_delay)
    state.metadata_ = build_state_metadata(
        definition=definition,
        step_index=next_index,
        existing_metadata=metadata,
    )
    await session.flush()
    return FunnelRunResult(
        lead_id=state.lead_id,
        funnel_key=state.funnel_key,
        sent_step_key=step.key,
        status=state.status,
        next_step_key=next_step.key,
        next_run_at=state.next_run_at,
    )


def step_with_question_option_buttons(
    definition: FunnelDefinition,
    step: FunnelStep,
) -> FunnelStep:
    if step.kind != "question" or step.question_key is None or step.buttons:
        return step
    if definition.questionnaire is None:
        return step

    question = definition.questionnaire.questions.get(step.question_key)
    if question is None:
        return step

    return step.model_copy(
        update={
            "buttons": [FunnelButton(text=option.text) for option in question.options],
        }
    )


def complete_state(state: FunnelState, completed_at: datetime) -> None:
    state.status = "completed"
    state.current_step_key = None
    state.next_run_at = None
    state.completed_at = completed_at


def build_state_metadata(
    definition: FunnelDefinition,
    step_index: int,
    existing_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata = dict(existing_metadata or {})
    metadata.update(
        {
        "definition_version": definition.version,
        "step_index": step_index,
        }
    )
    return metadata


def parse_delay(value: str) -> timedelta:
    if len(value) < 2:
        raise ValueError("Delay must look like 10m, 2h, or 1d.")

    amount_text = value[:-1]
    unit = value[-1]
    if not amount_text.isdigit():
        raise ValueError("Delay amount must be a non-negative integer.")

    amount = int(amount_text)
    if unit == "m":
        return timedelta(minutes=amount)
    if unit == "h":
        return timedelta(hours=amount)
    if unit == "d":
        return timedelta(days=amount)
    raise ValueError("Delay unit must be one of: m, h, d.")


def schedule_after_delay(current_time: datetime, delay: str) -> datetime:
    normalized_time = normalize_datetime(current_time)
    parsed_delay = parse_delay(delay)
    if delay.endswith("d"):
        day_count = int(delay[:-1])
        local_time = normalized_time.astimezone(FUNNEL_LOCAL_TIMEZONE)
        target_date = local_time.date() + timedelta(days=day_count)
        target_local_time = datetime.combine(
            target_date,
            DAILY_FUNNEL_SEND_TIME,
            tzinfo=FUNNEL_LOCAL_TIMEZONE,
        )
        return target_local_time.astimezone(UTC)
    return normalized_time + parsed_delay


def normalize_datetime(value: datetime | None) -> datetime:
    if value is None:
        return datetime.now(UTC)
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value
