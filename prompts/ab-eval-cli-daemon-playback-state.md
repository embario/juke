# CLI Daemon Playback State

Ecosystem goal: Let terminal users see what is playing across Juke clients without extra backend round-trips.

Evaluation focus: Tests whether the model builds on an existing daemon/IPC seam, keeps polling and caching testable, and limits TUI changes to the current-track display.

Review the repository handbook, CLI guidance, existing CLI prompt material, task board, and CLI architecture notes. This follow-up builds on the completed CLI daemon IPC/auth foundation (`prompts/ab-eval-cli-daemon-foundation.md`). Promote it into its own `ITERATIVE` task, then ingest the tasking tickets for the CLI project and continue iterative development: at a high level, wire the daemon's transport layer so it polls the backend for playback state every 10 seconds, caches the result, and broadcasts `playback.state.changed` over IPC whenever the state changes. Add a `playback.state` IPC handler so the TUI can ask "what's playing right now?" and receive a cached response instantly without a backend round-trip. Update the TUI stub to display the current track below the session line.

Success Criteria & Goal:
log in from the TUI, and within 10 seconds the screen shows the
currently-playing track and artist (or "Not playing" if nothing is active).
Pause from another Juke client (web/mobile) and watch the TUI reflect it on
the next poll cycle.
