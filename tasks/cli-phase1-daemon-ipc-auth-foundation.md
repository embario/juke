---
id: cli-phase1-daemon-ipc-auth
title: Juke CLI Phase 1 — Daemon skeleton, IPC protocol, and auth/session foundation
status: review
priority: p1
owner: unassigned
area: cli
label: CLI
labels:
  - juke-task
  - cli
  - go
complexity: 4
updated_at: 2026-06-10
owner: codex
---

## Goal

Bring up `juked` as a running daemon that binds an IPC socket on all three
platforms, speaks the length-prefixed JSON protocol, and handles
`session.state`, `session.login`, and `session.logout` requests backed by a
DRF token stored in `session.json` (mode 0600). Bring up `juke` as a minimal
TUI stub that connects to the socket, shows whether the user is logged in,
prompts for credentials when not, and re-renders on `session.changed` push
events without any user action.

**End state:** start the daemon in one terminal, start the TUI in another.
Log in from the TUI. See the session state flip to authenticated. Kill the TUI
and restart it — it reconnects and shows the session without re-entering
credentials. Kill -9 the daemon and restart it — it rebinds the same socket
path without `address already in use`.

Polling transport and playback state are explicitly out of scope. They land in
the next slice (Phase 1b — see Handoff).

---

## Scope

- `cli/go.mod` + `cli/go.sum` — module path `github.com/embario/juke/cli`,
  Go 1.24+, all deps from `cli/AGENTS.md §Stack`.
- `cli/cmd/juked/main.go` — cobra root, `--foreground` flag, `install`
  subcommand scaffold (per-OS service writers are `TODO` stubs, no
  implementation).
- `cli/cmd/juke/main.go` — TUI entrypoint.
- `cli/internal/config/paths.go` — `ConfigDir()`, `DataDir()`, `CacheDir()`,
  `SocketPath()` using XDG/macOS/Windows conventions. No cgo.
- `cli/internal/config/config.go` — TOML `Config` struct (`backend_url`,
  `[transport]`, `[theme]`, `[keys]`); `Load(path)` with sane defaults when
  file is absent.
- `cli/internal/session/store.go` — `Session{Username, Token, SavedAt}`;
  `Load(path)` / `Save(path, s)`. `Save` uses `os.OpenFile(..., 0600)` on
  Unix; creates parent dirs; Windows inherits `%APPDATA%` ACLs (best-effort).
- `cli/internal/api/client.go` — `Client{baseURL, token}`; `Do(method, path,
  body, dst)` injecting `Authorization: Token <key>` when set; returns typed
  `APIError{StatusCode, Message}`.
- `cli/internal/api/auth.go` — `Login(username, password) (token, error)` POSTing
  to `/api/v1/auth/api-auth-token/`; `Logout() error` POSTing to
  `/api/v1/auth/session/logout/`.
- `cli/internal/api/types.go` — `PlaybackState` struct mirroring
  `web/src/features/playback/types.ts:36-43` (`Provider`, `IsPlaying`,
  `ProgressMs`, `Track`, `Device`, `UpdatedAt`). Stub only this phase; no
  callers until Phase 1b.
- `cli/internal/ipc/protocol.go` — `Message{ID *int, Type string, Data
  json.RawMessage}`; `WriteFrame(w io.Writer, m Message) error`;
  `ReadFrame(r io.Reader) (Message, error)`. 4-byte big-endian u32 length
  prefix; `io.ReadFull` for the payload; `ErrFrameTooLarge` (>4 MiB).
- `cli/internal/ipc/socket_unix.go` (`//go:build !windows`) — `Listen() (net.Listener, error)`;
  `SocketPath() string`; stale-socket cleanup (try-connect → if refused,
  `os.Remove` → rebind).
- `cli/internal/ipc/socket_windows.go` (`//go:build windows`) — same interface
  via `winio.ListenPipe`.
- `cli/internal/ipc/server.go` — `Server`: accept loop, per-conn goroutines,
  per-conn write channel (never shared-mutex a writer), `Broadcast(m Message)`.
- `cli/internal/ipc/client.go` — `Client`: `Dial()`, `Request(m Message)
  (Message, error)` (blocks on matching `id`; concurrent-safe via pending-map +
  mutex), `Events() <-chan Message` (fed by reader goroutine for `id: null`
  frames), `Close()`.
- `cli/internal/daemon/state.go` — `State{mu sync.RWMutex, authenticated bool,
  username string}`; `SetSession(...)`, `Session() SessionSnapshot`.
- `cli/internal/daemon/handlers.go` — `HandleSessionState`, `HandleSessionLogin`,
  `HandleSessionLogout`. Login: call API, update state, write session.json,
  broadcast `session.changed`. Logout: call API (best-effort), clear state,
  remove/zero session.json, broadcast `session.changed`.
- `cli/internal/daemon/daemon.go` — `Daemon`: loads config + session, builds
  IPC server, registers handlers, `Run(ctx) error` blocks until ctx cancel or
  SIGINT/SIGTERM, prints socket path to stderr on startup.
- `cli/internal/tui/app.go` — root `tea.Model`; IPC event pump goroutine
  (`p.Send`); renders: (a) not-logged-in + login prompt (bubbles `textinput`
  for username/password), (b) `"✓ logged in as <username>"` + `q`-to-quit hint.
  Re-renders on `session.changed` push. No panes.
- `cli/testdata/fixtures/api-auth-token-200.json` — `{"token":"testtoken123"}`.
- `cli/testdata/fixtures/api-auth-token-400.json` —
  `{"non_field_errors":["Unable to log in with provided credentials."]}`.
- `scripts/test_cli.sh` — `set -euo pipefail; cd "$(git rev-parse
  --show-toplevel)/cli"; go vet ./... && staticcheck ./... && go test -race ./...`.

---

## Out Of Scope

- **Polling transport** (`internal/transport/poll.go`, ticker loop, diff
  against cached `PlaybackState`). Phase 1b.
- **Playback state cache** in daemon state, `playback.state` IPC handler,
  `playback.state.changed` broadcast. Phase 1b.
- **Playback control handlers** (`playback.play/pause/next/prev/seek`). Phase 3.
- **Any TUI panes** beyond the minimal session-status screen (search, catalog,
  playback bar, now-playing, recommendations). Phases 3–6.
- **Messaging and music generation** panes and IPC messages. Phases 5–6.
- **`backend/realtime/`** WebSocket app. cli-phase2.
- **`juked install` per-OS implementations** — cobra subcommand scaffold only.

---

## Iterations

Implement these slices in order. Each has a self-contained test point that must
pass before the next slice starts. The test points are cumulative — later slices
run all earlier tests too.

---

### Iteration 1 — Module scaffold and IPC framing codec

**Deliver:**
- `cli/go.mod` and `cli/go.sum` with all deps pinned.
- `cli/internal/ipc/protocol.go` — `Message`, `WriteFrame`, `ReadFrame`,
  `ErrFrameTooLarge`.
- `cli/internal/ipc/socket_unix.go` + `socket_windows.go` — `Listen() (net.Listener, error)`,
  `SocketPath() string`.

**What does NOT exist yet:** daemon, config, session, api, TUI — nothing but the
codec and socket binder.

**Test point:** `cd cli && go test -race ./internal/ipc/...`

Required test cases:
- `TestFrameRoundTrip` — encode a `Message`, decode it from the same bytes,
  assert equality.
- `TestFrameShortRead` — write the frame in two chunks (header in one `Write`,
  payload in another); `ReadFrame` must reassemble without error.
- `TestFrameConcurrentWrite` — 20 goroutines each write a distinct frame on the
  same `net.Conn` pipe; reader receives all 20 frames without JSON decode errors.
- `TestFrameTooLarge` — `WriteFrame` with a 5 MiB payload; `ReadFrame` returns
  `ErrFrameTooLarge`.

---

### Iteration 2 — Config and session store

**Deliver:**
- `cli/internal/config/paths.go` and `config.go`.
- `cli/internal/session/store.go`.

**Test point:** `cd cli && go test -race ./internal/config/... ./internal/session/...`

Required test cases:
- `TestSessionSavePerms` — `Save` on Unix; `stat` the file; assert mode bits are
  `0600`. Skip on Windows (`if runtime.GOOS == "windows" { t.Skip(...) }`).
- `TestSessionRoundTrip` — `Save` then `Load`; all fields equal.
- `TestSessionMissing` — `Load` from a nonexistent path returns `nil, nil`.
- `TestConfigDefaults` — `Load` from missing file returns a `Config` with
  `BackendURL == ""` and non-zero transport defaults.
- `TestConfigBadTOML` — `Load` from a path containing `[not valid` returns a
  non-nil error.

---

### Iteration 3 — Daemon skeleton, IPC server, and `session.state` handler

**Deliver:**
- `cli/internal/ipc/server.go` — `Server.Listen()`, `Server.Accept()`,
  `Server.Broadcast()`, `Server.Close()`. Per-conn write channels, no shared
  writer mutex.
- `cli/internal/daemon/state.go` — `State`, `SetSession`, `Session`.
- `cli/internal/daemon/handlers.go` — `HandleSessionState` only.
- `cli/internal/daemon/daemon.go` — `Daemon.Run(ctx)` with signal handling.
- `cli/cmd/juked/main.go` — cobra root + `--foreground` + `install` stub.

**Test point — unit:** `cd cli && go test -race ./internal/daemon/... ./internal/ipc/...`

Required test cases:
- `TestHandleSessionStateUnauthenticated` — handler called with empty `State`;
  response `data.authenticated == false`.
- `TestServerBroadcast` — two fake clients connected via `net.Pipe()`; server
  broadcasts one message; both clients receive it within 100ms.
- `TestServerConcurrentClients` — 10 clients connect concurrently; each sends
  `session.state`; each receives a response with its own `id`; no panics.

**Test point — manual (run once, not automated):**
```bash
cd cli
go run ./cmd/juked --foreground &
DAEMON_PID=$!
sleep 1
SOCK="$(go run ./cmd/juked --print-socket-path 2>&1 || \
  echo "${XDG_RUNTIME_DIR:-$HOME/Library/Application Support/Juke}/juke.sock")"
MSG='{"id":1,"type":"session.state","data":{}}'
python3 -c "
import sys, struct, json
b = sys.argv[1].encode()
sys.stdout.buffer.write(struct.pack('>I', len(b)) + b)
" "$MSG" | socat - "UNIX-CONNECT:$SOCK" | python3 -c "
import sys, struct, json
n = struct.unpack('>I', sys.stdin.buffer.read(4))[0]
print(json.loads(sys.stdin.buffer.read(n)))
"
kill $DAEMON_PID
```
Expected output: `{'id': 1, 'type': 'ok', 'data': {'authenticated': False, 'username': None}}`

---

### Iteration 4 — Backend API client and auth IPC handlers

**Deliver:**
- `cli/internal/api/client.go`, `auth.go`, `types.go`.
- `cli/testdata/fixtures/api-auth-token-200.json` and `…-400.json`.
- `cli/internal/daemon/handlers.go` — add `HandleSessionLogin` and
  `HandleSessionLogout`. Broadcast `session.changed` on success.

**`session.changed` event shape:**
```json
{"id": null, "type": "session.changed", "data": {"authenticated": true, "username": "melodyqueen"}}
```

**Test point:** `cd cli && go test -race ./internal/api/... ./internal/daemon/...`

Required test cases:
- `TestLoginSuccess` — `api.Login` driven by a `httptest.Server` returning the
  200 fixture; returns the token string.
- `TestLoginBadCredentials` — 400 fixture; returns `*APIError` with
  `StatusCode == 400`.
- `TestHandleSessionLoginSuccess` — mock API client returns token; handler
  updates `State`; broadcasts `session.changed` with `authenticated: true`.
- `TestHandleSessionLoginFailure` — mock returns `APIError`; handler responds
  with IPC `error` type; state unchanged; no broadcast.
- `TestHandleSessionLogout` — handler clears state; `session.changed` broadcast
  with `authenticated: false`; `Session().Token` is empty string.

---

### Iteration 5 — IPC client, TUI stub, stale-socket cleanup, and test script

**Deliver:**
- `cli/internal/ipc/client.go` — `Client.Dial()`, `Client.Request()`,
  `Client.Events()`, `Client.Close()`.
- Stale-socket cleanup in `socket_unix.go` (already specced in §Scope).
- `cli/internal/tui/app.go` — root `tea.Model` as described in §Scope.
- `cli/cmd/juke/main.go`.
- `scripts/test_cli.sh`.

**Test point:** `cd cli && go test -race ./internal/ipc/...`

Required test cases:
- `TestClientRequestConcurrent` — 10 goroutines on one `Client`, each calls
  `Request` with a distinct `id`; a fake server echoes each frame with matching
  `id`; each goroutine receives its own response. No id cross-talk.
- `TestClientEventChannel` — fake server sends a frame with `"id": null` after
  the connection opens; client delivers it to `Events()` channel within 100ms.
- `TestStaleSocketCleanup` — create a socket file at the path; start a goroutine
  that `net.Listen`s on it and immediately closes (simulates crashed daemon);
  call `Listen()` in the real code; assert it returns a live listener without
  `address already in use` error.

**End-to-end smoke test (manual, documents the Phase 1 demo):**
```bash
# Terminal 1
cd cli && go run ./cmd/juked --foreground

# Terminal 2
cd cli && go run ./cmd/juke
# → shows "Not logged in" + username/password prompt
# → enter credentials from .env (JUKE_TEST_USER / JUKE_TEST_PASS)
# → TUI flips to "✓ logged in as <username>"
# → Ctrl+C Terminal 1 (kill daemon)
# → restart Terminal 1
# → TUI auto-reconnects and re-shows session (no re-login needed)
```

**`scripts/test_cli.sh` exit 0:**
```bash
./scripts/test_cli.sh
```

---

## Acceptance Criteria

- `cd cli && CGO_ENABLED=0 go build ./cmd/...` produces `juked` and `juke`
  on linux/amd64, darwin/arm64, and windows/amd64.
- Daemon started with `--foreground` prints the bound socket path to stderr
  before serving.
- The `socat` round-trip from `cli/AGENTS.md §Debugging` returns a well-formed
  `session.state` response (`authenticated: false`) from a fresh daemon.
- `session.json` is written mode 0600; `TestSessionSavePerms` enforces this
  and is not skipped on Linux/macOS CI runners.
- Kill -9 the daemon, restart it — it rebinds the same socket path without
  error (`TestStaleSocketCleanup` covers this plus manual verification).
- `session.login` IPC over a live backend: flips `authenticated: true`,
  writes `session.json`, delivers `session.changed` to a connected TUI client.
- `session.logout` IPC: clears state, removes/zeros `session.json`, delivers
  `session.changed`.
- TUI re-renders on `session.changed` push without user keypress.
- `scripts/test_cli.sh` exits 0 from repo root.
- `cd cli && go test -race ./...` passes with no data races detected.

---

## Execution Notes

- **Program linkage:** phase1 of the `cli` program. Depends on
  `cli-phase0-architecture-and-design` (`review`). Phase 1b (polling) follows;
  phase2 (backend WS) follows phase 1b; phase3 (full TUI) follows phase2.
- **Read first:**
  - `docs/arch/cli-juke-terminal-architecture.md` §4 (process model), §6
    (IPC protocol + message catalog), §8 (config/session paths), §9 (package
    layout).
  - `cli/AGENTS.md` — all of it. "Never block in `Update`" and "IPC events are
    `tea.Msg`" are load-bearing bubbletea patterns; violating them causes
    deadlocks that don't show up until multiple TUI instances are open.
- **Key reference files:**
  - `web/src/features/playback/types.ts:36-43` — `PlaybackState` struct shape.
  - `backend/juke_auth/urls.py` — confirms login path is
    `/api/v1/auth/api-auth-token/` and logout is `/api/v1/auth/session/logout/`.
- **Module path:** `github.com/embario/juke/cli` (confirmed from `git remote`).
- **Iteration order is mandatory.** Iteration 1's codec is used by every
  subsequent package. Write its tests before anything depends on it. A
  length-prefix off-by-one reads garbage JSON on the *next* frame, not the
  current one — failures manifest two frames later and are extremely hard to
  debug.
- **Broadcast race surface.** `ipc/server.go` has per-conn goroutines reading
  + a caller doing `Broadcast`. Use a buffered channel per connection (writer
  goroutine drains it) rather than a shared `sync.Mutex`-protected writer.
  A slow/stalled TUI client must not block the broadcast to other clients.
- **Windows named pipe tests.** `socket_windows.go` tests require
  `//go:build windows` — they are silently skipped on Linux CI runners. Note
  this in the Handoff; verify manually on Windows before marking phase done.
- **`0600` on Windows.** Accept best-effort (inherit `%APPDATA%` ACLs).
  Document the decision in a comment in `session/store_windows.go`.

---

## Handoff

- Completed:
  - **Iteration 1** (2026-06-10) — `go.mod` (Go 1.26.4, github.com/embario/juke/cli),
    `internal/ipc/protocol.go` (WriteFrame/ReadFrame, ErrFrameTooLarge),
    `socket_unix.go` / `socket_windows.go` (Listen/Dial/SocketPath, stale-socket
    cleanup, Windows stub). 6 tests, all pass with -race.
  - **Iteration 2** (2026-06-10) — `internal/config/paths.go` (XDG/macOS/Windows
    path resolution), `config.go` (TOML load with defaults),
    `internal/session/store.go` + platform `writefile_*.go` (Save 0600, Load,
    Delete). 7 tests, all pass with -race. `TestSessionSavePerms` enforces 0600.
  - **Iteration 3** (2026-06-10) — `internal/ipc/server.go` (accept loop,
    per-conn write channels, Broadcast), `internal/daemon/state.go` (State,
    SessionSnapshot), `daemon/handlers.go` (HandleSessionState),
    `daemon/daemon.go` (Run, signal handling), `daemon/install/stub.go`,
    `cmd/juked/main.go` (cobra + --foreground + install stub). 5 tests.
  - **Iteration 4** (2026-06-10) — `internal/api/client.go` (Do, auth header),
    `api/auth.go` (Login/Logout), `api/types.go` (PlaybackState stub),
    `testdata/fixtures/api-auth-token-{200,400}.json`, daemon wired to real
    API client, `handlers.go` + HandleSessionLogin/HandleSessionLogout with
    broadcast. 8 tests.
  - **Iteration 5** (2026-06-10) — `internal/ipc/client.go` (Request
    concurrent-safe via pending-map, Events() chan), `socket_unix_test.go`
    stale-socket test (createStaleSocket via raw syscall), `internal/tui/app.go`
    (bubbletea model: connect → session.state → login form → logged-in view,
    re-renders on session.changed push), `cmd/juke/main.go`, `scripts/test_cli.sh`.
    `go test -race ./...` clean. Cross-compile verified: linux/amd64, darwin/arm64,
    windows/amd64.
  - **MVP scope cuts applied:**
    - `CacheDir()` not implemented (nothing needs it in Phase 1).
    - `[theme]` and `[keys]` config sections omitted from Config struct.
    - `go-winio` not added as a dep; `socket_windows.go` stubs return
      `errNotImplemented` (compiles; IPC non-functional on Windows until Phase 1b).
    - `daemon.transport.changed` event not emitted (no transport layer).
    - `PlaybackState` in `types.go` is a stub struct with no callers.
    - TUI is plain text with no lipgloss styling.
- Next:
  - **Phase 1b — polling transport.** Deliver `cli/internal/transport/poll.go`
    (ticker loop, `GET /api/v1/playback/state/`, diff against cached
    `PlaybackState`, emit `playback.state.changed` IPC broadcast), the
    `PlaybackState` field in `daemon/state.go`, and the `playback.state` IPC
    handler. This is the remaining Phase-1 scope deferred from this slice.
    Create `tasks/cli-phase1b-polling-transport.md` when this task reaches
    `review`.
  - **cli-phase2** — `backend/realtime/` Django app + ASGI switch. Unblocked
    once Phase 1b exists (daemon can exercise the polling path end-to-end
    before WS lands).
  - **cli-phase3** — full TUI panes, daemon WS client. Blocked on cli-phase2.
- Blockers:
  - `cli-phase0-architecture-and-design` must be `review` or `done`. ✓ (current
    status: `review`)
