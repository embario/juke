---
id: cli-phase2-backend-ws-transport
title: Juke CLI Phase 2 — Backend WebSocket transport (realtime/ app + ASGI)
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
updated_at: 2026-06-10
---

## Goal

Switch the Django backend from WSGI to ASGI and deliver a narrow
`backend/realtime/` app with one authenticated consumer: `PlaybackConsumer`
on `ws/v1/playback/`. The Go daemon from cli-phase1b will subscribe to this
in cli-phase3.

This is reusable platform infrastructure. Every future real-time feature
(`realtime-world-session-events`, `backend-direct-messaging-foundation`)
imports `TokenAuthMiddleware` from `realtime.middleware` and adds consumers
and routes on top — no transport work needed.

End state: a running backend where `websocat -H "Authorization: Token <key>"
ws://127.0.0.1:8000/ws/v1/playback/` connects successfully and receives a
`{"type": "playback.state", "state": {...}}` frame after any playback command
is issued — while every existing HTTP test continues to pass unchanged.

---

## Scope

**Dependencies (`backend/requirements.txt`):**
- `+channels` — Django Channels core
- `+channels-redis` — Redis channel layer backend
- `+daphne` — dev-only; hijacks `runserver` to serve ASGI
- `+uvicorn[standard]` — production ASGI server (replaces WSGI in gunicorn)

**Settings (`backend/settings/base.py`):**
- Add `daphne` to `INSTALLED_APPS` above `django.contrib.staticfiles`
  (required for runserver hijack to work correctly).
- Add `channels` to `INSTALLED_APPS`.
- Add `ASGI_APPLICATION = "settings.asgi.application"`.
- Add `CHANNEL_LAYERS` pointing to `channels_redis.core.RedisChannelLayer`
  at `redis://redis:6379/1` (DB 1 — separate from Celery's DB 0 to avoid key
  collisions).

**ASGI entry point (`backend/settings/asgi.py`):**
Rewrite the stock skeleton into a `ProtocolTypeRouter`:
- `"http"` → `get_asgi_application()` (called first to populate the Django
  apps registry before any consumer imports).
- `"websocket"` → `TokenAuthMiddleware(URLRouter(websocket_urlpatterns))`.

**New app (`backend/realtime/`):**
- `__init__.py`
- `apps.py` — `RealtimeConfig`, `name = "realtime"`.
- `middleware.py` — `TokenAuthMiddleware(BaseMiddleware)`. Reads
  `Authorization: Token <key>` from WS handshake headers. Looks up
  `rest_framework.authtoken.models.Token` via `database_sync_to_async`.
  Sets `scope["user"]` to the resolved user or `AnonymousUser` on miss.
- `consumers.py` — `PlaybackConsumer(AsyncJsonWebsocketConsumer)`.
  Group name `playback_{user.id}`. `connect()` closes with code 4401 for
  anonymous users. `receive_json` handles `{"type": "sync"}` by calling
  `PlaybackService(user).state()` via `database_sync_to_async` and responding
  with `{"type": "playback.state", "state": {...}}`. Group handler
  `playback_state_changed` forwards to `send_json`.
- `routing.py` — `websocket_urlpatterns = [re_path(r"^ws/v1/playback/$", PlaybackConsumer.as_asgi())]`.

**Publisher hook (`backend/catalog/services/playback.py`):**
Add `_publish(self, state)` method. Stays `def` (not async). Uses
`async_to_sync(get_channel_layer().group_send)(...)` to post to group
`playback_{user.id}`. No-op when `get_channel_layer()` returns `None`
(unset in some test configs). Called as `self._publish(state)` just before
`return state` in each of `play`, `pause`, `next`, `previous`, `seek`.

**Production runner (`backend/run_prod.sh`):**
Change gunicorn command from:
```
gunicorn settings.wsgi:application --workers 3
```
to:
```
gunicorn settings.asgi:application -k uvicorn.workers.UvicornWorker --workers 3
```

**`backend/run_dev.sh`:** No change. `daphne` in `INSTALLED_APPS` hijacks
`runserver` transparently.

**Tests (`backend/tests/unit/test_realtime_consumers.py`):**
See Testing section below.

---

## Out Of Scope

- Any Go code. The daemon's WS client lands in cli-phase3.
- `world.*`, `session.*`, or `dm.*` event types. `realtime-world-session-events`
  and `backend-direct-messaging-foundation` inherit this transport.
- `?token=` query-param fallback for browser WS clients. Added when Juke World
  needs it — not now.
- Server-side Celery polling for externally-initiated Spotify changes. The
  daemon's own 10s drift poll covers this (arch doc §5.3).
- Load testing / fan-out tuning.

---

## Testing

All tests use Django's test runner. Run with:
```bash
docker compose exec backend python manage.py test tests.unit.test_realtime_consumers
```

### `TestPlaybackConsumerAnonymousRejected`
Connect a `WebsocketCommunicator` to `PlaybackConsumer.as_asgi()` with no
`Authorization` header (anonymous scope). Call `communicator.connect()`. Assert
it returns `(False, 4401)` — connection closed with code 4401.

### `TestPlaybackConsumerAcceptsValidToken`
Seed a test user and their DRF `Token` in setup. Provide the scope with
`headers = [(b"authorization", b"Token <key>")]`. Assert `connect()` returns
`(True, None)` — accepted.

### `TestPlaybackConsumerSyncRequest`
After a successful connect, send `{"type": "sync"}`. Assert the communicator
receives a JSON frame where `frame["type"] == "playback.state"` and
`frame["state"]` is a dict (shape not exhaustively checked — just present).

### `TestPlaybackConsumerPublishFanout`
Connect two communicators as the same user. Call
`PlaybackService(user)._publish(mock_state)` directly. Assert both
communicators receive a `playback_state_changed` frame within the test. Assert
neither receives the frame of the other user's group.

### `TestPlaybackConsumerPublishIsolation`
Connect communicator A as user 1, communicator B as user 2. Call `_publish`
for user 1. Assert communicator A receives a frame. Assert communicator B
receives nothing (timeout on receive → expected).

### `TestPublishNoOpWithoutChannelLayer`
Temporarily set `CHANNEL_LAYERS = {}` in settings override. Call
`PlaybackService(user)._publish(mock_state)`. Assert no exception is raised.

### Async containment test (regression)
Run the **full existing test suite**:
```bash
docker compose exec backend python manage.py test
```
Every pre-existing test must pass. This is the primary validation of the async
containment guarantee: sync views, serializers, services, models, and Celery
tasks all run in the ASGI HTTP handler's threadpool unchanged. If any existing
test breaks, the containment boundary failed.

### Manual probe
```bash
# Get a token
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/api-auth-token/ \
  -H "Content-Type: application/json" \
  -d '{"username":"test_user","password":"<password>"}' | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

# Connect and listen (install websocat: brew install websocat)
websocat -H "Authorization: Token $TOKEN" ws://127.0.0.1:8000/ws/v1/playback/
# → blocks waiting for frames

# In another terminal, trigger a playback event:
curl -s -X POST http://localhost:8000/api/v1/playback/pause/ \
  -H "Authorization: Token $TOKEN"
# → websocat terminal should print: {"type": "playback.state", "state": {...}}
```

---

## Acceptance Criteria

- `docker compose exec backend python manage.py test` passes — **all tests**,
  including every pre-existing test. Zero regressions.
- HTTP routes (`/api/v1/playback/state/`, `/api/v1/auth/api-auth-token/`, etc.)
  return identical response shapes before and after the ASGI switch.
- `docker compose up backend` comes up healthy with the uvicorn worker in
  production config.
- Anonymous WS connection to `ws/v1/playback/` closes with code 4401.
- Authenticated WS connection accepts and receives a `playback.state` frame on
  a `{"type": "sync"}` message.
- `POST /api/v1/playback/pause/` via curl causes a `playback.state` frame to
  arrive on the open WS connection for that user (fan-out works).
- Two connections for the same user both receive the same broadcast frame.
- A connection for user B does not receive user A's playback frames.

---

## Execution Notes

- **Program linkage:** phase2 of the `cli` program. This is the only Django
  phase. Depends on phase1b for sequencing (daemon has a transport stub to
  prove against). Unblocks cli-phase3's real WS client.
- **`get_asgi_application()` must be called before any consumer import.**
  The Django apps registry must be fully populated before models resolve.
  The `asgi.py` ordering in arch doc §7 gets this right — do not reorder.
- **Separate Redis DB for channels.** Use DB 1 (`redis://redis:6379/1`).
  Celery already owns DB 0. Sharing a keyspace causes silent message loss when
  a channel-layer key collides with a Celery queue key.
- **`async_to_sync` in `_publish`.** The publisher hook stays `def` (sync).
  `async_to_sync` opens a new event loop per call when called from a sync
  context — that is correct and expected. Do not call `_publish` from inside
  an already-async context (e.g. from a consumer method); call `group_send`
  directly there.
- **`InMemoryChannelLayer` for unit tests.** Use it instead of Redis in
  `test_realtime_consumers.py` to avoid Redis dependency in CI:
  ```python
  @override_settings(CHANNEL_LAYERS={"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}})
  ```
- **`database_sync_to_async` + `TransactionTestCase`.** Consumer tests that
  hit the DB via `database_sync_to_async` may need `@pytest.mark.django_db`
  with `transaction=True`, or use `channels.testing.WebsocketCommunicator`
  inside a `TestCase` with `@override_settings`.
- **Read first:**
  - `docs/arch/cli-juke-terminal-architecture.md` §7 — full code sketch for
    every file in this phase (consumer, middleware, routing, asgi.py, publisher
    hook) is written there verbatim.
  - `backend/settings/asgi.py` — 17-line stock skeleton, gets replaced.
  - `backend/catalog/services/playback.py` — where `_publish` is added.
  - `backend/run_prod.sh` — the one gunicorn line that changes.
- **Key files:**
  - `backend/requirements.txt`
  - `backend/settings/{base,asgi}.py`
  - `backend/realtime/{__init__,apps,middleware,consumers,routing}.py`
  - `backend/catalog/services/playback.py`
  - `backend/run_prod.sh`
  - `backend/tests/unit/test_realtime_consumers.py`

---

## To Test This

```bash
# 1. Rebuild the backend image (new deps)
docker compose build backend

# 2. Bring up the stack
docker compose up -d backend db redis

# 3. Run all tests (zero regressions is the primary gate)
docker compose exec backend python manage.py test

# 4. Run consumer tests in isolation
docker compose exec backend python manage.py test tests.unit.test_realtime_consumers -v 2

# 5. Manual WS probe (requires websocat: brew install websocat)
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/api-auth-token/ \
  -H "Content-Type: application/json" \
  -d '{"username":"test_user","password":"<password>"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['token'])")

websocat -H "Authorization: Token $TOKEN" ws://127.0.0.1:8000/ws/v1/playback/
# → In another terminal:
curl -s -X POST http://localhost:8000/api/v1/playback/pause/ -H "Authorization: Token $TOKEN"
# → websocat should print a playback.state frame within ~1 second
```

---

## Handoff

- Completed:
- Next:
  - cli-phase3 replaces `transport/ws_stub.go` with a real `gorilla/websocket`
    client dialling `ws://127.0.0.1:8000/ws/v1/playback/`.
  - `realtime-world-session-events` adds `world.*`/`session.*` consumers on
    top of this transport — no new transport work.
- Blockers:
  - `cli-phase1b-polling-transport` should be `review`/`done` for sequencing
    (soft blocker — this backend work is independent, but cli-phase3 needs both
    sides ready before wiring the WS client).
