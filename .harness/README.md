# FunnelHub Harness Workspace

FunnelHub is an MVP server-side communication system for an online-course funnel around GetCourse.

GetCourse remains responsible for courses, payments, installments, access, login/password issuance, and the student cabinet. FunnelHub owns long-term communication: lead database, Telegram/VK bots, future Max channel, email sequences, inbox, imports, broadcasts, funnel state, and analytics.

## Harness-engineering

1. Repo is the source of truth.
2. WIP = 1.
3. Start every session with `.harness/init.md`.
4. Work through Planner -> Implementer -> Verifier.
5. Update `.harness/progress.md` and `.harness/session-handoff.md` at the end of the session.
6. Do not claim done without applicable verification results.

## Cold Start Questions

1. What stays in GetCourse?
2. What is our server the source of truth for?
3. What is the MVP stack?
4. What is currently in scope and out of scope?
5. Which verification commands apply?
