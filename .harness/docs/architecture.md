# Architecture Notes

## Source of Truth

GetCourse: courses, payments, installments, course access, login/password issuance, student cabinet, temporary manual work with leads.

FunnelHub server: persistent lead database, Telegram/VK subscribers, future Max subscribers, email subscribers, communication history, funnel state, inbox, imports, broadcasts, analytics.

## Target Flow

```text
GetCourse form
-> GetCourse creates/updates user and issues login/password
-> GetCourse calls FunnelHub webhook
-> FunnelHub stores/updates lead and generates bot-start token
-> User redirects to thank-you / bot choice page
-> Telegram/VK bot links messenger account to lead
-> FunnelHub controls bot/email communication
```

## Non-Negotiable Constraint

Deleting a non-buyer from GetCourse must not remove the ability to communicate with that person from FunnelHub, provided the person is still subscribed and legally allowed to receive messages.

## Future Knowledge / RAG Layer

RAG is not the primary access path for operational lead data.

Structured data such as leads, contacts, consents, statuses, messages, subscriptions, funnel states, and events should be accessed through SQL, read-only tools, admin APIs, reports, and filters.

RAG should be reserved for unstructured knowledge:

- funnel scenario texts;
- inbox conversations and message bodies;
- product knowledge;
- customer objections;
- offers, policies, and documents;
- operator instructions;
- future agent answer drafts in inbox.

When this feature becomes rational to implement, prefer PostgreSQL + `pgvector` over a separate vector database for MVP. The project already depends on PostgreSQL, so a separate Pinecone/Qdrant/Milvus service should be avoided unless scale or operations later require it.

Keep this layer separate from the core lead schema. A future implementation should introduce dedicated knowledge/search tables, for example `knowledge_documents` and `knowledge_chunks`, with embedding vectors and metadata such as `source`, `lead_id`, `message_id`, `document_id`, `visibility`, and timestamps.
