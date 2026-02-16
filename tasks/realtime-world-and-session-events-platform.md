---
id: realtime-world-session-events
title: Build realtime event infrastructure for Juke World and live sessions
status: ready
priority: p1
owner: unassigned
area: platform
label: ALL/GENERAL
complexity: 5
updated_at: 2026-02-16
---

## Goal

Introduce a shared realtime event layer so Juke World and live session experiences update without polling-only behavior.

## Scope

- Define realtime transport strategy (WebSocket or SSE) and authentication model.
- Publish backend events for world profile updates, session lifecycle changes, and playback state transitions.
- Add web subscriptions for Juke World incremental updates and live session state refresh.
- Add client fallback strategy when realtime transport is unavailable.

## Out Of Scope

- Private messaging/chat.
- Full multiplayer game synchronization for every app.
- Third-party event bus migration.

## Acceptance Criteria

- Backend exposes authenticated realtime stream/channel for approved event types.
- Juke World can reflect live user/profile state changes without manual refresh.
- Session state updates propagate to connected clients within agreed latency SLO.
- Integration tests cover auth, event serialization, reconnect behavior, and fallback-to-polling.

## Execution Notes

- Idea rank: `#7`
- Portfolio classification: `experimental`
- Key files:
- `/Users/embario/Documents/juke/backend/settings/urls.py`
- `/Users/embario/Documents/juke/backend/juke_auth/views.py`
- `/Users/embario/Documents/juke/backend/catalog/views.py`
- `/Users/embario/Documents/juke/web/src/features/world/**`
- `/Users/embario/Documents/juke/web/src/features/**/hooks/**` (session consumers)
- Commands:
- `docker compose exec backend python manage.py test`
- `docker compose exec web npm test`
- Risks:
- Infrastructure overhead and connection fan-out under load.
- Event contract churn if canonical payloads are not frozen early.

## Handoff

- Completed:
- Task seeded for cross-surface realtime requirements that exceed current polling paths.
- Next:
- Select transport, define event schema, and deliver one vertical slice (world points live update).
- Blockers:

