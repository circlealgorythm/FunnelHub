from __future__ import annotations

import io

import pytest
from httpx import ASGITransport, AsyncClient
from openpyxl import Workbook

from funnelhub.main import app
from funnelhub.services.auth import AuthenticatedAdmin, require_admin_session
from funnelhub.services.inbox_database import (
    MAX_IMPORT_FILE_SIZE_BYTES,
    MAX_IMPORT_ROWS,
    preview_import_file,
    read_import_file_rows,
)


def create_test_csv(row_count: int, trailing_empty: int = 0) -> bytes:
    lines = ["name,email,phone"]
    for i in range(1, row_count + 1):
        lines.append(f"User {i},user{i}@example.com,+7999000{i:04d}")
    for _ in range(trailing_empty):
        lines.append("   ,  , ")
    return "\n".join(lines).encode("utf-8")


def create_test_xlsx(row_count: int, trailing_empty: int = 0) -> bytes:
    wb = Workbook()
    sheet = wb.active
    sheet.append(["name", "email", "phone"])
    for i in range(1, row_count + 1):
        sheet.append([f"User {i}", f"user{i}@example.com", f"+7999000{i:04d}"])
    for _ in range(trailing_empty):
        sheet.append(["", "", ""])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_import_caps_constants_exist():
    assert MAX_IMPORT_FILE_SIZE_BYTES == 10 * 1024 * 1024
    assert MAX_IMPORT_ROWS == 5000


def test_read_import_file_rows_rejects_oversized_file():
    small_limit = 50
    content = b"x" * 51
    with pytest.raises(ValueError, match="Размер файла превышает допустимый лимит"):
        read_import_file_rows("leads.csv", content, max_file_size_bytes=small_limit)


def test_read_import_file_rows_rejects_csv_exceeding_max_rows():
    content = create_test_csv(6)
    with pytest.raises(ValueError, match="Файл содержит более 5 строк"):
        read_import_file_rows("leads.csv", content, max_rows=5)


def test_read_import_file_rows_accepts_csv_within_limit_and_ignores_empty_trailing_rows():
    content = create_test_csv(5, trailing_empty=3)
    headers, rows, delimiter = read_import_file_rows("leads.csv", content, max_rows=5)
    assert headers == ["name", "email", "phone"]
    assert len(rows) == 5
    assert rows[0][0] == "User 1"
    assert rows[4][0] == "User 5"


def test_read_import_file_rows_rejects_xlsx_exceeding_max_rows():
    content = create_test_xlsx(6)
    with pytest.raises(ValueError, match="Файл содержит более 5 строк"):
        read_import_file_rows("leads.xlsx", content, max_rows=5)


def test_read_import_file_rows_accepts_xlsx_within_limit_and_ignores_empty_trailing_rows():
    content = create_test_xlsx(5, trailing_empty=2)
    headers, rows, delimiter = read_import_file_rows("leads.xlsx", content, max_rows=5)
    assert headers == ["name", "email", "phone"]
    assert len(rows) == 5
    assert rows[0][0] == "User 1"
    assert rows[4][0] == "User 5"


def test_preview_import_file_enforces_caps():
    content = create_test_csv(10)
    with pytest.raises(ValueError, match="Файл содержит более 5 строк"):
        preview_import_file("leads.csv", content, max_rows=5)

    valid_content = create_test_csv(5)
    preview = preview_import_file("leads.csv", valid_content, max_rows=5)
    assert preview.headers == ["name", "email", "phone"]
    assert len(preview.rows) == 5
    assert preview.suggested_mapping["name"] == "name"
    assert preview.suggested_mapping["email"] == "email"
    assert preview.suggested_mapping["phone"] == "phone"


@pytest.mark.asyncio
async def test_api_preview_returns_413_for_oversized_file(monkeypatch):
    app.dependency_overrides[require_admin_session] = lambda: AuthenticatedAdmin("aisu")
    try:
        # Патчим лимит на маленький для быстрого теста
        import funnelhub.api.inbox as inbox_api
        monkeypatch.setattr(inbox_api, "MAX_IMPORT_FILE_SIZE_BYTES", 50)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
        ) as client:
            files = {"file": ("leads.csv", b"a" * 51, "text/csv")}
            response = await client.post("/api/inbox/database/leads/import/preview", files=files)
            assert response.status_code == 413
            assert "Размер файла превышает допустимый лимит" in response.json()["detail"]
    finally:
        app.dependency_overrides.pop(require_admin_session, None)


@pytest.mark.asyncio
async def test_api_preview_returns_422_when_rows_exceed_cap(monkeypatch):
    app.dependency_overrides[require_admin_session] = lambda: AuthenticatedAdmin("aisu")
    try:
        import funnelhub.services.inbox_database as inbox_db
        monkeypatch.setattr(inbox_db, "MAX_IMPORT_ROWS", 3)

        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
        ) as client:
            content = create_test_csv(5)
            files = {"file": ("leads.csv", content, "text/csv")}
            response = await client.post("/api/inbox/database/leads/import/preview", files=files)
            assert response.status_code == 422
            assert "Файл содержит более 3 строк" in response.json()["detail"]
    finally:
        app.dependency_overrides.pop(require_admin_session, None)


@pytest.mark.asyncio
async def test_api_preview_succeeds_within_caps():
    app.dependency_overrides[require_admin_session] = lambda: AuthenticatedAdmin("aisu")
    try:
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://127.0.0.1:8000",
        ) as client:
            content = create_test_csv(5)
            files = {"file": ("leads.csv", content, "text/csv")}
            response = await client.post("/api/inbox/database/leads/import/preview", files=files)
            assert response.status_code == 200
            data = response.json()
            assert data["headers"] == ["name", "email", "phone"]
            assert len(data["rows"]) == 5
    finally:
        app.dependency_overrides.pop(require_admin_session, None)
