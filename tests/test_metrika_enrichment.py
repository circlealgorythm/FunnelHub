from __future__ import annotations

import uuid
from unittest.mock import MagicMock

from funnelhub.services.inbox_database import (
    XLSX_EXPORT_COLUMNS,
    DatabaseLeadDetail,
    DatabaseLeadSummary,
    build_lead_search_filter,
    xlsx_export_row,
)


def test_xlsx_export_columns_has_search_query_and_keyword():
    col_dict = dict(XLSX_EXPORT_COLUMNS)
    assert "search_query" in col_dict
    assert col_dict["search_query"] == "Поисковый запрос / Ключевое слово"
    # utm_term is no longer a duplicate column in export
    assert "utm_term" not in col_dict


def test_xlsx_export_row_uses_search_query():
    lead_id = uuid.uuid4()
    detail = DatabaseLeadDetail(
        lead=DatabaseLeadSummary(
            id=lead_id,
            getcourse_user_id=123,
            name="Иван",
            email="ivan@test.com",
            phone="+79991234567",
            country="Россия",
            city="Москва",
            source="yandex",
            status="open",
            telegram="@ivan",
            vk="id123",
            conversations_count=1,
            messages_count=1,
            created_at=MagicMock(isoformat=lambda: "2026-10-08T12:00:00"),
            updated_at=MagicMock(isoformat=lambda: "2026-10-08T12:00:00"),
        ),
        profile_fields=[],
        contacts=[],
        identities=[],
        external_ids=[],
        utm_snapshots=[
            {
                "source_kind": "form",
                "utm_source": "yandex",
                "utm_medium": "cpc",
                "utm_campaign": "campaign1",
                "utm_term": "---autotargeting",
                "search_query": "как стать ведьмой",
                "utm_content": "",
                "utm_group": "",
                "yclid": "123456",
                "metrika_client_id": "999888",
                "metrika_visit_id": "111",
                "device_fingerprint": "",
                "created_at": None,
            }
        ],
        custom_fields=[],
        consents=[],
        email_subscriptions=[],
        funnel_states=[],
        recent_messages=[],
        raw_getcourse_data={},
    )
    row = xlsx_export_row(detail)
    assert row["search_query"] == "как стать ведьмой"
    # Autotargeting string is replaced by the actual search query
    assert row["utm_term"] == "как стать ведьмой"


def test_xlsx_export_row_fallback_to_keyword_when_not_autotargeting():
    lead_id = uuid.uuid4()
    detail = DatabaseLeadDetail(
        lead=DatabaseLeadSummary(
            id=lead_id,
            getcourse_user_id=123,
            name="Иван",
            email="ivan@test.com",
            phone="+79991234567",
            country="Россия",
            city="Москва",
            source="yandex",
            status="open",
            telegram="@ivan",
            vk="id123",
            conversations_count=1,
            messages_count=1,
            created_at=MagicMock(isoformat=lambda: "2026-10-08T12:00:00"),
            updated_at=MagicMock(isoformat=lambda: "2026-10-08T12:00:00"),
        ),
        profile_fields=[],
        contacts=[],
        identities=[],
        external_ids=[],
        utm_snapshots=[
            {
                "source_kind": "form",
                "utm_source": "yandex",
                "utm_medium": "cpc",
                "utm_campaign": "campaign1",
                "utm_term": "духовные практики",
                "search_query": None,
                "utm_content": "",
                "utm_group": "",
                "yclid": "123456",
                "metrika_client_id": "999888",
                "metrika_visit_id": "111",
                "device_fingerprint": "",
                "created_at": None,
            }
        ],
        custom_fields=[],
        consents=[],
        email_subscriptions=[],
        funnel_states=[],
        recent_messages=[],
        raw_getcourse_data={},
    )
    row = xlsx_export_row(detail)
    # When manual keyword was specified and no separate search_query, fallback to keyword
    assert row["search_query"] == "духовные практики"
    assert row["utm_term"] == "духовные практики"


def test_build_lead_search_filter_structure():
    filter_expr = build_lead_search_filter("магия")
    assert filter_expr is not None
