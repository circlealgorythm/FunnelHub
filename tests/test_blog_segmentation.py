from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.dialects import postgresql

from funnelhub.api.inbox import DatabaseLeadResponse
from funnelhub.api.webhooks import AisuLandingApplicationRequest
from funnelhub.services.getcourse_webhook import (
    ADDITIONAL_FIELD_LABELS,
    KNOWN_ADDITIONAL_FIELD_ALIASES,
    human_custom_field_label,
)
from funnelhub.services.inbox_database import (
    XLSX_EXPORT_COLUMNS,
    DatabaseLeadSummary,
    build_lead_summary_query,
    lead_exclude_source_filter,
)


def test_aisu_landing_request_supports_blog_and_article() -> None:
    req = AisuLandingApplicationRequest(
        name="Елена",
        phone="+79991234567",
        email="elena@example.com",
        form_type="consultation",
        smartcaptcha_token="token_xyz",
        source="blog",
        article_title="Васту для гармонии дома",
        article_url="/blog/vastu-dlya-doma",
    )
    assert req.source == "blog"
    assert req.article_title == "Васту для гармонии дома"
    assert req.article_url == "/blog/vastu-dlya-doma"


def test_article_fields_in_getcourse_aliases_and_labels() -> None:
    assert "article_title" in KNOWN_ADDITIONAL_FIELD_ALIASES
    assert "article_url" in KNOWN_ADDITIONAL_FIELD_ALIASES
    assert human_custom_field_label("article_title") == "Статья блога"
    assert human_custom_field_label("article_url") == "Ссылка на статью"
    assert ADDITIONAL_FIELD_LABELS["article_title"] == "Статья блога"


def test_lead_exclude_source_filter_multi_source() -> None:
    compiled_single = str(
        lead_exclude_source_filter("most-tsennostey").compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "most-tsennostey" in compiled_single

    compiled_multi = str(
        lead_exclude_source_filter("most-tsennostey,blog").compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "most-tsennostey" in compiled_multi
    assert "blog" in compiled_multi


def test_database_lead_summary_and_response_fields() -> None:
    now = datetime.now(UTC)
    summary = DatabaseLeadSummary(
        id=uuid.uuid4(),
        getcourse_user_id=12345,
        name="Мария",
        email="maria@example.com",
        phone="+79998887766",
        city="Москва",
        country="Россия",
        source="blog",
        status="new",
        created_at=now,
        updated_at=now,
        telegram=None,
        vk=None,
        conversations_count=1,
        messages_count=2,
        article_title="Карма и предназначение",
        article_url="/blog/karma-i-prednaznachenie",
    )
    assert summary.article_title == "Карма и предназначение"
    assert summary.article_url == "/blog/karma-i-prednaznachenie"

    response = DatabaseLeadResponse(
        id=summary.id,
        getcourse_user_id=summary.getcourse_user_id,
        name=summary.name,
        email=summary.email,
        phone=summary.phone,
        city=summary.city,
        country=summary.country,
        source=summary.source,
        article_title=summary.article_title,
        article_url=summary.article_url,
        status=summary.status,
        created_at=summary.created_at,
        updated_at=summary.updated_at,
        telegram=summary.telegram,
        vk=summary.vk,
        conversations_count=summary.conversations_count,
        messages_count=summary.messages_count,
    )
    assert response.source == "blog"
    assert response.article_title == "Карма и предназначение"
    assert response.article_url == "/blog/karma-i-prednaznachenie"


def test_xlsx_export_columns_include_article() -> None:
    keys = [k for k, _ in XLSX_EXPORT_COLUMNS]
    assert "article_title" in keys
    assert "article_url" in keys


def test_build_lead_summary_query_compilation() -> None:
    statement = build_lead_summary_query()
    compiled = str(statement.compile(dialect=postgresql.dialect()))
    assert "article_title" in compiled
    assert "article_url" in compiled
