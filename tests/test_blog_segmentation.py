from __future__ import annotations

import uuid
from datetime import UTC, datetime

from sqlalchemy.dialects import postgresql

from funnelhub.api.inbox import DatabaseLeadResponse
from funnelhub.api.webhooks import AisuLandingApplicationRequest
from funnelhub.config import Settings
from funnelhub.db.models import Lead, LeadCustomField
from funnelhub.services.getcourse_webhook import (
    ADDITIONAL_FIELD_LABELS,
    KNOWN_ADDITIONAL_FIELD_ALIASES,
    human_custom_field_label,
)
from funnelhub.services.inbox_database import (
    XLSX_EXPORT_COLUMNS,
    DatabaseLeadSummary,
    apply_database_leads_ordering,
    build_lead_summary_query,
    extract_quiz_detail,
    lead_exclude_source_filter,
)
from funnelhub.services.lead_notifications import build_lead_notification_text
from funnelhub.services.lead_post_submit_tasks import _consultation_contact_signature


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


def test_blog_application_leaves_quiz_status_none_and_hides_empty_quiz() -> None:
    req = AisuLandingApplicationRequest(
        name="Анна",
        phone="+79991112233",
        email="anna@example.com",
        form_type="consultation",
        source="blog",
    )
    assert req.quiz_status is None

    lead_id = uuid.uuid4()
    blog_false_completed = [
        LeadCustomField(
            id=uuid.uuid4(),
            lead_id=lead_id,
            field_key="quiz_status",
            value="completed",
        )
    ]
    assert extract_quiz_detail(blog_false_completed, {}, lead_source="blog") is None
    assert extract_quiz_detail(blog_false_completed, {}, lead_source="aisu") is None


def test_extract_quiz_detail_draft_overrides_old_answers_and_completed_keeps_all() -> None:
    lead_id = uuid.uuid4()
    fields = [
        LeadCustomField(id=uuid.uuid4(), lead_id=lead_id, field_key="quiz_status", value="draft"),
        LeadCustomField(
            id=uuid.uuid4(), lead_id=lead_id, field_key="quiz_messenger", value="Telegram"
        ),
        LeadCustomField(id=uuid.uuid4(), lead_id=lead_id, field_key="quiz_known", value="Да"),
        LeadCustomField(id=uuid.uuid4(), lead_id=lead_id, field_key="quiz_goal", value="Да"),
        LeadCustomField(id=uuid.uuid4(), lead_id=lead_id, field_key="quiz_training", value="Да"),
    ]
    draft_quiz = extract_quiz_detail(fields, {}, lead_source="aisu")
    assert draft_quiz is not None
    assert draft_quiz["status"] == "draft"
    assert draft_quiz["is_completed"] is False
    assert draft_quiz["messenger"] is None
    assert draft_quiz["training"] is None

    fields[0].value = "completed"
    completed_quiz = extract_quiz_detail(fields, {}, lead_source="aisu")
    assert completed_quiz is not None
    assert completed_quiz["status"] == "completed"
    assert completed_quiz["is_completed"] is True
    assert completed_quiz["messenger"] == "Telegram"
    assert completed_quiz["training"] == "Да"


def test_apply_database_leads_ordering_uses_greatest_with_live_events_and_tasks() -> None:
    statement = apply_database_leads_ordering(build_lead_summary_query())
    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )
    assert "greatest(" in compiled.lower()
    assert "landing.application.received" in compiled
    assert "getcourse_consultation_submission" in compiled


def test_notification_text_includes_quiz_answers_only_for_completed_quiz() -> None:
    settings = Settings(_env_file=None)
    lead = Lead(
        id=uuid.uuid4(),
        full_name="Мария",
        source="aisu",
        raw_getcourse_data={},
    )
    quiz_text = build_lead_notification_text(
        lead=lead,
        contacts={"phone": "+79990001122", "email": "maria@example.com"},
        created=True,
        source="aisu",
        settings=settings,
        quiz={
            "status": "completed",
            "is_completed": True,
            "messenger": "Telegram, WhatsApp",
            "known": "Да",
            "goal": "Да",
            "training": "Нет",
        },
    )
    assert "Анкета консультации:" in quiz_text
    assert "1. Удобный мессенджер: Telegram, WhatsApp" in quiz_text
    assert "4. Желание обучаться тонкому плану: Нет" in quiz_text
    assert "Форма: consultation" in quiz_text

    blog_text = build_lead_notification_text(
        lead=lead,
        contacts={"phone": "+79990001122", "email": "maria@example.com"},
        created=True,
        source="blog",
        settings=settings,
        quiz=None,
    )
    assert "Анкета консультации:" not in blog_text


def test_consultation_contact_signature_normalizes_variants() -> None:
    sig1 = _consultation_contact_signature("  Анна ", "+7 (999) 123-45-67", "Anna@Example.COM ")
    sig2 = _consultation_contact_signature("анна", "89991234567", "anna@example.com")
    assert sig1 == sig2
