# tools.md

## Harness Roles

### Planner

Clarify scope, success criteria, risks, dependencies, and feature state.

### Implementer

Make the smallest complete change, follow repo patterns, avoid unrelated refactors, keep WIP = 1.

### Verifier

Run applicable checks, report exact results, explain skipped checks, update progress/handoff.

## Standard Commands

- Lint: `ruff check .`
- Type check: `mypy src`
- Unit tests: `pytest -x`
- E2E smoke: `pytest tests/e2e -x`
