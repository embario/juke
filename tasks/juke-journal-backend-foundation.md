---
id: juke-journal-backend-foundation
title: Juke Journal backend authentication, encrypted sync, and private AI boundaries
status: review
priority: p1
owner: codex
area: backend
label: BACKEND
complexity: 4
updated_at: 2026-08-31
---

## Goal

Provide the secure server contracts needed by the Juke Journal Mac client without storing plaintext journal prose.

## Scope

- PKCE-bound browser authorization-code exchange for `juke-journal-mac`.
- Account capability response and permission-gated chat.
- Metadata-only opening questions.
- Ciphertext-only, account-isolated, idempotent encrypted record sync and cursor feed.
- Public lightweight API health response.

## Out Of Scope

- Cross-device key wrapping or recovery.
- Enabling cloud AI for accounts without an explicit account-level decision.
- Production deployment or service restarts.

## Acceptance Criteria

- Authorization codes are short-lived, one-time, stored only as digests, redirect-allowlisted, and PKCE-bound.
- Journal endpoints require existing Juke token/session authentication and enforce account isolation.
- Unknown/private prose fields are rejected at the metadata and sync boundaries.
- Sync preserves the current Swift envelope shape and has repeatable cursor semantics.
- Focused tests cover replay, PKCE, expiry, isolation, idempotency, privacy boundaries, and capabilities.

## Execution Notes

- Key files: `backend/journal/`, `backend/tests/api/test_journal_api.py`, `backend/settings/{base,urls}.py`.
- Run: `docker compose exec backend python manage.py test tests.api.test_journal_api`.
- Risk: production HTTPS and database migration are prerequisites; verified sign-up and password reset intentionally require the user to return to the app and begin a fresh short-lived PKCE attempt.

## Handoff

- Completed: backend models, migration, serializers, routes, auth exchange, encrypted sync, prompt/chat boundaries, browser login/create/reset aliases and handoff, tests and web build.
- Next: apply migration and expose the existing web/backend stack on HTTPS at `neptune.tail647b75.ts.net` before enabling the client.
- Blockers: HTTPS port 443 is not currently accepting connections; production migration has deliberately not been applied.
