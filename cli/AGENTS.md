# Juke CLI — Agent Guide

## Scope

The `cli/` subproject ships two Go binaries:

- **`juked`** — background daemon. Owns the auth token, the backend connection
  (WebSocket or polling), the playback state cache, and the IPC socket. Runs
  under systemd/launchd/Windows-service. Survives terminal close.
- **`juke`** — interactive TUI. Stateless bubbletea client that connects to
  `juked` over a local socket. Instant-start, multi-instance-safe, disposable.

The daemon talks to the same Django `/api/v1/*` surface as web and mobile.
No CLI-specific backend endpoints. Auth header: `Authorization: Token <key>`.

**Read before working:**
- `docs/arch/cli-juke-terminal-architecture.md` — decisions locked, IPC
  protocol, transport layer, backend `realtime/` app design, phase roadmap.
- `docs/arch/cli-juke-tux-designs.md` — pane layouts, keybindings, responsive
  collapse rules. Every pane you build has a mockup here.

## Status

Phase 0 complete (architecture + design). No Go code yet — Phase 1 delivers
`go.mod`, daemon skeleton, IPC protocol, auth, polling transport. See
`tasks/cli-phase1-daemon-ipc-auth-foundation.md` for the first implementation
task.

## Stack

| Concern | Choice | Why |
|---|---|---|
| Language | Go (version pinned in `go.mod` once it exists) | Static binaries, trivial cross-compile, no user-side runtime deps |
| TUI | `github.com/charmbracelet/bubbletea` + `lipgloss` + `bubbles` | Elm-architecture event loop, best-in-class terminal rendering |
| CLI flags | `github.com/spf13/cobra` | Standard subcommand surface (`juked install`, `juke --config ...`) |
| WebSocket | `github.com/gorilla/websocket` | Mature, lets us set the `Authorization` header on handshake |
| Windows pipes | `github.com/Microsoft/go-winio` | IPC on Windows (no Unix sockets) |
| Config | `github.com/BurntSushi/toml` | TOML, no reflection magic |
| HTTP | `net/http` (stdlib) | No need for a heavier client |

**`CGO_ENABLED=0` always.** If a dependency needs cgo, find a different
dependency. Static binaries are the whole reason we picked Go.

## Directory Layout

This is forward-looking — the tree fills in as phases land. See arch doc §9
for the full annotated version.

```
cli/
├── AGENTS.md                  # this file
├── go.mod  go.sum             # phase 1
├── cmd/
│   ├── juked/main.go          # daemon entrypoint
│   └── juke/main.go           # TUI entrypoint
├── internal/
│   ├── api/                   # Juke backend HTTP client
│   ├── transport/             # WS-primary / poll-fallback (daemon ↔ backend)
│   ├── ipc/                   # daemon ↔ TUI socket protocol
│   ├── daemon/                # juked wiring + IPC request handlers
│   ├── config/                # TOML load + XDG path resolution
│   ├── session/               # session.json read/write (0600)
│   └── tui/                   # bubbletea app + panes
└── testdata/fixtures/         # recorded backend responses
```

**Why `internal/` not `pkg/`:** this is an application, not a library. Go's
`internal/` is compiler-enforced private — nothing outside `cli/` can import
from it. Everything goes here.

## Conventions

### Bubbletea

Bubbletea is Elm-architecture: every pane is a `tea.Model` with
`Init() tea.Cmd`, `Update(tea.Msg) (tea.Model, tea.Cmd)`, `View() string`.
The root model in `internal/tui/app.go` composes child pane models and routes
messages based on focus.

**IPC events are tea.Msg.** The IPC client runs a goroutine that reads frames
from the socket and pushes them into the bubbletea program via `p.Send(msg)`.
The `Update` method pattern-matches on message type. This is the one
integration point between the daemon and the TUI — get it clean.

**Never block in `Update`.** If you need to wait for something, return a
`tea.Cmd` (a `func() tea.Msg`). Bubbletea runs it on a goroutine and delivers
the result as a message.

### Build tags

Platform-conditional code uses `_unix.go` / `_windows.go` suffixes with a
`//go:build` line at the top. **Only two areas need this:** IPC socket binding
(`internal/ipc/socket_*.go`) and service-unit installation
(`internal/daemon/install/*.go`). Everything else is portable. If you find
yourself adding a third tagged area, check whether you're reaching for the
wrong abstraction.

### IPC protocol

Length-prefixed JSON: 4-byte big-endian u32 length, then that many bytes of
UTF-8 JSON. Envelope fields are `id` (client-assigned, `null` for server-pushed
events), `type`, `data`. See arch doc §6 for the full message catalog.

Do not change the envelope shape. Add message types, don't add envelope fields.

### Backend API types

`internal/api/types.go` mirrors the Django serializer output. When a backend
shape changes, update here. The `PlaybackState` struct must match
`web/src/features/playback/types.ts:36-43` — `provider`, `is_playing`,
`progress_ms`, `track`, `device`, `updated_at`. Same JSON, same field names.

## Build & Test

```bash
# Build both binaries (from repo root)
cd cli && go build ./cmd/...

# Run all tests
cd cli && go test ./...

# Run with race detector (do this before any PR)
cd cli && go test -race ./...

# Cross-compile (example: linux/arm64 from macOS)
cd cli && GOOS=linux GOARCH=arm64 CGO_ENABLED=0 go build -o dist/juked-linux-arm64 ./cmd/juked
```

`scripts/test_cli.sh` wraps `go test -race ./...` plus `go vet` and
`staticcheck`. Script lands in Phase 1.

**Integration with the backend:** the `internal/api/` tests hit recorded
fixtures in `testdata/fixtures/`, not the live backend. For manual end-to-end,
bring up the Docker stack (`docker compose up -d backend db redis`) and point
the daemon at it via `config.toml` → `backend_url = "http://127.0.0.1:8000"`.

## Running Locally

```bash
# Terminal 1 — daemon in foreground (no service install needed for dev)
cd cli && go run ./cmd/juked --foreground

# Terminal 2 — TUI
cd cli && go run ./cmd/juke
```

The daemon writes its socket path to stderr on startup. If the TUI can't find
the socket, it prints the resolved path it tried — compare the two.

## Debugging the IPC Socket

You can talk to `juked` without the TUI. The protocol is length-prefixed JSON,
so you need a tiny length-prefix helper. One-liner for a `session.state` probe:

```bash
# Linux: XDG_RUNTIME_DIR is usually /run/user/$UID
SOCK="${XDG_RUNTIME_DIR:-/tmp}/juke.sock"
MSG='{"id":1,"type":"session.state","data":{}}'
python3 -c "import sys,struct; b=sys.argv[1].encode(); sys.stdout.buffer.write(struct.pack('>I',len(b))+b)" "$MSG" \
  | socat - "UNIX-CONNECT:$SOCK" \
  | xxd
```

The first 4 bytes of the response are the length prefix; the rest is JSON.
If the daemon also pushes a `playback.state.changed` event while you're
connected, you'll see a second frame with `"id":null`.

For Windows: PowerShell + `System.IO.Pipes.NamedPipeClientStream` against
`\\.\pipe\juke`. Same framing.

## Config & Session Paths

| OS | Config | Session | Socket |
|---|---|---|---|
| Linux | `~/.config/juke/config.toml` | `~/.local/share/juke/session.json` | `$XDG_RUNTIME_DIR/juke.sock` |
| macOS | `~/Library/Application Support/Juke/config.toml` | `~/Library/Application Support/Juke/session.json` | `~/Library/Application Support/Juke/juke.sock` |
| Windows | `%APPDATA%\Juke\config.toml` | `%APPDATA%\Juke\session.json` | `\\.\pipe\juke` |

**`session.json` is written mode 0600.** It contains the auth token. If a test
needs to write a session file, use `internal/session/store.go` — don't write
the file directly, you'll get the perms wrong.

The TUI never touches `session.json`. It asks the daemon for session state
over IPC. Only `juked` has the code path to that file.

## Cross-Platform Gotchas

- **Terminal detection:** lipgloss auto-detects truecolor via `$COLORTERM`.
  Windows Terminal sets it correctly; `cmd.exe` does not. Don't hardcode
  color profiles — let lipgloss degrade.
- **Socket cleanup:** Unix sockets leave a file behind if the daemon crashes.
  On startup, `juked` tries to connect to the existing socket path first; if
  connection refused, it unlinks the stale file and rebinds. Named pipes on
  Windows don't have this problem — they vanish with the process.
- **Path separators:** always `filepath.Join`, never string-concat with `/`.
  This is Go 101 but it's the #1 source of Windows-only bugs.
- **SIGTERM vs Ctrl+C:** the daemon must handle both. `signal.Notify` with
  `syscall.SIGINT, syscall.SIGTERM` on Unix; on Windows, `os.Interrupt` covers
  Ctrl+C and service-stop sends `svc.Stop` via the service handler.

## Phase Task Files

| Phase | Task | What it delivers |
|---|---|---|
| 0 | `tasks/cli-phase0-architecture-and-design.md` | This — docs + task generation |
| 1 | `tasks/cli-phase1-daemon-ipc-auth-foundation.md` | Go module, daemon, IPC, auth, polling |
| 2 | `tasks/cli-phase2-backend-websocket-transport.md` | Django `realtime/` app, ASGI switch |
| 3 | `tasks/cli-phase3-catalog-playback-tui.md` | Search + playback panes, daemon WS client |
| 4 | `tasks/cli-phase4-recommendations-and-facts.md` | Recs + fun-facts sidebar |
| 5 | `tasks/cli-phase5-direct-messaging.md` | DM pane |
| 6 | `tasks/cli-phase6-music-generation.md` | Gen pane |

Phases 4–6 run in parallel once Phase 3 is done.
