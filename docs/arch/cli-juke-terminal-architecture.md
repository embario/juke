# Juke CLI — Architecture Document

**Version:** 1.0
**Date:** 2026-03-06
**Status:** Phase 0 — Approved direction (decisions locked)
**Scope:** `cli/` subproject + `backend/realtime/` WebSocket foundation

---

## 1. Executive Summary

Juke CLI is a power-user client for the Juke ecosystem, delivered as two native
binaries: a background daemon (`juked`) and an interactive terminal UI (`juke`).
It targets users who live in terminals and want keyboard-first control over
listening, discovery, and social features without reaching for a phone or browser.

The daemon owns all long-lived state — auth token, backend connection, playback
cache — and exposes a local IPC socket. The TUI is a thin, instant-start client
that connects to that socket. This mirrors `mpd`/`ncmpcpp` and `spotifyd`/`spt`,
which power users already understand.

The CLI is a **peer client** to web and mobile. It talks to the same
`/api/v1/*` surface and introduces no CLI-specific backend endpoints. Features
requiring new backend capability (DMs, track fun-facts, music generation) are
tracked as separate backend tasks that the CLI phases depend on.

One exception: **cli-phase2 delivers the backend WebSocket transport layer**
(`backend/realtime/`). This is CLI-roadmap work, but scoped as reusable platform
infrastructure. The daemon's playback subscription is its first — and
deliberately narrow — proving ground. `realtime-world-session-events` and the
future DM backend then add event types on top of the same transport.

---

## 2. Decisions Locked

These decisions were resolved during Phase 0 and should be treated as
implementation constraints.

1. **Language/stack:** Go. Single static binary per OS, trivial cross-compile.
   No runtime dependency on the user's machine.
2. **TUI framework:** Charm stack — `bubbletea` (Elm-architecture event loop),
   `lipgloss` (styling), `bubbles` (list/textinput/viewport/spinner widgets).
3. **Process model:** daemon + thin TUI. Two binaries shipped together.
4. **IPC transport:** Unix domain socket on Linux/macOS
   (`$XDG_RUNTIME_DIR/juke.sock`), named pipe on Windows (`\\.\pipe\juke`).
5. **IPC protocol:** length-prefixed JSON frames. Request/response correlation
   via client-assigned `id`. Server-pushed events have `id: null`.
6. **Backend transport:** WebSocket-primary, polling-fallback. Daemon tries
   `wss://<backend>/ws/v1/playback/` first; on any failure, falls back to
   polling `GET /api/v1/playback/state/` on a slow interval (~10s).
7. **Async containment (backend):** existing Django sync views/services/tasks
   stay sync. ASGI's HTTP handler runs them in a threadpool automatically.
   Only new `backend/realtime/` code is `async def`.
8. **Backend scope:** features needing new backend (DMs, fun-facts, music-gen)
   are separate task files. CLI phases declare them as blockers.
9. **WebSocket foundation ownership:** CLI roadmap owns delivering the
   `backend/realtime/` transport (cli-phase2). `realtime-world-session-events`
   inherits it and adds event types.
10. **Config format:** TOML. `~/.config/juke/config.toml` (XDG on Linux,
    equivalent paths on macOS/Windows — see §8).
11. **Session storage:** plain JSON file at `~/.local/share/juke/session.json`,
    mode 0600. Mirrors the Android `SessionStore` model from `fm.juke.core`
    (plain DataStore, no encryption layer). Token is the only secret.
12. **Service installation:** `juked install` subcommand writes the appropriate
    unit file (systemd user unit / launchd agent / Windows service XML).
    No package-manager integration in early phases.
13. **Image rendering:** deferred. Album art via sixel/kitty/iTerm2 protocols
    is a post-phase-3 enhancement. Initial TUI is text-only.
14. **Keybinding model:** vim-derived defaults (`j`/`k` nav, `/` search,
    `:` command palette, `space` play/pause). User-remappable via config.

---

## 3. Feature → Backend Dependency Map

The six CLI features map to backend readiness as follows. This table drove the
phase ordering and the separate-backend-task decision.

| CLI Feature | Backend Endpoint(s) | Status | CLI Phase | Blocked By |
|---|---|---|---|---|
| Auth / login | `POST /api/v1/auth/api-auth-token/`, `session/logout/` | Exists | 1 | — |
| Search catalog | `GET /api/v1/{genres,artists,albums,tracks}/` | Exists | 3 | — |
| Playback controls | `POST /api/v1/playback/{play,pause,next,previous,seek}/`, `GET state/` | Exists | 3 | — |
| Playback realtime push | `ws/v1/playback/` | **Built in cli-phase2** | 2 → 3 | — |
| Recommend from current track | `GET /api/v1/recommendations/` | Exists | 4 | — |
| Fun-facts about current track | new endpoint | Missing | 4 | `backend-track-facts-llm-endpoint` |
| DM other users | new `messaging/` app + WS consumer | Missing | 5 | `backend-direct-messaging-foundation` |
| Generate music from prompt | new ML service | Missing | 6 | `backend-music-generation-service` |

Reference: `backend/catalog/urls.py`, `backend/juke_auth/urls.py`,
`backend/recommender/urls.py`. Auth header is `Authorization: Token <key>` —
same as web (`web/src/shared/api/apiClient.ts:64`) and mobile.

---

## 4. Process Model

### 4.1 Runtime Topology

```
 user's machine                                           Juke platform
┌─────────────────────────────────────────────┐         ┌──────────────────┐
│                                             │         │                  │
│  ┌─────────────┐   IPC socket   ┌────────┐  │  HTTPS  │  Django + DRF    │
│  │ juke  (TUI) │◄──────────────►│ juked  │◄─┼────────►│  /api/v1/*       │
│  │ bubbletea   │  len-prefixed  │ daemon │  │         │                  │
│  │ event loop  │  JSON frames   │        │  │   WSS   │  Channels        │
│  └─────────────┘                │        │◄─┼────────►│  /ws/v1/*        │
│                                 └────────┘  │         │                  │
│  ┌─────────────┐  second TUI        │       │         │  Redis           │
│  │ juke  (TUI) │◄──── same ─────────┘       │         │  (channel layer) │
│  └─────────────┘     socket                 │         │                  │
│                                             │         └──────────────────┘
│  ~/.config/juke/config.toml                 │
│  ~/.local/share/juke/session.json  (0600)   │
│  ~/.cache/juke/                             │
└─────────────────────────────────────────────┘
```

### 4.2 Daemon Responsibilities

`juked` is the single source of truth on the user's machine.

| Concern | Behavior |
|---|---|
| **Lifecycle** | Starts on login (systemd/launchd/Windows service). Survives terminal close. `juked --foreground` for dev. |
| **Auth** | Holds the token. TUI never touches `session.json` directly — it asks the daemon. Login flow: TUI collects credentials → IPC `auth.login` → daemon POSTs `/api/v1/auth/api-auth-token/` → persists token → broadcasts `session.changed`. |
| **Backend transport** | Maintains one WS connection (or polling loop). See §5. |
| **Playback cache** | Last-known `PlaybackState`. TUI gets sub-millisecond reads from cache, not round-trips to Django. |
| **IPC server** | Listens on the socket. Multiple TUI instances can connect. See §6. |
| **Catalog cache** | Recent search results cached in `~/.cache/juke/catalog/` with TTL. Mitigates re-query on TUI restart. |

### 4.3 TUI Responsibilities

`juke` is stateless and disposable.

| Concern | Behavior |
|---|---|
| **Startup** | Connect to socket → request `session.state` + `playback.state` → render. If daemon not running, offer to start it (`juked --foreground` for now; service install is opt-in). |
| **Rendering** | Bubbletea `Model` holds view state only. All domain state lives in the daemon. |
| **Input** | Keypress → IPC request → wait for response or subsequent event → re-render. |
| **Multi-instance** | Two `juke` windows can run. Both see the same playback bar update simultaneously because both receive the same `playback.state.changed` broadcast. |

---

## 5. Transport Layer (Daemon ↔ Backend)

### 5.1 WebSocket-Primary

On startup and after auth, the daemon attempts:

```
GET wss://<backend>/ws/v1/playback/
Authorization: Token <key>
```

The Go daemon can set request headers on the WS handshake (unlike browsers),
so token auth works identically to REST. No query-param token needed for the
daemon path.

**Server → daemon events** (JSON frames over the WS):

```json
{"type": "playback.state", "state": { ...PlaybackState... }}
```

`PlaybackState` shape matches `GET /api/v1/playback/state/` exactly —
see `web/src/features/playback/types.ts:36-43` for the canonical schema
(`provider`, `is_playing`, `progress_ms`, `track`, `device`, `updated_at`).
Using the same shape means the daemon's state-handling code is transport-agnostic.

**Daemon → server messages** (rare; server-push is the primary direction):

```json
{"type": "sync"}
```

Sent once after `connect` / `reconnect` to get the current state without waiting
for the next change. Server responds with a `playback.state` frame.

**Reconnect:** exponential backoff starting at 1s, cap at 30s, jitter ±25%.
While disconnected, the daemon falls back to polling (§5.2) so the TUI never
goes dark.

### 5.2 Polling Fallback

When WS is unavailable — backend doesn't have cli-phase2 yet, network drops,
corporate proxy strips Upgrade headers — the daemon polls:

```
GET /api/v1/playback/state/
Authorization: Token <key>
```

Interval: 10s (slow — WS is expected to be the common path). On each poll,
diff against cached state; if changed, emit `playback.state.changed` over IPC
just as the WS path would. TUI cannot tell the difference.

**Phase sequencing:** Phase 1 ships **polling only**. Phase 2 ships the backend
WS endpoint. Phase 3 wires the daemon's WS client. A Phase-1 daemon works
against today's backend with zero changes.

### 5.3 Honest Gap: External Playback Changes

Spotify has no playback-state webhooks. If the user hits play in the Spotify
app directly (not via any Juke client), the backend doesn't know until
something asks Spotify.

- **Juke-initiated changes** (web, mobile, CLI hit `/api/v1/playback/play/`):
  backend calls Spotify → gets fresh state → `group_send` → daemon receives
  via WS → ~0ms latency. This is the common case.
- **External changes**: caught by the daemon's slow drift poll (10s) even
  when WS is connected. The poll runs regardless; it just becomes a safety net
  instead of the primary path.

A server-side Celery poller for users with active WS connections could close
this gap further, but it's out of scope for cli-phase2. Flagged in that task's
Execution Notes.

---

## 6. IPC Protocol (TUI ↔ Daemon)

### 6.1 Framing

Length-prefixed JSON over a stream socket. Each frame:

```
┌──────────────┬─────────────────────────────┐
│ 4-byte BE u32│  N bytes UTF-8 JSON         │
│ = N          │                             │
└──────────────┴─────────────────────────────┘
```

Simple, debuggable (`socat` + `xxd`), no dependency on protobuf/msgpack toolchains.

### 6.2 Message Envelope

All frames share one envelope:

```json
{"id": 42,   "type": "playback.play", "data": {...}}   // TUI → daemon request
{"id": 42,   "type": "ok",            "data": {...}}   // daemon → TUI response
{"id": 42,   "type": "error",         "data": {"code": "...", "message": "..."}}
{"id": null, "type": "playback.state.changed", "data": {...}}  // server-pushed event
```

- `id` is client-assigned, monotonic per connection. Responses echo it.
- `id: null` means unsolicited event (broadcast).
- Request/response and event frames can interleave freely on the stream.

### 6.3 Message Catalog (Phase 1–3 scope)

**Requests (TUI → daemon):**

| Type | Data | Response Data |
|---|---|---|
| `session.state` | — | `{authenticated: bool, username: string?}` |
| `auth.login` | `{username, password}` | `{username}` or error |
| `auth.logout` | — | `{}` |
| `playback.state` | — | `PlaybackState?` (cached, no backend round-trip) |
| `playback.play` | `{track_uri?, context_uri?, offset_uri?, offset_position?, position_ms?, device_id?}` | `PlaybackState?` |
| `playback.pause` | `{device_id?}` | `PlaybackState?` |
| `playback.next` | `{device_id?}` | `PlaybackState?` |
| `playback.previous` | `{device_id?}` | `PlaybackState?` |
| `playback.seek` | `{position_ms, device_id?}` | `PlaybackState?` |
| `catalog.search` | `{query, kinds: ["genre","artist","album","track"], limit?}` | `{genres[], artists[], albums[], tracks[]}` |
| `catalog.artist` | `{id}` | enriched artist detail |
| `catalog.album` | `{id}` | enriched album detail |
| `recommend.from_track` | `{track_id, limit?}` | `{tracks[]}` |

**Events (daemon → TUI, broadcast to all connections):**

| Type | Data | Fired When |
|---|---|---|
| `session.changed` | `{authenticated, username?}` | login/logout succeeds |
| `playback.state.changed` | `PlaybackState` | WS push or poll-diff |
| `daemon.transport.changed` | `{mode: "websocket" \| "polling"}` | WS connects/drops (TUI shows a subtle indicator) |

Phases 4–6 extend this catalog (`facts.*`, `dm.*`, `gen.*`). The envelope stays fixed.

### 6.4 Socket Location

| OS | Path |
|---|---|
| Linux | `$XDG_RUNTIME_DIR/juke.sock` (fallback `/tmp/juke-$UID.sock` if unset) |
| macOS | `~/Library/Application Support/Juke/juke.sock` |
| Windows | `\\.\pipe\juke` |

Build tags handle the split: `ipc_unix.go` (`//go:build !windows`) and
`ipc_windows.go` (`//go:build windows`). The rest of `internal/ipc/` is
platform-agnostic and deals only with `io.ReadWriteCloser`.

---

## 7. Backend `realtime/` App Design (cli-phase2)

### 7.1 Why This Is CLI-Roadmap Work

Building WS transport as part of the CLI roadmap — rather than blocking on
`realtime-world-session-events` — was a deliberate inversion:

- The daemon's playback subscription is **one event type, one subscriber
  shape**. Simplest possible proving ground for the transport.
- A long-lived Go process is the canonical WS client: persistent connection,
  explicit reconnect, heartbeat. Easier to validate server behavior against
  than a browser tab with visibility/effect quirks.
- Juke World's consumer is harder: LOD filtering, bounding-box subscriptions,
  high fan-out. Better to inherit working transport than to build transport
  and a hard consumer simultaneously.

`realtime-world-session-events` shrinks to "add `world.*` and `session.*`
event types on the existing `realtime/` app."

### 7.2 Async Containment

**Existing sync code is not touched.** This is the governing constraint.

```
                   ┌────────────────── settings/asgi.py ─────────────────┐
                   │         ProtocolTypeRouter                          │
                   │                                                     │
                   │  ┌─ "http" ─────────────────────────────────────┐   │
  HTTP request ────┼─►│ django.core.asgi.get_asgi_application()      │   │
                   │  │   detects sync `def` view → threadpool       │──►│──► catalog/views.py        (sync, unchanged)
                   │  │   view never knows ASGI exists               │──►│──► juke_auth/views.py      (sync, unchanged)
                   │  └──────────────────────────────────────────────┘   │──► PlaybackService         (sync, +3 lines)
                   │                                                     │──► all tests               (sync, unchanged)
                   │  ┌─ "websocket" ────────────────────────────────┐   │
  WS upgrade ──────┼─►│ TokenAuthMiddleware → URLRouter              │   │
                   │  │   → PlaybackConsumer                         │──►│──► realtime/consumers.py   (async, NEW)
                   │  │   `async def` from day one                   │──►│──► realtime/middleware.py  (async, NEW)
                   │  └──────────────────────────────────────────────┘   │
                   └─────────────────────────────────────────────────────┘
```

Django's ASGI HTTP handler has a built-in sync adapter. When it encounters a
sync `def` view, it runs it in a threadpool and awaits the result. The view
receives a normal `HttpRequest`, returns a normal `HttpResponse`. Zero code
changes to any existing view, serializer, service, model, Celery task, or test.

The middleware stack (`settings/base.py:157-167`) is all stock Django +
whitenoise + corsheaders, all of which are async-capable on Django 6.

### 7.3 File Map

```
backend/realtime/
├── __init__.py
├── apps.py
├── consumers.py      # PlaybackConsumer(AsyncJsonWebsocketConsumer)
├── middleware.py     # TokenAuthMiddleware
└── routing.py        # websocket_urlpatterns
```

Plus edits to existing files:

| File | Change | Sync? |
|---|---|---|
| `settings/asgi.py` | Wrap in `ProtocolTypeRouter`, add `"websocket"` route | — (config) |
| `settings/base.py` | `+CHANNEL_LAYERS` (→ existing Redis), `+ASGI_APPLICATION`, `+'daphne'` and `+'realtime'` in `INSTALLED_APPS` | — (config) |
| `requirements.txt` | `+channels +channels-redis +uvicorn[standard] +daphne` | — |
| `run_prod.sh:17` | `settings.wsgi` → `settings.asgi`, `+ -k uvicorn.workers.UvicornWorker` | — |
| `run_dev.sh` | No change — `daphne` in `INSTALLED_APPS` hijacks `runserver` transparently | — |
| `catalog/services/playback.py` | Add `_publish(state)` helper, call it at tail of play/pause/next/previous/seek | **Stays sync** |

### 7.4 Consumer

```python
# backend/realtime/consumers.py
from channels.db import database_sync_to_async
from channels.generic.websocket import AsyncJsonWebsocketConsumer
from catalog.services.playback import PlaybackService

class PlaybackConsumer(AsyncJsonWebsocketConsumer):
    @property
    def group(self):
        return f"playback_{self.scope['user'].id}"

    async def connect(self):
        if self.scope["user"].is_anonymous:
            await self.close(code=4401)
            return
        await self.channel_layer.group_add(self.group, self.channel_name)
        await self.accept()

    async def disconnect(self, code):
        if not self.scope["user"].is_anonymous:
            await self.channel_layer.group_discard(self.group, self.channel_name)

    async def receive_json(self, content):
        if content.get("type") == "sync":
            state = await database_sync_to_async(
                PlaybackService(self.scope["user"]).state
            )()
            await self.send_json({"type": "playback.state", "state": state})

    async def playback_state_changed(self, event):
        # Invoked by channel layer when group_send uses type="playback.state.changed".
        await self.send_json({"type": "playback.state", "state": event["state"]})
```

### 7.5 Token Auth Middleware

```python
# backend/realtime/middleware.py
from channels.db import database_sync_to_async
from channels.middleware import BaseMiddleware
from django.contrib.auth.models import AnonymousUser
from rest_framework.authtoken.models import Token

@database_sync_to_async
def _user_for_token(key):
    try:
        return Token.objects.select_related("user").get(key=key).user
    except Token.DoesNotExist:
        return AnonymousUser()

class TokenAuthMiddleware(BaseMiddleware):
    async def __call__(self, scope, receive, send):
        headers = dict(scope.get("headers", []))
        raw = headers.get(b"authorization", b"").decode()
        key = raw.removeprefix("Token ").strip() if raw.startswith("Token ") else None
        scope["user"] = await _user_for_token(key) if key else AnonymousUser()
        return await super().__call__(scope, receive, send)
```

Browser clients (future Juke World consumer) cannot set custom headers on the
WS handshake. A `?token=` query-param fallback will be added when the web
needs it — not in cli-phase2.

### 7.6 Publisher Hook (sync → channel layer)

```python
# backend/catalog/services/playback.py  — additions only
from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer

class PlaybackService:
    # ... existing methods unchanged ...

    def _publish(self, state):
        if state is None:
            return
        layer = get_channel_layer()
        if layer is None:  # CHANNEL_LAYERS unset (e.g. some test configs)
            return
        async_to_sync(layer.group_send)(
            f"playback_{self.user.id}",
            {"type": "playback.state.changed", "state": state},
        )
```

Called as `self._publish(state)` just before `return state` in each of `play`,
`pause`, `next`, `previous`, `seek`. The method stays `def`, not `async def`.
If no consumer is subscribed to the group, `group_send` writes to Redis and
nothing reads it — cheap no-op.

### 7.7 Testing

- `ChannelsLiveServerTestCase` + `websockets` client for integration tests
  (connect → trigger `POST /api/v1/playback/play/` → assert frame received).
- `WebsocketCommunicator` for consumer unit tests (no real socket).
- Existing `tests/api/test_playback_api.py` stays green unchanged — sync
  HTTP path is unaffected.

---

## 8. Config, Session, and Cache Storage

### 8.1 Paths

XDG Base Directory spec on Linux; platform conventions elsewhere.

| Purpose | Linux | macOS | Windows |
|---|---|---|---|
| Config | `$XDG_CONFIG_HOME/juke/config.toml` (`~/.config/juke/`) | `~/Library/Application Support/Juke/config.toml` | `%APPDATA%\Juke\config.toml` |
| Session | `$XDG_DATA_HOME/juke/session.json` (`~/.local/share/juke/`) | `~/Library/Application Support/Juke/session.json` | `%APPDATA%\Juke\session.json` |
| Cache | `$XDG_CACHE_HOME/juke/` (`~/.cache/juke/`) | `~/Library/Caches/Juke/` | `%LOCALAPPDATA%\Juke\cache\` |
| IPC socket | `$XDG_RUNTIME_DIR/juke.sock` | `~/Library/Application Support/Juke/juke.sock` | `\\.\pipe\juke` |

`session.json` is written with mode `0600`. On Windows, the equivalent is
inheriting ACLs from `%APPDATA%` which is already user-scoped — no extra work.

### 8.2 `config.toml` Schema

```toml
# Backend target — same value as BACKEND_URL in template.env.
backend_url = "https://juke.example.com"

# Transport preferences.
[transport]
# Set to "polling" to force polling even if WS is available. "auto" is default.
mode = "auto"
poll_interval_seconds = 10

# Theme — lipgloss color overrides. Keys mirror the JukePlatformPalette
# interface from fm.juke.core for visual consistency across clients.
[theme]
accent       = "#ff8c42"
accent_soft  = "#ffb380"
# ... (full palette)

# Keybindings — vim defaults, user-remappable.
[keys]
play_pause = "space"
next       = "n"
previous   = "p"
search     = "/"
command    = ":"
nav_up     = "k"
nav_down   = "j"
nav_left   = "h"
nav_right  = "l"
quit       = "q"
```

### 8.3 `session.json` Schema

```json
{"username": "melodyqueen", "token": "a1b2c3...", "saved_at": "2026-03-06T14:27:00Z"}
```

Intentionally minimal — mirrors `SessionSnapshot` from `fm.juke.core`
(`username`, `token`). Only the daemon reads/writes this file; the TUI asks
the daemon for session state via IPC.

---

## 9. Go Package Layout

```
cli/
├── AGENTS.md                       # subproject agent guide (Phase 0)
├── go.mod                          # module: TBD — org-qualified path (Phase 1)
├── go.sum
│
├── cmd/
│   ├── juked/
│   │   └── main.go                 # daemon entrypoint — flag parsing, signal handling
│   └── juke/
│       └── main.go                 # TUI entrypoint — cobra root + subcommands
│
├── internal/
│   ├── api/                        # Juke backend HTTP client
│   │   ├── client.go               # base client, Token auth injection, retry
│   │   ├── auth.go                 # login, logout
│   │   ├── catalog.go              # genres/artists/albums/tracks search + detail
│   │   ├── playback.go             # play/pause/next/prev/seek/state
│   │   ├── recommend.go            # recommendations
│   │   └── types.go                # PlaybackState, Track, Artist, Album, etc.
│   │
│   ├── transport/                  # daemon ↔ backend connection management
│   │   ├── transport.go            # interface: Connect() / Events() <-chan / Close()
│   │   ├── ws.go                   # WebSocket implementation (gorilla/websocket)
│   │   ├── poll.go                 # polling fallback implementation
│   │   └── manager.go              # tries WS, falls back to poll, emits transport.changed
│   │
│   ├── ipc/                        # daemon ↔ TUI protocol
│   │   ├── protocol.go             # envelope types, encode/decode
│   │   ├── server.go               # daemon side — accept loop, broadcast
│   │   ├── client.go               # TUI side — request/response correlation, event chan
│   │   ├── socket_unix.go          # //go:build !windows
│   │   └── socket_windows.go       # //go:build windows
│   │
│   ├── daemon/                     # juked core
│   │   ├── daemon.go               # wiring: transport + ipc server + state store
│   │   ├── state.go                # cached PlaybackState, session state
│   │   ├── handlers.go             # IPC request → backend API → response
│   │   └── install/                # service-unit writers
│   │       ├── systemd.go
│   │       ├── launchd.go
│   │       └── windows.go
│   │
│   ├── config/
│   │   ├── config.go               # TOML load/validate/defaults
│   │   └── paths.go                # XDG + macOS + Windows path resolution
│   │
│   ├── session/
│   │   └── store.go                # session.json read/write (0600)
│   │
│   └── tui/                        # bubbletea app
│       ├── app.go                  # root Model, Init/Update/View, IPC event pump
│       ├── keys.go                 # keybinding map → tea.Msg
│       ├── theme/
│       │   └── theme.go            # lipgloss.Style palette
│       └── panes/
│           ├── playbackbar.go      # persistent bottom bar
│           ├── nav.go              # left nav (Library / Messages / Generate)
│           ├── search.go           # modal overlay
│           ├── catalog.go          # search results + detail drill-down
│           ├── nowplaying.go       # right sidebar — current track + facts
│           ├── recommend.go        # "flows into" recommendations
│           ├── dm.go               # conversation list + thread (phase 5)
│           ├── generate.go         # prompt box + progress (phase 6)
│           └── help.go             # ? overlay — keybinding cheatsheet
│
└── testdata/
    └── fixtures/                   # recorded backend responses for api/ tests
```

**Why `internal/`:** Go's `internal/` directory is compiler-enforced private —
nothing outside `cli/` can import from it. Since this is an application (not a
library), everything goes here. No `pkg/`.

**Module path:** to be finalized in Phase 1 once the GitHub org path is known.
Placeholder in `go.mod` until then.

---

## 10. Cross-Platform Strategy

### 10.1 Build Tags

Platform-conditional code lives in `_unix.go` / `_windows.go` suffixed files
with `//go:build` constraints at the top. The rest of the codebase imports
platform-agnostic interfaces.

Concretely, only two areas need tagged files:

| Area | Unix | Windows |
|---|---|---|
| IPC socket | `net.Listen("unix", path)` | `winio.ListenPipe(path, nil)` (`github.com/Microsoft/go-winio`) |
| Service install | systemd unit / launchd plist writers | `golang.org/x/sys/windows/svc` |

Everything else — HTTP, WebSocket, TOML, JSON, bubbletea — is already portable.

### 10.2 CI Matrix

GitHub Actions matrix build producing release artifacts:

| GOOS | GOARCH | Runner |
|---|---|---|
| linux | amd64 | ubuntu-latest |
| linux | arm64 | ubuntu-latest (cross-compile) |
| darwin | amd64 | macos-latest (cross-compile) |
| darwin | arm64 | macos-latest |
| windows | amd64 | windows-latest |

`CGO_ENABLED=0` for all — pure-Go dependencies only, static binaries.

### 10.3 Terminal Compatibility

Bubbletea/lipgloss degrade gracefully on terminals that lack truecolor or
unicode box-drawing. The theme layer detects `$COLORTERM` / `$TERM` and falls
back to 256-color → 16-color → monochrome. Phase 3 includes a manual test
checklist covering: iTerm2, Terminal.app, Alacritty, kitty, GNOME Terminal,
Windows Terminal, and `ssh` into a headless Linux box.

---

## 11. Phase Roadmap

| Phase | Task File | Deliverable | Lang | Blocked By | Complexity |
|---|---|---|---|---|---|
| 0 | `cli-phase0-architecture-and-design` | This doc + TUX doc + `cli/AGENTS.md` + task files | — | — | 3 |
| 1 | `cli-phase1-daemon-ipc-auth-foundation` | `juked` + `juke` skeleton, IPC protocol, auth flow, config/session, **polling transport**, `scripts/test_cli.sh` | Go | phase0 | 4 |
| 2 | `cli-phase2-backend-websocket-transport` | `backend/realtime/` app, ASGI switch, `PlaybackConsumer`, publisher hook | Django | phase1 | 3 |
| 3 | `cli-phase3-catalog-playback-tui` | Search pane, catalog drill-down, playback bar, keybindings, **daemon WS client** | Go | phase2 | 4 |
| 4 | `cli-phase4-recommendations-and-facts` | Recs pane, fun-facts sidebar | Go | phase3, `backend-track-facts-llm-endpoint` | 3 |
| 5 | `cli-phase5-direct-messaging` | DM conversation list + thread pane | Go | phase3, `backend-direct-messaging-foundation` | 4 |
| 6 | `cli-phase6-music-generation` | Gen prompt pane + progress | Go | phase3, `backend-music-generation-service` | 3 |

Phases 4–6 are parallel-capable once Phase 3 lands.

### 11.1 Separate Backend Dependency Tasks

Per the Phase 0 decision, these are platform tasks the CLI depends on but does
not own. Other clients will consume them too.

| Task | Scope | Blocks |
|---|---|---|
| `backend-track-facts-llm-endpoint` | New endpoint using the `openai` client pattern from `backend/tunetrivia/services.py:258-344`. Takes a track, returns 2–3 fun facts. | cli-phase4 |
| `backend-direct-messaging-foundation` | New `messaging/` Django app. Conversation + Message models, REST CRUD, `MessageConsumer` on `realtime/` transport. | cli-phase5 |
| `backend-music-generation-service` | Experimental. New service container (likely calling an external gen API). Prompt → job → poll/push progress → audio URL. | cli-phase6 |

---

## 12. Linked Tasks

- `tasks/realtime-world-and-session-events-platform.md` — inherits cli-phase2's
  WS transport. Its scope shrinks to adding `world.*` and `session.*` event
  types plus browser-side subscription. Execution Notes in that task updated.
- `tasks/clients-feature-parity.md` — the CLI becomes a fifth client in the
  parity matrix once Phase 3 ships.
- `tasks/social-graph-and-follow-activity-foundation.md` — DM was explicitly
  out-of-scope there. `backend-direct-messaging-foundation` is a sibling task,
  not a dependency of the social-graph work.

---

## 13. Progress Log

| Phase | Status | Notes |
|---|---|---|
| 0 | review | Arch + TUX docs, `cli/AGENTS.md`, task generation |
| 1 | ready | — |
| 2 | ready | — |
| 3 | ready | — |
| 4 | blocked | on `backend-track-facts-llm-endpoint` |
| 5 | blocked | on `backend-direct-messaging-foundation` |
| 6 | blocked | on `backend-music-generation-service` |

---

*Document Version: 1.0*
*Last Updated: 2026-03-06*
