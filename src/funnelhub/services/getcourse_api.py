from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, cast

import httpx
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from funnelhub.config import Settings
from funnelhub.db.models import Lead, LeadContact, LeadExternalId
from funnelhub.services.getcourse_webhook import (
    ingest_getcourse_webhook,
    normalize_email,
    normalize_phone,
)

logger = logging.getLogger(__name__)
httpx_logger = logging.getLogger("httpx")


@dataclass(frozen=True)
class GetCourseProfileEnrichmentResult:
    attempted: bool
    updated: bool
    reason: str | None = None


async def enrich_lead_from_getcourse_api(
    *,
    session: AsyncSession,
    settings: Settings,
    lead_id: Any,
    http_client: httpx.AsyncClient | None = None,
) -> GetCourseProfileEnrichmentResult:
    if not is_getcourse_api_configured(settings):
        return GetCourseProfileEnrichmentResult(attempted=False, updated=False)

    lead = await session.get(Lead, lead_id)
    if lead is None:
        return GetCourseProfileEnrichmentResult(
            attempted=False,
            updated=False,
            reason="lead_not_found",
        )
    if await lead_has_getcourse_vk_id(session, lead.id):
        return GetCourseProfileEnrichmentResult(attempted=False, updated=False)

    contacts = await load_contacts(session, lead.id)
    filter_params = build_user_export_filter(lead, contacts)
    if not filter_params:
        return GetCourseProfileEnrichmentResult(
            attempted=False,
            updated=False,
            reason="no_supported_filter",
        )

    client = GetCourseExportClient(settings=settings, http_client=http_client)
    try:
        profile = await client.fetch_user_profile(filter_params)
    except Exception as exc:
        logger.warning("GetCourse profile enrichment failed: %s", exc)
        return GetCourseProfileEnrichmentResult(
            attempted=True,
            updated=False,
            reason="api_failed",
        )

    if profile is None:
        return GetCourseProfileEnrichmentResult(
            attempted=True,
            updated=False,
            reason="profile_not_found",
        )

    await ingest_getcourse_webhook(session, profile)
    return GetCourseProfileEnrichmentResult(attempted=True, updated=True)


def is_getcourse_api_configured(settings: Settings) -> bool:
    return bool(settings.getcourse_api_base_url and settings.getcourse_api_key)


async def lead_has_getcourse_vk_id(session: AsyncSession, lead_id: Any) -> bool:
    existing = await session.scalar(
        select(LeadExternalId.id).where(
            LeadExternalId.lead_id == lead_id,
            LeadExternalId.provider == "getcourse_vk_id",
        )
    )
    return existing is not None


async def load_contacts(session: AsyncSession, lead_id: Any) -> dict[str, str]:
    contacts = (
        await session.scalars(
            select(LeadContact).where(LeadContact.lead_id == lead_id)
        )
    ).all()
    result: dict[str, str] = {}
    for contact in contacts:
        result.setdefault(contact.contact_type, contact.value)
    return result


def build_user_export_filter(lead: Lead, contacts: dict[str, str]) -> dict[str, str]:
    email = contacts.get("email")
    if email and not is_getcourse_technical_email(email):
        return {"email": email}

    phone = contacts.get("phone")
    if phone:
        return {"phone": phone}

    return {}


def is_getcourse_technical_email(email: str) -> bool:
    return normalize_email(email).endswith("@vktech.gc")


class GetCourseExportClient:
    def __init__(
        self,
        *,
        settings: Settings,
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        if not settings.getcourse_api_base_url or not settings.getcourse_api_key:
            raise ValueError("GetCourse API is not configured.")
        self._base_url = settings.getcourse_api_base_url.rstrip("/")
        self._api_key = settings.getcourse_api_key
        self._poll_attempts = max(settings.getcourse_api_poll_attempts, 1)
        self._poll_interval = max(settings.getcourse_api_poll_interval_seconds, 0.0)
        self._http_client = http_client

    async def fetch_user_profile(self, filter_params: dict[str, str]) -> dict[str, Any] | None:
        export_id = await self._start_users_export(filter_params)
        export_payload = await self._poll_export(export_id)
        if export_payload is None:
            return None

        rows = parse_export_rows(export_payload)
        if not rows:
            return None
        return select_matching_profile(rows, filter_params)

    async def _start_users_export(self, filter_params: dict[str, str]) -> str:
        payload = await self._get_json(
            f"{self._base_url}/pl/api/account/users",
            params=filter_params,
        )
        if payload.get("success") is not True:
            raise RuntimeError(str(payload.get("error_message") or "users export failed"))

        info = payload.get("info")
        export_id = info.get("export_id") if isinstance(info, dict) else None
        if not isinstance(export_id, int | str):
            raise RuntimeError("GetCourse users export response has no export_id.")
        return str(export_id)

    async def _poll_export(self, export_id: str) -> dict[str, Any] | None:
        for attempt in range(self._poll_attempts):
            if attempt > 0 and self._poll_interval > 0:
                await asyncio.sleep(self._poll_interval)

            payload = await self._get_json(f"{self._base_url}/pl/api/account/exports/{export_id}")
            if payload.get("success") is True:
                return payload
            error_code = payload.get("error_code")
            if error_code != 909:
                raise RuntimeError(str(payload.get("error_message") or "export failed"))
        return None

    async def _get_json(self, url: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        request_params = {"key": self._api_key, **(params or {})}
        previous_httpx_level = httpx_logger.level
        httpx_logger.setLevel(logging.WARNING)
        try:
            if self._http_client is not None:
                response = await self._http_client.get(url, params=request_params)
            else:
                async with httpx.AsyncClient(timeout=20.0, follow_redirects=True) as client:
                    response = await client.get(url, params=request_params)
        finally:
            httpx_logger.setLevel(previous_httpx_level)
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise RuntimeError("GetCourse API returned non-object JSON.")
        return cast(dict[str, Any], data)


def parse_export_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    info = payload.get("info")
    if not isinstance(info, dict):
        return []

    fields = info.get("fields")
    items = info.get("items")
    if not isinstance(items, list):
        return []

    field_names = normalize_export_fields(fields)
    rows: list[dict[str, Any]] = []
    for item in items:
        if isinstance(item, dict):
            rows.append(dict(item))
        elif isinstance(item, list) and field_names:
            rows.append(
                {
                    field_names[index]: value
                    for index, value in enumerate(item)
                    if index < len(field_names)
                }
            )
    return rows


def normalize_export_fields(fields: Any) -> list[str]:
    if not isinstance(fields, list):
        return []

    result: list[str] = []
    for index, field in enumerate(fields):
        label: str | None
        if isinstance(field, str):
            label = field
        elif isinstance(field, dict):
            label = first_string_field(field, ("label", "title", "name", "key", "id"))
        else:
            label = None
        result.append(label or str(index))
    return result


def first_string_field(payload: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, int):
            return str(value)
    return None


def select_matching_profile(
    rows: list[dict[str, Any]],
    filter_params: dict[str, str],
) -> dict[str, Any] | None:
    for row in rows:
        normalized = normalize_export_row(row)
        if row_matches_filter(normalized, filter_params):
            return normalized
    return normalize_export_row(rows[0]) if rows else None


def normalize_export_row(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    alias_pairs = {
        "id": ("id", "ID", "ID пользователя", "User ID"),
        "gc_user_id": ("gc_user_id", "getcourse_user_id"),
        "email": ("email", "Email", "E-mail"),
        "phone": ("phone", "Телефон", "Phone"),
        "name": ("name", "ФИО", "Имя", "Имя пользователя"),
        "first_name": ("first_name", "Имя"),
        "last_name": ("last_name", "Фамилия"),
        "vk_id": (
            "vk_id",
            "VK-ID",
            "VK ID",
            "ID VK",
            "ВК-ID",
            "ID ВК",
            "ID ВКонтакте",
        ),
    }
    for target, aliases in alias_pairs.items():
        for alias in aliases:
            value = row.get(alias)
            if value not in (None, ""):
                normalized[target] = value
                break
    return normalized


def row_matches_filter(row: dict[str, Any], filter_params: dict[str, str]) -> bool:
    email = filter_params.get("email")
    if email and normalize_email(str(row.get("email") or "")) == normalize_email(email):
        return True

    phone = filter_params.get("phone")
    if phone and normalize_phone(str(row.get("phone") or "")) == normalize_phone(phone):
        return True

    user_id = filter_params.get("id")
    if user_id and str(row.get("id") or row.get("gc_user_id") or "").strip() == user_id:
        return True

    return False
