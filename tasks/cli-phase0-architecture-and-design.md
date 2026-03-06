---
id: cli-phase0-architecture-and-design
title: Juke CLI Phase 0 - Architecture, TUX design, and roadmap generation
status: review
priority: p1
owner: codex
area: platform
label: CLI
labels:
  - juke-task
  - cli
  - architecture
  - docs
complexity: 3
updated_at: 2026-03-06
---

## Goal

Produce the locked architectural design, terminal UX design, agent handbook, and
phased task roadmap for the Juke CLI — a daemon + TUI power-user client for
Linux, macOS, and Windows. No Go code yet; this phase is the blueprint that
every later phase references.

## Scope

- Architecture document: process model, IPC protocol, transport layer (WS-primary /
  poll-fallback), backend `realtime/` app design, Go package layout, cross-platform
  strategy, phase roadmap.
- TUI/TUX design document: ASCII mockups for every pane, keybinding vocabulary,
  responsive collapse rules, state indicator glyphs.
- `cli/` directory + `cli/AGENTS.md`: stack table, conventions, build/test commands,
  IPC debugging recipe, cross-platform gotchas.
- Task files: six CLI phases (this file through phase6) + three backend dependency
  tasks (track-facts, DM foundation, music-gen).
- `tasks/_index.md` rows for all of the above.
- Execution note in `realtime-world-and-session-events-platform.md` pointing at
  cli-phase2 as the transport provider.

## Out Of Scope

- Any Go code (`go.mod`, `cmd/`, `internal/`). That is Phase 1.
- Any Django code. cli-phase2 owns the `backend/realtime/` implementation.
- CI pipeline wiring. `scripts/test_cli.sh` lands in Phase 1.
- Homebrew / apt / winget packaging. Post-phase6.

## Acceptance Criteria

- `docs/arch/cli-juke-terminal-architecture.md` exists with locked decisions,
  IPC message catalog, full `backend/realtime/` code sketch, and phase roadmap.
- `docs/arch/cli-juke-tux-designs.md` exists with mockups for main view, search
  overlay, album detail, now-playing sidebar, messages, generate, help overlay,
  and command palette.
- `cli/AGENTS.md` exists with conventions that block predictable mistakes
  (cgo, envelope-field creep, blocking in `Update`, session.json perms).
- Task files for cli-phase1..6 plus three backend-dependency tasks exist in
  `tasks/`, follow `_template.md` frontmatter, and are cross-linked via
  Execution Notes and Handoff → Blockers.
- `tasks/_index.md` has rows for every file above.

## Execution Notes

- Program linkage: this is phase0 of the `cli` program (cli-phase0 through
  cli-phase6). Phase 2 is Django work; phases 1, 3–6 are Go work.
- Key files:
  - `docs/arch/cli-juke-terminal-architecture.md`
  - `docs/arch/cli-juke-tux-designs.md`
  - `cli/AGENTS.md`
  - `tasks/cli-phase{0..6}-*.md`
  - `tasks/backend-{track-facts-llm-endpoint,direct-messaging-foundation,music-generation-service}.md`
  - `tasks/_index.md`
  - `tasks/realtime-world-and-session-events-platform.md` (cross-reference only)
- Commands: none (docs-only phase).
- Risks:
  - The WS transport (cli-phase2) crosses into backend territory. The decision
    to make the CLI roadmap own that foundation — rather than depending on
    `realtime-world-session-events` — means cli-phase2 must stay narrow enough
    to land fast. If it balloons, the whole program stalls behind Django work.
  - The three backend dependency tasks are experimental-classification and may
    never ship. Phases 4–6 are `blocked` until they do, which is by design.

## Handoff

- Completed:
  - All four documents written (arch, TUX, cli/AGENTS.md, this task file).
  - Nine downstream task files generated.
  - `tasks/_index.md` updated with ten new rows.
  - `tasks/realtime-world-and-session-events-platform.md` Execution Notes now
    point at cli-phase2 as the transport provider.
  - `docs/arch/cli-juke-terminal-architecture.md` §13 progress log reflects
    phase0 → `review`, phases 1–3 → `ready`, phases 4–6 → `blocked`.
- Next:
  - Phase 1 (`cli-phase1-daemon-ipc-auth-foundation`) is the first implementation
    task. It delivers a running daemon you can `socat` into before any TUI exists.
- Blockers:
  - None.
