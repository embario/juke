---
id: cli-phase6-music-generation
title: Juke CLI Phase 6 - Music generation prompt pane
status: blocked
priority: p3
owner: unassigned
area: cli
label: CLI
labels:
  - juke-task
  - cli
  - go
  - tui
  - experimental
complexity: 3
updated_at: 2026-03-06
---

## Goal

Add the Generate nav entry: a multi-line prompt box, a job list showing
in-progress and completed generations, and play/save/delete actions on
completed ones. Prompt → `Ctrl+Enter` submits → spinner → audio URL → play.
Thin client over `backend-music-generation-service`.

## Scope

- `cli/internal/api/generation.go` — client for the gen service. Submit prompt
  (returns job ID), poll/stream job status, fetch result (audio URL).
- `cli/internal/daemon/handlers_gen.go` — IPC handlers `gen.submit`,
  `gen.jobs`, `gen.cancel`, `gen.play`, `gen.delete`. Daemon polls job status
  for active jobs and pushes `gen.job.updated` events to the TUI.
- `cli/internal/tui/panes/generate.go` — `bubbles/textarea` for the prompt
  (multi-line, `Ctrl+Enter` submits, Enter inserts newline). Job list below
  with Braille-spinner for in-progress, `▸ play  ⌫ delete  ⎘ save` actions for
  completed. `bubbles/spinner` for the per-job indicator.
- Play action hands the audio URL to the playback path. Whether this means a
  separate local playback mechanism or the Spotify-backed `playback.play`
  depends on what the gen service produces — decide at implementation time
  based on the backend deliverable.

## Out Of Scope

- Any generation model work. Pure client.
- Saving generated tracks into the catalog. "Save" here means keeping the job
  result in the list vs. auto-pruning after N days — a daemon-side list, not a
  backend write.
- Prompt templates / presets.
- Generation parameters beyond the prompt text (duration, genre hints, etc.).
  If the backend accepts them, add fields; if not, don't.

## Acceptance Criteria

- Generate nav entry opens the pane. Textarea is focused by default. Typing
  works, Enter newlines, `Ctrl+Enter` submits.
- Submitted job appears in the list with a spinner. Status updates arrive via
  IPC push (daemon is polling the backend on the TUI's behalf).
- Completed job shows the action row. `Enter` plays. `d` deletes. The spinner
  stops.
- Cancelled/failed jobs show a terminal state and an error summary line.
- Leaving the Generate pane and coming back preserves the job list (daemon
  owns it, TUI re-fetches on mount).

## Execution Notes

- Program linkage: phase6 of the `cli` program. Parallel with phase4 and phase5
  once phase3 is done. Blocked on `backend-music-generation-service`, which is
  the most experimental of the three backend deps and may never ship —
  `priority: p3` reflects that.
- Read first:
  - `docs/arch/cli-juke-tux-designs.md` §Generate view — prompt box layout,
    job list, Braille spinner glyphs (`⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏`).
  - The deliverable of `backend-music-generation-service` for the job lifecycle
    (states, polling vs. push, result format).
- Key files:
  - `cli/internal/api/generation.go`
  - `cli/internal/daemon/handlers_gen.go`
  - `cli/internal/tui/panes/generate.go`
- Commands:
  - `cd cli && go test -race ./...`
  - `./scripts/test_cli.sh`
- Risks:
  - Generation is slow (minutes). The daemon's job-status poller needs to run
    on a separate ticker from the playback poller, with a much longer interval,
    and back off when no jobs are active. Don't hammer the backend for an empty
    job list.
  - `bubbles/textarea` and multi-line input in terminals is finicky around
    Enter vs. Ctrl+Enter detection — some terminals send the same escape
    sequence. May need a submit-button fallback (tab to a `[Submit]` label,
    Enter there) if Ctrl+Enter proves unreliable.
  - Playing an arbitrary audio URL is outside the Spotify playback model. If
    the gen service returns a URL that Spotify can't play, this phase needs a
    local-playback fallback (`mpv`/`afplay`/platform equivalent shelled out
    from the daemon), which is a meaningfully larger scope. Clarify with the
    backend task before starting.

## Handoff

- Completed:
- Next:
- Blockers:
  - `cli-phase3-catalog-playback-tui` must be `done`.
  - `backend-music-generation-service` must be `done`.
