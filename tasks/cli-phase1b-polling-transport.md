---
id: cli-phase1b-polling-transport
title: Juke CLI Phase 1b — Polling transport, playback state cache, and playback.state IPC
status: ready
priority: p1
owner: unassigned
area: cli
label: CLI
labels:
  - juke-task
  - cli
  - go
complexity: 3
updated_at: 2026-06-10
---

## Goal

Wire the daemon's transport layer so it polls the backend for playback state
every 10 seconds, caches the result, and broadcasts `playback.state.changed`
over IPC whenever the state changes. Add a `playback.state` IPC handler so
the TUI can ask "what's playing right now?" and receive a cached response
instantly without a backend round-trip. Update the TUI stub to display the
current track below the session line.

End state: log in from the TUI, and within 10 seconds the screen shows the
currently-playing track and artist (or "Not playing" if nothing is active).
Pause from another Juke client (web/mobile) and watch the TUI reflect it on
the next poll cycle.

This phase delivers the polling path only. The WS transport client lands in
Phase 3 once the backend endpoint exists (Phase 2). A WS stub in
`transport/ws.go` always fails, keeping the manager on the polling path for
now.

---

## Scope

- `cli/internal/transport/transport.go` — `Transport` interface:
  `Connect(ctx context.Context, updates chan<- *api.PlaybackState) error`,
  `Mode() string`, `Stop()`. `TransportMode` constants `"websocket"` and
  `"polling"`.
- `cli/internal/transport/poll.go` — `PollTransport` struct. Ticker at
  `config.Transport.PollIntervalSeconds` (default 10s). On each tick: call
  `api.Client.PlaybackState()`, compare to last-known via `reflect.DeepEqual`,
  send to updates channel only on diff. Stops cleanly when ctx is cancelled.
- `cli/internal/transport/ws_stub.go` — `WSTransport` stub. `Connect` always
  returns `errWSNotAvailable`. Mode returns `"websocket"`. Replaced in Phase 3
  with a real gorilla/websocket client.
- `cli/internal/transport/manager.go` — `Manager`. On `Start`: attempt WS;
  on failure (including the stub), start poll transport. Emits
  `daemon.transport.changed` IPC event when the active mode changes. Exposes
  `Mode() string` for the TUI indicator.
- `cli/internal/api/playback.go` — `(c *Client) PlaybackState() (*PlaybackState, error)`.
  `GET /api/v1/playback/state/`. Returns `nil, nil` when backend responds with
  no active session (204 or empty body). Returns `*NetworkError` on transport
  failure (same classification as login).
- `cli/testdata/fixtures/playback-state-playing.json` — representative playing
  state from a real backend response. Used by api tests.
- `cli/testdata/fixtures/playback-state-stopped.json` — state with
  `is_playing: false` and a track present.
- `cli/internal/daemon/state.go` — add `playback *api.PlaybackState` field.
  `SetPlaybackState(s *api.PlaybackState)`, `PlaybackState() *api.PlaybackState`.
  Both guarded by the existing `mu sync.RWMutex`.
- `cli/internal/daemon/handlers.go` — add `HandlePlaybackState(req, state)`.
  Returns the cached `*PlaybackState` immediately; no backend call.
- `cli/internal/daemon/daemon.go` — instantiate `transport.Manager`, start it
  after successful auth or on startup when a session is already present. Drain
  the updates channel in a goroutine: call `state.SetPlaybackState(s)` then
  `server.Broadcast(playback.state.changed event)`.
- `cli/internal/tui/app.go` — handle `playback.state.changed` push. Below
  the `"✓ logged in as <username>"` line add one line: `"▸ Track — Artist"`
  when playing, `"⏸ Track — Artist"` when paused, `"  Not playing"` when nil.
  This is not the full playback bar (Phase 3) — just a status line.

---

## Out Of Scope

- Real WebSocket transport client (`transport/ws.go` beyond the stub). Phase 3.
- `daemon.transport.changed` IPC event consumers in the TUI. Phase 3 (the
  `ws`/`poll` indicator lives in the playback bar).
- Playback control handlers (`playback.play/pause/next/prev/seek`). Phase 3
  (there are no controls in the TUI yet to trigger them).
- The full playback bar pane. Phase 3.
- `catalog.*` IPC handlers. Phase 3.

---

## Testing

### Unit tests — `internal/transport`

**`TestPollTransportEmitsDiff`**
Set up a mock `httptest.Server` that returns state A on the first call and
state B on the second. Start `PollTransport` with a very short interval (50ms).
Assert the updates channel receives exactly one emission (state B). Assert no
third emission when the server returns state B again.

**`TestPollTransportNoEmitSameState`**
Mock server always returns the same state. Run two poll cycles. Assert updates
channel receives zero emissions (no spurious diffs on equal state).

**`TestPollTransportContextCancel`**
Start transport. Cancel context. Assert the transport's goroutine exits within
`2 * interval` (use a `time.After` guard, not `time.Sleep`).

**`TestPollTransportNetworkError`**
Mock server closes connections immediately. Assert `PollTransport` logs the
error and continues polling (does not stop on a single network failure).

**`TestManagerModeIsPollWhenWSFails`**
Create a `Manager` with the WS stub. Call `Start`. Assert `Manager.Mode()`
returns `"polling"` immediately after the WS attempt fails.

### Unit tests — `internal/api`

**`TestPlaybackStateSuccess`**
Mock server returns `playback-state-playing.json` with HTTP 200. Assert
`client.PlaybackState()` returns a populated `*PlaybackState` with
`IsPlaying == true` and `Track.Name` matching the fixture.

**`TestPlaybackStateStopped`**
Mock server returns `playback-state-stopped.json`. Assert `IsPlaying == false`
and `Track` is present.

**`TestPlaybackStateNotPlaying`**
Mock server returns HTTP 204 (no content). Assert `nil, nil` — not an error.

**`TestPlaybackStateNetworkError`**
Mock server resets connection. Assert `*NetworkError` is returned with a clean
message (no raw TCP error strings).

### Unit tests — `internal/daemon`

**`TestHandlePlaybackStateNil`**
Daemon state has no playback set. `HandlePlaybackState` response `data` field
decodes to a JSON null or `{}`.

**`TestHandlePlaybackStateFilled`**
`state.SetPlaybackState(fixture)` called first. `HandlePlaybackState` response
`data` round-trips to a `PlaybackState` equal to the fixture.

**`TestDaemonBroadcastsPlaybackChanged`**
Wire a real `ipc.Server` in a test using `net.Pipe`. Simulate the daemon
receiving an update from the transport goroutine (call the update-drain path
directly). Assert the connected test client receives a `playback.state.changed`
frame containing the new state.

### `scripts/test_cli.sh`

```bash
./scripts/test_cli.sh
```

Must exit 0 after this phase lands. The new packages (`transport/`) are
included automatically by `./...`.

---

## Acceptance Criteria

- `go test -race ./...` passes with no data races. The transport goroutine and
  broadcast path are the new race surface.
- With Docker stack running, Spotify connected, and a track playing:
  `juked --foreground` + `juke` → log in → within 10 seconds TUI displays
  `▸ <track> — <artist>`.
- While the TUI is open, pause playback from any other Juke client (web or
  mobile); within 10 seconds TUI switches to `⏸ <track> — <artist>`.
- `playback.state` IPC response arrives in < 1ms after the first poll has
  run (cache hit, no backend call on subsequent requests).
- When no Spotify session is active, TUI displays `  Not playing`.
- `transport.Manager.Mode()` returns `"polling"` (WS stub always fails).
- Daemon handles a `PlaybackState()` API network error gracefully — logs the
  error, continues the poll loop, does not crash.

---

## Execution Notes

- **Program linkage:** phase1b of the `cli` program. Depends on phase1
  (daemon + IPC + auth). Feeds phase2 (backend WS endpoint needs a client to
  test against) and phase3 (WS client replaces the stub).
- **Read first:**
  - `docs/arch/cli-juke-terminal-architecture.md` §5 (transport layer design,
    polling fallback, honest gap re: external Spotify changes).
  - `cli/AGENTS.md` §Conventions — "IPC events are tea.Msg".
  - `web/src/features/playback/types.ts:36-43` — `PlaybackState` shape.
  - `backend/catalog/urls.py` and `backend/catalog/views.py` — confirm the
    exact path and response format for `GET /api/v1/playback/state/`.
- **Diff equality.** `reflect.DeepEqual` on the `*api.PlaybackState` struct
  works for the polling diff check, but `updated_at` changes every response
  even when nothing else changes. Either exclude `UpdatedAt` from the diff, or
  build a shallow comparison on `(IsPlaying, ProgressMs/10000, Track.URI)`.
  The arch doc §5.3 describes this as the "drift poll" — it should not fire an
  event every 10 seconds when the user is idle.
- **Poller start timing.** The transport should only start once auth is
  confirmed (token is set). Don't start polling with an empty token; the
  backend will return 401 on every tick and log noise.
- **Nil PlaybackState is valid.** The backend returns an empty or null state
  when Spotify is not connected or not playing. `PlaybackState() *api.PlaybackState`
  returning `nil` is not an error.
- **Key files:**
  - `cli/internal/transport/transport.go`, `poll.go`, `ws_stub.go`, `manager.go`
  - `cli/internal/api/playback.go`
  - `cli/internal/daemon/state.go`, `handlers.go`, `daemon.go`
  - `cli/internal/tui/app.go`
  - `cli/testdata/fixtures/playback-state-{playing,stopped}.json`
- **Commands:**
  - `cd cli && go test -race ./internal/transport/... ./internal/api/... ./internal/daemon/...`
  - `./scripts/test_cli.sh`

---

## To Test This

```bash
# 1. Rebuild
./scripts/setup_cli.sh

# 2. Start the stack
docker compose up -d backend db redis

# 3. Two terminals
juked --foreground         # Terminal 1 — watch for socket path + "transport: polling"
juke                       # Terminal 2 — log in, then within 10s:
                           #   ▸ So What — Miles Davis   (if playing)
                           #   or:  Not playing

# 4. Pause from another client, then watch the TUI update within 10s
```

---

## Handoff

- Completed:
- Next:
  - **cli-phase2** — backend WS endpoint. Once that lands, the WS stub in
    `transport/ws_stub.go` can be replaced with a real `gorilla/websocket`
    client in cli-phase3.
  - **cli-phase3** — full TUI panes + real WS client.
- Blockers:
  - `cli-phase1-daemon-ipc-auth` must be `review`/`done`. ✓
