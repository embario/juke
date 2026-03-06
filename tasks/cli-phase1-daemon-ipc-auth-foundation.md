---
id: cli-phase1-daemon-ipc-auth
title: Juke CLI Phase 1 - Daemon skeleton, IPC protocol, auth, polling transport
status: ready
priority: p1
owner: unassigned
area: cli
label: CLI
labels:
  - juke-task
  - cli
  - go
complexity: 4
updated_at: 2026-03-06
---

## Goal

Bring up `juked` as a runnable daemon that binds an IPC socket, speaks the
length-prefixed JSON protocol, holds a DRF auth token, and keeps a playback
state cache warm via **polling** (no WebSocket yet). Bring up `juke` as a
minimal TUI stub that connects, shows session + playback state, and exits
cleanly. The end state is: two terminals, daemon in one, TUI in the other,
and the TUI updates when you change playback from the web app.

## Scope

- `cli/go.mod` + `cli/go.sum` — Go version pin, deps from arch doc §2.
- `cli/cmd/juked/main.go` — daemon entry. `--foreground` flag for dev.
  `install` subcommand scaffold (implementation stubs per-OS).
- `cli/cmd/juke/main.go` — TUI entry.
- `cli/internal/config/` — TOML load, XDG path resolution (Linux/macOS/Windows).
- `cli/internal/session/` — `session.json` read/write with mode 0600 enforced.
- `cli/internal/api/` — HTTP client for `/api/v1/auth/api-auth-token/`,
  `/api/v1/playback/state/`. `PlaybackState` struct mirroring
  `web/src/features/playback/types.ts:36-43`.
- `cli/internal/transport/poll.go` — ticker loop hitting `state/`, pushing
  diffs into the daemon's cache. WS stub that always fails → forces poll path.
- `cli/internal/ipc/` — framing codec, server (daemon side), client (TUI side).
  `socket_unix.go` / `socket_windows.go` with build tags. Stale-socket cleanup.
- `cli/internal/daemon/` — wires config + session + transport + IPC. Handlers
  for `session.state`, `session.login`, `session.logout`, `playback.state`.
  Emits `playback.state.changed` pushes when transport delivers a diff.
- `cli/internal/tui/` — root `tea.Model`, IPC client goroutine doing `p.Send(msg)`,
  minimal render of login prompt + playback-state dump. No panes yet.
- `cli/testdata/fixtures/` — recorded responses for `api-auth-token` and
  `playback/state`.
- `scripts/test_cli.sh` — `go vet ./... && staticcheck ./... && go test -race ./...`.

## Out Of Scope

- WebSocket transport client (Phase 3, after cli-phase2 ships the backend).
- Any TUI panes beyond a dumb status screen. Search/playback/recs/DM/gen are
  Phases 3–6.
- `juked install` platform implementations — scaffold the cobra subcommand and
  the `internal/daemon/install/` directory but leave the service-file writers
  as `TODO` returning `errors.New("not yet implemented")`.
- `backend/realtime/`. That is cli-phase2.
- Playback control IPC handlers (`playback.play`/`pause`/`next`/`prev`/`seek`).
  Phase 3 — the TUI has no controls to trigger them yet.

## Acceptance Criteria

- `cd cli && go build ./cmd/...` produces `juked` and `juke` binaries on
  linux/amd64, darwin/arm64, windows/amd64 with `CGO_ENABLED=0`.
- Daemon started with `--foreground` prints the bound socket path to stderr.
- The `socat` one-liner from `cli/AGENTS.md` §Debugging returns a well-formed
  length-prefixed `session.state` response from a running daemon.
- `session.json` is written with mode 0600 (0600 test that fails if perms widen).
- Stale-socket test: kill -9 a running daemon, start a new one, it rebinds the
  same path without `address already in use`.
- Polling loop updates the daemon cache and pushes a `playback.state.changed`
  frame to a connected TUI when backend state differs from cache.
- TUI shows "not logged in" → login prompt (`session.login` over IPC) →
  playback state render, and re-renders on push.
- `scripts/test_cli.sh` passes in repo root.
- `go test -race ./...` passes (IPC server with concurrent clients is the main
  race surface).

## Execution Notes

- Program linkage: phase1 of the `cli` program. Depends on phase0 (docs). Feeds
  phase2 (backend WS) which in turn unblocks phase3's WS client.
- Read first:
  - `docs/arch/cli-juke-terminal-architecture.md` §4 (process model), §5
    (transport), §6 (IPC protocol + message catalog), §8 (config/session paths),
    §9 (package layout).
  - `cli/AGENTS.md` — all of it. The "never block in Update" and "IPC events are
    tea.Msg" rules are the load-bearing bubbletea patterns.
- Key files:
  - `cli/go.mod`
  - `cli/cmd/juked/main.go`, `cli/cmd/juke/main.go`
  - `cli/internal/{config,session,api,transport,ipc,daemon,tui}/`
  - `cli/internal/ipc/socket_unix.go`, `cli/internal/ipc/socket_windows.go`
  - `cli/testdata/fixtures/playback_state.json`
  - `scripts/test_cli.sh`
  - `web/src/features/playback/types.ts:36-43` (PlaybackState shape reference)
  - `backend/juke_auth/urls.py` (auth endpoint path reference)
- Commands:
  - `cd cli && go mod init github.com/<org>/juke/cli` (org TBD — check other
    go.mod files in repo or ask)
  - `cd cli && go build ./cmd/...`
  - `cd cli && go test -race ./...`
  - `./scripts/test_cli.sh`
  - Manual e2e: `docker compose up -d backend db redis` then
    `cd cli && go run ./cmd/juked --foreground` in one terminal,
    `go run ./cmd/juke` in another.
- Risks:
  - **Framing bugs are silent.** A length-prefix off-by-one reads garbage JSON
    on the next frame, not this one. Write the codec tests first (round-trip,
    short-read, concurrent-write) before anything uses it.
  - **Windows CI.** `go-winio` named pipes don't work in GitHub Actions Linux
    runners. The `socket_windows.go` tests need `//go:build windows` and a
    Windows runner, or they get skipped in phase1 and verified manually.
  - **0600 on Windows.** Unix permission bits don't map to Windows ACLs. The
    session store needs a `_windows.go` variant that uses `go-acl` or accepts
    best-effort. Arch doc §8 defers this decision — decide here.
  - The polling interval (~10s per arch doc §5) is the ceiling on external-change
    latency until phase3 wires WS. Don't gold-plate the poller; it becomes the
    fallback path only.

## Handoff

- Completed:
- Next:
  - cli-phase2 delivers the backend WS transport. Once that lands, phase3
    rewrites `cli/internal/transport/` to try WS first and keep this phase's
    poller as the degraded path.
- Blockers:
  - `cli-phase0-architecture-and-design` must be `review`/`done`.
