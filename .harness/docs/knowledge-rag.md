# Knowledge / RAG Layer

## Position In Roadmap

This is a planned later feature, not the next step.

Rational placement:

1. GetCourse webhook.
2. Bot linking.
3. Funnel engine and Telegram scenarios.
4. Email provider.
5. Simple inbox.
6. GetCourse import.
7. Manual broadcasts.
8. Knowledge/RAG layer.
9. Autoposting and production hardening.

RAG becomes useful only after FunnelHub has a real corpus of unstructured text: scenario messages, inbox conversations, product documents, objections, policies, offers, operator instructions, and broadcast copy.

## What RAG Is Not For

RAG must not be the primary way to query the operational database.

Structured data should be handled through:

- SQL queries;
- read-only tools;
- admin APIs;
- reports;
- filters.

Examples of structured data:

- leads;
- contacts;
- consents;
- statuses;
- subscriptions;
- messenger identities;
- funnel states;
- events;
- message metadata.

## What RAG Is For

RAG is for unstructured knowledge search and future agent assistance:

- funnel scenario texts;
- customer messages and inbox conversations;
- product knowledge;
- customer objections;
- documents, offers, and policies;
- operator instructions;
- draft replies for inbox agents.

## MVP Architecture Choice

Use PostgreSQL + `pgvector` when implementing this feature.

Do not add Pinecone, Qdrant, Milvus, or another vector database for MVP unless scale or operational constraints later justify it. PostgreSQL is already part of the stack and is enough for the expected initial corpus.

## Future Schema Shape

Keep knowledge/search separate from the core lead tables.

Expected future additions:

- PostgreSQL extension: `vector`;
- `knowledge_documents`;
- `knowledge_chunks`;
- embedding vector column;
- metadata fields such as:
  - `source`;
  - `lead_id`;
  - `message_id`;
  - `document_id`;
  - `visibility`;
  - `created_at`.

The exact schema should be designed when the first real text corpus exists.
