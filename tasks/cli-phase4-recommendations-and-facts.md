---
id: cli-phase4-recs-and-facts
title: Juke CLI Phase 4 - Recommendations pane and fun-facts sidebar
status: blocked
priority: p2
owner: unassigned
area: cli
label: CLI
labels:
  - juke-task
  - cli
  - go
  - tui
complexity: 3
updated_at: 2026-03-06
---

## Goal

Fill the now-playing sidebar with its two toggleable views: **FACTS** (LLM
fun-facts about the current track, from `backend-track-facts-llm-endpoint`) and
**FLOWS INTO** (recommendations that follow naturally from the current track,
from the existing `/api/v1/recommendations/` surface). Toggle between them with
`f` / `r`. Facts fetch lazily on track change; recs refresh on demand.

## Scope

- `cli/internal/api/recommendations.go` — client for
  `/api/v1/recommendations/`. Seed with current track's `juke_id` (or
  `spotify_id` depending on where mlcore lands by then — check
  `backend/recommender/urls.py` at implementation time).
- `cli/internal/api/facts.go` — client for the new facts endpoint (path TBD by
  `backend-track-facts-llm-endpoint`).
- `cli/internal/daemon/handlers_recs.go` — IPC handlers `recs.for_track`,
  `facts.for_track`. Daemon caches facts per track (they're deterministic-ish
  and slow to generate — don't re-fetch on every `playback.state.changed`).
- `cli/internal/tui/panes/sidebar.go` — the 32ch right column. Two sub-models:
  `facts` and `flows`. `f`/`r` toggle focus between them. `bubbles/viewport`
  for scrolling fact text. Enter on a FLOWS INTO item plays it (reuses
  phase3's `playback.play` IPC path).
- On `playback.state.changed` with a new track ID: sidebar emits a `tea.Cmd`
  to fetch facts + recs. Show a spinner until they arrive.

## Out Of Scope

- Any changes to the recommender backend. This consumes it as-is.
- Fact caching persistence across daemon restarts. In-memory only.
- Rating/feedback on recommendations. Read-only surface.

## Acceptance Criteria

- Sidebar shows FACTS by default after a track starts, with a spinner during
  fetch and 2–3 wrapped fact paragraphs once loaded.
- `r` switches to FLOWS INTO with a list of 5–8 recommended tracks. `f`
  switches back. `j`/`k` scroll the focused sub-pane.
- Enter on a FLOWS INTO item triggers playback. The sidebar then refreshes for
  the new track.
- Facts cache hits: playing track A → track B → track A re-shows A's facts
  without a new backend call (daemon-side cache).
- Sidebar gracefully shows "—" when the facts endpoint returns empty/error
  (don't block the rest of the UI on LLM failures).
- Responsive: when terminal width drops below 100 cols, the sidebar collapses
  entirely and `f`/`r` become no-ops (phase3's collapse logic handles the
  layout; this phase just handles the key no-op).

## Execution Notes

- Program linkage: phase4 of the `cli` program. Parallel with phase5 and phase6
  once phase3 is done. Blocked on `backend-track-facts-llm-endpoint` for the
  FACTS half — the FLOWS INTO half could ship against the existing recommender
  independently, but keeping them together matches the sidebar's design.
- Read first:
  - `docs/arch/cli-juke-tux-designs.md` §Now Playing sidebar — the FACTS /
    FLOWS INTO mockups, including the fact text wrapping at 30 chars.
  - `backend/recommender/urls.py` + whatever serializer backs it (confirm the
    request/response shape at implementation time — mlcore phases are in flight).
  - The deliverable of `backend-track-facts-llm-endpoint` for the facts contract.
- Key files:
  - `cli/internal/api/{recommendations,facts}.go`
  - `cli/internal/daemon/handlers_recs.go`
  - `cli/internal/tui/panes/sidebar.go`
  - `docs/arch/cli-juke-tux-designs.md` (sidebar mockup)
- Commands:
  - `cd cli && go test -race ./...`
  - `./scripts/test_cli.sh`
- Risks:
  - Facts are slow (LLM round-trip). The fetch must be a `tea.Cmd`, never
    blocking `Update`. If the user skips tracks rapidly, in-flight fact fetches
    for now-stale tracks should be ignored when they arrive (tag requests with
    the track ID, drop responses that don't match the current one).
  - The recommender surface may change under mlcore Phase 2–4. If the contract
    drifts significantly, this task's `api/recommendations.go` follows.
  - 32 characters is narrow. Fact text needs aggressive wrapping and the
    viewport needs clear scroll indicators (`▲`/`▼`) or facts get truncated
    invisibly.

## Handoff

- Completed:
- Next:
- Blockers:
  - `cli-phase3-catalog-playback-tui` must be `done`.
  - `backend-track-facts-llm-endpoint` must be `done`.
