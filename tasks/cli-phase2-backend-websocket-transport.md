---
id: cli-phase2-backend-ws-transport
title: Juke CLI Phase 2 - Backend WebSocket transport (realtime/ app + ASGI)
status: ready
priority: p1
owner: unassigned
area: backend
label: BACKEND
labels:
  - juke-task
  - cli
  - backend
  - realtime
  - asgi
complexity: 3
updated_at: 2026-03-06
---

## Goal

Switch the Django backend from WSGI to ASGI (gunicorn stays, worker class swaps
to uvicorn) and deliver a narrow `backend/realtime/` app with one authenticated
consumer: `PlaybackConsumer` on `ws/v1/playback/`. The daemon from cli-phase1
will subscribe to this in cli-phase3. This is the **reusable WS transport
foundation** — `realtime-world-session-events` and the future DM backend add
event types on top of the same `TokenAuthMiddleware` + channel-layer wiring.

## Scope

- `backend/requirements.txt`: `+channels`, `+channels-redis`, `+uvicorn[standard]`,
  `+daphne` (daphne is dev-only, for `runserver` hijack).
- `backend/settings/base.py`: add `daphne` + `channels` to `INSTALLED_APPS`
  (daphne must be above `django.contrib.staticfiles`); add `ASGI_APPLICATION`;
  add `CHANNEL_LAYERS` pointing `channels_redis.core.RedisChannelLayer` at the
  existing Redis broker (`CELERY_BROKER_URL` host, separate DB number).
- `backend/settings/asgi.py`: rewrite the existing stock skeleton into a
  `ProtocolTypeRouter` with `"http"` → `get_asgi_application()` and
  `"websocket"` → `TokenAuthMiddleware(URLRouter(...))`.
- `backend/realtime/` new app:
  - `apps.py`
  - `middleware.py` — `TokenAuthMiddleware`. Reads `Authorization: Token <key>`
    from WS handshake headers, resolves `rest_framework.authtoken.models.Token`,
    sets `scope["user"]`. Anonymous on miss.
  - `consumers.py` — `PlaybackConsumer(AsyncJsonWebsocketConsumer)`. Group
    `playback_{user.id}`. `connect()` rejects anonymous with close code 4401.
    `receive_json` handles a `{"type": "sync"}` request by calling
    `PlaybackService(...).state()` via `database_sync_to_async`. Group handler
    `playback_state_changed` forwards to `send_json`.
  - `routing.py` — `websocket_urlpatterns` with one `re_path`.
- `backend/catalog/services/playback.py`: add `_publish(state)` helper. Sync
  `def`, uses `async_to_sync(get_channel_layer().group_send)(...)`. Called at
  the tail of `play`/`pause`/`next`/`previous`/`seek`. No-op when channel layer
  is `None` (unset in some test configs).
- `backend/run_prod.sh`: change
  `gunicorn settings.wsgi:application --workers 3` →
  `gunicorn settings.asgi:application -k uvicorn.workers.UvicornWorker --workers 3`.
- `backend/run_dev.sh`: no change. `daphne` in `INSTALLED_APPS` hijacks
  `runserver` to serve ASGI.
- Tests: `backend/tests/unit/test_realtime_consumers.py` using
  `channels.testing.WebsocketCommunicator` + `InMemoryChannelLayer`. Cover
  auth-reject (4401), connect-sync-receive, and publish-fanout (two communicators
  on same user group both receive).

## Out Of Scope

- Any Go code. The daemon's WS client lands in cli-phase3.
- `world.*` or `session.*` event types. Those belong to
  `realtime-world-session-events`, which this task unblocks.
- `MessageConsumer`. That belongs to `backend-direct-messaging-foundation`.
- Server-side polling of Spotify for externally-initiated changes (the "honest
  gap" from arch doc §5). The daemon's own drift poller covers this.
- Load testing / connection fan-out tuning. Narrow proving ground first.

## Acceptance Criteria

- `docker compose exec backend python manage.py test` passes — **including every
  existing test**. The async containment guarantee (arch §2, decision 7) is that
  existing sync code is untouched and just runs in the ASGI HTTP handler's
  threadpool. If existing tests break, the containment failed.
- `docker compose up backend` comes up healthy with the uvicorn worker. HTTP
  routes (`/api/v1/playback/state/` etc.) return identical responses pre- and
  post-switch.
- `WebsocketCommunicator` tests demonstrate: connection rejected without token,
  connection accepted with valid token, `{"type": "sync"}` returns playback
  state, `PlaybackService._publish()` fans out to two connected communicators
  on the same user group.
- Manual check: with a running backend, a WS connection to
  `ws://127.0.0.1:8000/ws/v1/playback/` with `Authorization: Token <key>`
  receives a `{"type": "playback.state", "state": {...}}` frame after hitting
  `POST /api/v1/playback/pause/` via curl.

## Execution Notes

- Program linkage: phase2 of the `cli` program. This is the one Django phase.
  Depends on phase1 only for sequencing (the daemon exists, so there's a client
  to prove the transport works end-to-end in phase3).
- **This task delivers reusable platform infra.** When
  `realtime-world-session-events` picks up, it imports `TokenAuthMiddleware`
  from `realtime.middleware` and adds consumers + routes — no transport work.
- Read first:
  - `docs/arch/cli-juke-terminal-architecture.md` §7 (full `realtime/` code
    sketch — the consumer, middleware, routing, asgi.py rewrite, and publisher
    hook are all written out there) and §7.2 (async containment boundary).
  - `backend/settings/asgi.py` (17-line stock skeleton — gets rewritten).
  - `backend/run_prod.sh:17` (the one-line gunicorn change).
  - `backend/settings/base.py:157-167` (MIDDLEWARE — all stock Django +
    whitenoise + corsheaders, all already async-compatible, nothing to change).
  - `backend/catalog/services/playback.py` (where `_publish` lands).
- Key files:
  - `backend/requirements.txt`
  - `backend/settings/base.py`
  - `backend/settings/asgi.py`
  - `backend/realtime/{__init__,apps,middleware,consumers,routing}.py`
  - `backend/catalog/services/playback.py`
  - `backend/run_prod.sh`
  - `backend/tests/unit/test_realtime_consumers.py`
- Commands:
  - `docker compose build backend` (new deps)
  - `docker compose exec backend python manage.py test`
  - `docker compose exec backend python manage.py test tests.unit.test_realtime_consumers`
  - Manual WS probe: `websocat -H "Authorization: Token <key>" ws://127.0.0.1:8000/ws/v1/playback/`
- Risks:
  - `get_asgi_application()` **must be called before importing consumers**
    (Django apps registry must be populated before model imports resolve).
    The arch doc asgi.py sketch gets this ordering right — don't reorder it.
  - `channels-redis` wants a separate Redis DB from Celery. Reuse the broker
    host/port but bump the DB index (`redis://redis:6379/1`) so channel-layer
    keys and Celery queue keys don't share a keyspace.
  - The publisher hook's `async_to_sync` opens a new event loop per call if
    there isn't one running. That's fine for the publish path (called from sync
    views) but don't call `_publish` from inside an already-async context — use
    the channel layer directly there.
  - Some older Django tests use `TransactionTestCase` with `serialized_rollback`.
    `InMemoryChannelLayer` in tests avoids Redis, but the consumer's
    `database_sync_to_async` still hits the test DB. Test setup may need
    `@pytest.mark.django_db(transaction=True)` or equivalent.

## Handoff

- Completed:
- Next:
  - cli-phase3 wires the daemon's `internal/transport/ws.go` WS client to this
    endpoint and swaps transport priority to WS-first.
  - `realtime-world-session-events` can now start — its scope shrinks to adding
    `world.*`/`session.*` event types + consumers on top of this transport.
- Blockers:
  - `cli-phase1-daemon-ipc-auth` should be `review`/`done` for sequencing.
    (Soft blocker — technically this backend work is independent, but phase3
    needs both sides ready.)
