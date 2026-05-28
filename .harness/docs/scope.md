# Scope

## In MVP

- FastAPI backend.
- PostgreSQL lead database.
- Redis-backed job processing.
- GetCourse webhook ingestion.
- Telegram/VK bot linking.
- Basic scheduled funnel sequence.
- Email provider integration.
- Simple mobile inbox.
- CSV/XLSX import from GetCourse.
- Manual broadcasts.

## Out of MVP

- Replacing GetCourse courses, payments, installments, access, or student cabinet.
- Full CRM/helpdesk.
- React admin frontend.
- Direct Gmail-based mass mailing.
- Max production integration unless bot API access is confirmed.
- Full agent/RAG implementation before there is a real corpus of scenario texts, inbox messages, documents, and customer objections.

## Planned Later

- Knowledge/RAG layer for unstructured knowledge using PostgreSQL + pgvector.
- Agent assistance in inbox based on product knowledge, objections, policies, offers, instructions, scenarios, and message history.
- Structured lead operations must remain SQL/API/report driven, not RAG-driven.
