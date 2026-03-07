---
id: cli-phase3-catalog-playback-tui
title: Juke CLI Phase 3 - Catalog browsing, playback controls, and daemon WS client
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
updated_at: 2026-03-06
---

## Goal

Turn the Phase 1 stub TUI into the real thing for the core loop: search →
browse catalog → play → control. Wire the daemon's WebSocket transport client
(cli-phase2 shipped the backend). At the end of this phase the CLI is usable
daily — you can search for an album, play it, skip tracks, and watch the
playback bar update in real time over WS.

## Scope

**Daemon side (`cli/internal/`):**
- `transport/ws.go` — `gorilla/websocket` client. Dials
  `wss://<backend>/ws/v1/playback/` with `Authorization: Token <key>` on the
  handshake. Reconnect with exponential backoff (1s → 30s, ±25% jitter per
  arch §5). On WS connect, send `{"type": "sync"}` to hydrate. On any failure,
  fall back to phase1's poller. The 10s drift poll **keeps running** even when
  WS is healthy, to catch Spotify-app-initiated changes (the honest gap).
- `api/` — add catalog endpoints: genres/artists/albums/tracks list + detail,
  search. Mirror Django serializer shapes. Add playback control calls
  (`play`/`pause`/`next`/`previous`/`seek` with the `PlayRequest`/`ControlRequest`
  shapes from `web/src/features/playback/api/playbackApi.ts`).
- `daemon/` — new IPC handlers: `catalog.search`, `catalog.genres`,
  `catalog.artists`, `catalog.albums`, `catalog.tracks`, `catalog.album.tracks`,
  `playback.play`, `playback.pause`, `playback.next`, `playback.previous`,
  `playback.seek`. Handlers are thin: unmarshal → call `api/` → marshal.

**TUI side (`cli/internal/tui/`):**
- `app.go` — root model composing child panes, focus routing, responsive
  collapse (sidebar drops <100 cols, nav drops <80, refuse <60).
- `panes/nav.go` — left 16ch rail. Library/Search/Messages/Generate.
- `panes/library.go` — genre → artist → album → track drill-down. Breadcrumb.
  `bubbles/list` for each level.
- `panes/search.go` — `/` overlay. `bubbles/textinput` + live-filtered results.
  Section filters (`[g]/[a]/[A]/[t]`).
- `panes/playback.go` — bottom 3-row persistent bar. Track/artist/album,
  progress bar, play/pause glyph, `ws`/`poll` indicator. Handles
  `playback.state.changed` messages from IPC.
- `panes/album.go` — track list. `♪` glyph on currently-playing. Enter plays
  with `context_uri` = album + `offset_uri` = track (same model as web per
  `tasks/web-playback-next-track.md`).
- `keys.go` — keybinding map. Vim defaults (`j`/`k`/`h`/`l`, `/`, `space`,
  `n`/`p`, `g`/`G`, `?`, `:`). Loaded from `config.toml [keys]` with fallback.
- `overlays/help.go` — `?` overlay. Full keybind reference.
- `overlays/command.go` — `:` palette. `:login`, `:logout`, `:connect spotify`,
  `:config edit`, `:daemon restart`, `:theme <name>`.
- `styles.go` — lipgloss styles. Theme colors from `config.toml [theme]`,
  mirroring the `JukePlatformPalette` keys from Android/iOS.
- Tests for the root model's message routing (focus moves on `h`/`l`, search
  opens on `/`, `playback.state.changed` reaches the playback pane regardless
  of focus).

## Out Of Scope

- Now-playing sidebar content (FACTS/FLOWS INTO). Phase 4.
- Messages pane. Phase 5.
- Generate pane. Phase 6.
- Album art rendering (sixel/kitty/iterm2). Arch §2 defers this. Leave a
  placeholder block in the sidebar for now.
- `juked install` platform implementations. Still stubbed from Phase 1.

## Acceptance Criteria

- Daemon connects to `ws://127.0.0.1:8000/ws/v1/playback/` against a local
  Docker stack, and falls back to polling when the backend is run WSGI-only.
  The TUI's `ws`/`poll` indicator reflects which path is active.
- `POST /api/v1/playback/pause/` via curl causes a WS frame → daemon cache
  update → IPC push → TUI playback bar re-render, with no poll cycle in between.
- Search overlay filters live as you type and Enter on a track plays it.
- Album detail view plays the selected track with context so Spotify's own
  next-track advances through the album (parity with
  `tasks/web-playback-next-track.md`).
- Playback bar keybinds work globally: `space` toggles play/pause, `n`/`p`
  skip, regardless of which pane has focus.
- Responsive collapse behaves per the TUX doc table at 100/80/60 column widths.
- `go test -race ./...` passes. WS reconnect loop is the main new race surface.

## Execution Notes

- Program linkage: phase3 of the `cli` program. Depends on phase1 (daemon+IPC)
  and phase2 (backend WS). Unblocks phases 4/5/6 in parallel.
- Read first:
  - `docs/arch/cli-juke-tux-designs.md` — every pane built here has a mockup.
    Match the mockup. Box-drawing chars, glyphs, column widths are all specified.
  - `docs/arch/cli-juke-terminal-architecture.md` §5 (WS event schema +
    reconnect backoff), §6 (IPC catalog — add the new message types there too).
  - `cli/AGENTS.md` — "IPC events are tea.Msg" and "never block in Update"
    matter most here. Every IPC request from a pane is a returned `tea.Cmd`;
    the response arrives later as a `tea.Msg`.
- Key files:
  - `cli/internal/transport/ws.go`
  - `cli/internal/api/{catalog,playback}.go`
  - `cli/internal/daemon/handlers_{catalog,playback}.go`
  - `cli/internal/tui/{app,keys,styles}.go`
  - `cli/internal/tui/panes/{nav,library,search,playback,album}.go`
  - `cli/internal/tui/overlays/{help,command}.go`
  - `web/src/features/playback/api/playbackApi.ts` (request shape reference)
  - `backend/catalog/urls.py` (endpoint path reference)
  - `docs/arch/cli-juke-tux-designs.md` (mockups)
- Commands:
  - `cd cli && go build ./cmd/...`
  - `cd cli && go test -race ./...`
  - `./scripts/test_cli.sh`
  - Manual: `docker compose up -d backend db redis` →
    `go run ./cmd/juked --foreground` → `go run ./cmd/juke`
- Risks:
  - **Focus routing is where the root model gets messy.** The temptation is to
    have every pane handle every key. Instead: global keys (space, `n`/`p`, `?`,
    `:`, `/`) are intercepted by the root model before dispatch; all other keys
    go only to the focused child. Write this first and test it before building
    panes.
  - `gorilla/websocket` doesn't auto-pong. The reconnect loop needs a read
    deadline + pong handler or it will hang on a silently-dropped connection.
  - `bubbles/list` default key handling conflicts with `h`/`l` nav. Disable its
    built-in keymap and drive it from the root.
  - Lipgloss width calculations on CJK / emoji are notoriously wrong. The TUX
    design uses only ASCII + box-drawing + a handful of ambiguous-width glyphs
    (`♪`, `▸`, `●`) — if those look off, swap to ASCII equivalents (`>`, `*`).

## Handoff

- Completed:
- Next:
  - Phases 4, 5, 6 are parallel-capable. Each adds one pane + daemon handlers.
- Blockers:
  - `cli-phase1-daemon-ipc-auth` must be `done`.
  - `cli-phase2-backend-ws-transport` must be `done`.
