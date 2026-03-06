---
id: realtime-world-session-events
title: Build realtime event infrastructure for Juke World and live sessions
status: ready
priority: p1
owner: unassigned
area: platform
label: ALL/GENERAL
complexity: 5
updated_at: 2026-03-06
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
- **Transport provided by cli-phase2.** The WebSocket foundation
  (`backend/realtime/` app, `TokenAuthMiddleware`, `ProtocolTypeRouter` ASGI
  switch, `channels-redis` channel layer) is delivered by
  `tasks/cli-phase2-backend-websocket-transport.md` as reusable platform infra.
  That task ships with one narrow consumer (`PlaybackConsumer`) as a proving
  ground. This task inherits the transport and its scope shrinks to: adding
  `world.*` / `session.*` event types, the consumers + publisher hooks for
  them, and the web-side subscriptions. No transport strategy decisions left
  to make — WS via Django Channels, token-header auth, channel-layer pub/sub.
  See `docs/arch/cli-juke-terminal-architecture.md` §7 for the full transport
  design.
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
- Define `world.*` / `session.*` event schema and deliver one vertical slice
  (world points live update) on top of the cli-phase2 transport.
- Blockers:
- `cli-phase2-backend-ws-transport` provides `backend/realtime/`,
  `TokenAuthMiddleware`, and the ASGI switch. Soft blocker — this task could
  still own the transport if the CLI program stalls, but the preferred path is
  to inherit it.

