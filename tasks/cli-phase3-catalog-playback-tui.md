---
id: cli-phase3-catalog-playback-tui
title: Juke CLI Phase 3 — Catalog browsing, playback controls, and daemon WS client
status: ready
priority: p1
owner: unassigned
area: cli
label: CLI
labels:
  - juke-task
  - cli
  - go
  - tui
complexity: 4
updated_at: 2026-06-10
---

## Goal

Turn the Phase 1 status screen into a usable daily-driver: search for music,
drill into albums, play tracks, control playback with the keyboard, and watch
the playback bar update in real time over WebSocket.

Replace the polling-only transport from Phase 1b with WS-primary / poll-fallback
(WS connects to the Phase 2 backend endpoint; polling stays as the degraded path
and as the 10s Spotify-drift safety net). Wire all catalog and playback IPC
handlers. Build the full pane layout per the TUX design doc.

End state: `juke` opens on a fully-laid-out terminal screen. Press `/` to search
"miles davis", Enter on a result, Enter on an album, Enter on a track → it starts
playing on Spotify. The playback bar at the bottom updates live. `space` pauses.
`n`/`p` skip. All keybinds work from any pane.

---

## Scope

### Daemon — `cli/internal/`

**`transport/ws.go`** — real `gorilla/websocket` client replacing the Phase 1b stub.
- Dials `<backend_url>/ws/v1/playback/` with `Authorization: Token <key>` on
  the HTTP handshake (not a query param — daemon clients can set headers, unlike
  browsers).
- On connect: sends `{"type": "sync"}` to hydrate state immediately.
- Reconnect: exponential backoff 1s → 30s, ±25% jitter. On reconnect, re-sends
  `sync`. Emits `daemon.transport.changed` event on connect/disconnect.
- Sets a read deadline + pong handler to detect silently dropped connections
  (gorilla/websocket does not auto-pong).
- On any failure: signals manager to fall back to `PollTransport`.

**`transport/manager.go`** — update to attempt WS first. When WS connects,
pause the poll ticker (keep goroutine alive; resume on WS failure). The 10s
drift poll continues regardless: it runs as a second, slower check even when WS
is healthy, catching Spotify-app-initiated changes (arch doc §5.3 honest gap).

**`api/catalog.go`** — backend calls mirroring `backend/catalog/urls.py`:
- `SearchCatalog(query string, kinds []string, limit int) (*SearchResults, error)`
- `GetArtist(id string) (*Artist, error)`
- `GetAlbum(id string) (*Album, error)`
- `GetAlbumTracks(albumID string) ([]*Track, error)`

**`api/playback.go`** — extend with control calls. Shapes from
`web/src/features/playback/api/playbackApi.ts`:
- `Play(req PlayRequest) (*PlaybackState, error)`
- `Pause(deviceID string) (*PlaybackState, error)`
- `Next(deviceID string) (*PlaybackState, error)`
- `Previous(deviceID string) (*PlaybackState, error)`
- `Seek(positionMs int, deviceID string) (*PlaybackState, error)`

**`daemon/handlers_catalog.go`** — IPC handlers for:
`catalog.search`, `catalog.artist`, `catalog.album`.
Each: unmarshal request data → call `api/` → marshal response. Cache TTL for
search results: 60s in `~/.cache/juke/catalog/` (keyed by query hash).

**`daemon/handlers_playback.go`** — IPC handlers for:
`playback.play`, `playback.pause`, `playback.next`, `playback.previous`,
`playback.seek`. Each: call `api/` → update cached `PlaybackState` → broadcast
`playback.state.changed` → return new state. On `*APIError` (e.g. no active
device), return IPC `error` with `code: "no_device"` so the TUI can show a
helpful message.

### TUI — `cli/internal/tui/`

**`app.go`** — root `tea.Model`. Composes child pane models. Focus routing:
- Global keys (`space`, `n`, `p`, `/`, `?`, `:`, `q`) intercepted by root
  before dispatch to any child.
- `h`/`l` or `Tab`/`Shift+Tab` move focus between nav, content, sidebar.
- `playback.state.changed` IPC events routed to the playback pane regardless
  of focus.
- Responsive collapse: sidebar drops below 100 cols; nav drops below 80 cols;
  refuse to render below 60 cols (show a "terminal too narrow" message).

**`keys.go`** — `KeyMap` struct. Defaults: `j`/`k` nav, `h`/`l` pane switch,
`/` search, `space` play/pause, `n`/`p` skip, `g`/`G` top/bottom, `?` help,
`:` command palette, `q` quit. Loaded from `config.toml [keys]` with fallback
to defaults when key is absent.

**`styles.go`** — lipgloss `Style` palette. Colors from `config.toml [theme]`,
falling back to the Juke orange (`#ff8c42`) accent. Matches `JukePlatformPalette`
key names from `fm.juke.core` for visual consistency across clients.

**`panes/nav.go`** — 16ch left rail. Items: Library, Messages (Phase 5),
Generate (Phase 6). Inactive items greyed out. `j`/`k` navigate,  `Enter`
activates. Shows active indicator (`▶`).

**`panes/library.go`** — genre → artist → album → track drill-down. Breadcrumb
header showing current path. `bubbles/list` at each level (list keymap disabled;
driven by root model). `Enter` descends; `Backspace`/`h` ascends; `Enter` on a
track plays with `context_uri = album_uri, offset_uri = track_uri` (same album
context model as `tasks/web-playback-next-track.md`).

**`panes/search.go`** — `/` overlay. `bubbles/textinput` for query.
Section toggles `[g]/[a]/[A]/[t]` filter by kind. Results update as you type
(debounce 200ms, min 2 chars). `Enter` on a result navigates: artist → library
pane at that artist; album → album detail; track → plays immediately. `Esc`
closes overlay.

**`panes/playbackbar.go`** — persistent 3-row bottom bar. Row 1: track name
(truncated), artist, album. Row 2: progress bar (lipgloss), `MM:SS / MM:SS`.
Row 3: `|◀  ▶  ▶|` glyphs (prev/play-pause/next), volume %, transport mode
indicator (`ws` in green, `poll` in yellow). Handles `playback.state.changed`
IPC pushes. Renders `-- not connected --` when daemon disconnects.

**`panes/album.go`** — track list. `♪` glyph on the currently-playing track
(matched by URI). `Enter` plays with album context.

**`overlays/help.go`** — `?` overlay. Full keybind reference table from
`keys.go`. Dismisses on `?` or `Esc`.

**`overlays/command.go`** — `:` palette. Commands: `:login`, `:logout`,
`:config edit` (opens `$EDITOR`), `:daemon restart`, `:connect spotify`
(placeholder for Phase 3+ Spotify auth flow).

---

## Out Of Scope

- Now-playing sidebar (FACTS section, FLOWS INTO recommendations). Phase 4.
- Messages pane. Phase 5.
- Generate pane. Phase 6.
- Album art rendering (sixel/kitty/iterm2). Arch §2.13 defers this; leave a
  placeholder block in the sidebar.
- `juked install` platform implementations. Still stubbed.
- `?token=` query-param WS auth (only needed for browser clients).

---

## Testing

### Unit tests — `internal/transport`

**`TestWSTransportConnectsWithAuthHeader`**
Start an `httptest.Server` that upgrades to WebSocket and records the
`Authorization` header on the handshake. Assert the header value is
`"Token <key>"`. Assert the client sends `{"type": "sync"}` as the first
frame after connecting.

**`TestWSTransportReconnectsAfterDisconnect`**
Server accepts one connection then closes it. Assert `ws.Transport` reconnects
within `2 * initialBackoff` (mock `time.Sleep` or use a short backoff in tests).
Assert it sends `sync` again on reconnect.

**`TestWSTransportFallsBackOnDialFailure`**
Configure `Manager` with a WS URL pointing to a closed port. Assert
`Manager.Mode()` returns `"polling"` within the fallback timeout.

**`TestManagerDriftPollContinuesWhileWSActive`**
WS mock server stays connected. Assert that `PollTransport` still ticks (at
least once during the test window) even though WS is active — verifying the
drift poll is never disabled.

**`TestManagerTransportChangedEvent`**
WS connects successfully. Assert a `daemon.transport.changed` IPC broadcast
with `mode: "websocket"`. Disconnect WS server. Assert a second broadcast
with `mode: "polling"`.

### Unit tests — `internal/api`

**`TestSearchCatalog`**
Mock server returns a fixture with one artist, one album, one track. Assert
`SearchResults` populates all three slices correctly.

**`TestPlayReturnsUpdatedState`**
Mock server returns a `PlaybackState` with `IsPlaying: true`. Assert
`api.Play(req)` returns it and the daemon cache is updated.

**`TestPlayAPIError`**
Mock server returns HTTP 404 with `{"detail": "no active device"}`. Assert
`*APIError{StatusCode: 404}` is returned (not a `*NetworkError`).

### Unit tests — `internal/daemon`

**`TestHandlersCatalogSearchRoutes`**
Dispatch table routes `catalog.search` to the handler, not an unknown-type
error.

**`TestHandlersPlaybackPlayBroadcasts`**
Mock API returns a new state. `HandlePlaybackPlay` updates daemon state and
broadcasts `playback.state.changed`. Assert broadcast fires exactly once.

**`TestHandlersPlaybackNoDeviceReturnsError`**
Mock API returns `*APIError{StatusCode: 404}`. Handler returns IPC
`{"type": "error", "data": {"code": "no_device", ...}}`. Assert no broadcast.

### Unit tests — `internal/tui`

**`TestRootModelGlobalKeys`**
Feed `space`, `n`, `p` key messages to the root model from different focus
states (nav focused, library focused, search open). Assert a playback IPC
command is returned as a `tea.Cmd` in every case — global keys are never
swallowed by child panes.

**`TestRootModelFocusRouting`**
Feed `h` and `l` keys. Assert focus index cycles through nav → content →
sidebar → nav. Feed `tab`. Assert same cycle.

**`TestRootModelPlaybackPushUpdatesBar`**
Send a `playback.state.changed` IPC message to the root model regardless of
current focus (nav, search overlay, command palette open). Assert the playback
bar model receives the update in all three cases.

**`TestSearchOverlayOpenClose`**
Feed `/` key to root. Assert search overlay is open. Feed `Esc`. Assert closed.
Assert focus returns to previous pane.

**`TestResponsiveCollapse`**
Send `tea.WindowSizeMsg{Width: 95, Height: 40}` — assert sidebar not rendered.
Send `{Width: 75}` — assert nav not rendered. Send `{Width: 55}` — assert
"terminal too narrow" message rendered.

### `scripts/test_cli.sh`

```bash
./scripts/test_cli.sh
```

Must exit 0. Pay particular attention to the race detector on the WS
reconnect loop — that is the primary new race surface.

---

## Acceptance Criteria

- `go test -race ./...` passes. WS reconnect goroutine and `Broadcast` calls
  are the primary race surfaces.
- Daemon connects to `ws://127.0.0.1:8000/ws/v1/playback/` and the TUI's
  transport indicator shows `ws`.
- `POST /api/v1/playback/pause/` via curl causes a playback bar update in the
  TUI in < 1 second (WS push, not poll cycle).
- When backend is started in WSGI mode (e.g. a non-upgraded dev server), daemon
  falls back to polling and indicator shows `poll`.
- Search: `/` opens overlay, typing "miles davis" returns results, pressing
  Enter on "Kind of Blue" opens album detail, pressing Enter on "So What" starts
  playback on Spotify.
- Album context: after playing a track via the album pane, pressing `n` (or
  next in Spotify's own UI) advances to the next track in the album — not a
  random track. This validates `context_uri` + `offset_uri` are set correctly.
- `space` pauses/resumes regardless of which pane has focus.
- Responsive collapse: sidebar hides below 100 cols; nav hides below 80; error
  message shown below 60.
- `?` overlay lists all keybindings. `:logout` from the command palette calls
  `session.logout` IPC, clears the token, returns to login screen.

---

## Execution Notes

- **Program linkage:** phase3 of the `cli` program. Depends on phase1b (daemon
  transport interface) and phase2 (backend WS endpoint). Unblocks phases 4, 5,
  6 in parallel.
- **Focus routing is load-bearing.** The root model intercepts global keys
  before dispatching to children. Write `TestRootModelGlobalKeys` first. If
  a child pane accidentally handles `space`, playback controls stop working in
  that pane — this is the #1 source of subtle bugs.
- **`bubbles/list` default keymap conflicts.** `bubbles/list` handles `j`/`k`
  and also `h`/`l` in some versions. Disable its built-in keymap entirely and
  drive it only from root model dispatch.
- **`gorilla/websocket` does not auto-pong.** Set `SetReadDeadline` on the
  connection and `SetPongHandler` to reset it. Without this, a silently-dropped
  connection hangs the read goroutine indefinitely — the reconnect loop never
  fires.
- **lipgloss width on non-ASCII glyphs.** `♪`, `▸`, `▶`, `⏸`, `●` are
  ambiguous-width. Use `lipgloss.Width()` (not `len()`) for truncation. If
  glyphs render wrong in the target terminal, fall back to ASCII (`>`, `*`).
- **Read first:**
  - `docs/arch/cli-juke-tux-designs.md` — every pane has an ASCII mockup.
    Match column widths, glyph choices, and collapse behaviour exactly.
  - `docs/arch/cli-juke-terminal-architecture.md` §5 (WS reconnect backoff,
    drift poll), §6 (IPC catalog — add the new message types there).
  - `web/src/features/playback/api/playbackApi.ts` — playback request shapes.
  - `backend/catalog/urls.py` — catalog endpoint paths.
  - `tasks/web-playback-next-track.md` — the album context model this phase
    must match.
- **Key files:**
  - `cli/internal/transport/ws.go`, `manager.go`
  - `cli/internal/api/{catalog,playback}.go`
  - `cli/internal/daemon/handlers_{catalog,playback}.go`
  - `cli/internal/tui/{app,keys,styles}.go`
  - `cli/internal/tui/panes/{nav,library,search,playbackbar,album}.go`
  - `cli/internal/tui/overlays/{help,command}.go`

---

## To Test This

```bash
# 1. Full stack up (Phase 2 must be merged first)
docker compose up -d backend db redis

# 2. Rebuild CLI
./scripts/setup_cli.sh

# 3. Two terminals
juked --foreground     # Terminal 1 — watch for "transport: websocket"
juke                   # Terminal 2

# 4. In the TUI:
#   - Log in
#   - Press / → type "miles davis" → Enter on an album
#   - Enter on a track → it plays on Spotify
#   - Press space → pauses
#   - Press n → next track
#   - Press ? → help overlay
#   - Press :logout → returns to login screen

# 5. Verify WS push (< 1s update):
curl -s -X POST http://localhost:8000/api/v1/playback/pause/ \
  -H "Authorization: Token <token>"
# TUI playback bar updates immediately, not on the next 10s poll tick

# 6. Verify fallback (stop the backend, restart it without ASGI):
#    Transport indicator should switch from "ws" to "poll" and back
```

---

## Handoff

- Completed:
- Next:
  - Phases 4, 5, 6 are parallel-capable after this lands. Each adds one pane
    and a set of daemon handlers on top of the foundation built here.
- Blockers:
  - `cli-phase1b-polling-transport` must be `review`/`done`.
  - `cli-phase2-backend-ws-transport` must be `review`/`done`.
