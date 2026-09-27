# CLI Daemon IPC/Auth Foundation

Ecosystem goal: Start a durable power-user client architecture that can eventually support playback, discovery, messaging, and automation from the terminal.

Evaluation focus: Tests whether the model follows the intended Go-based CLI direction, creates a task spec before coding, and draws a clean seam between daemon protocol and future TUI work.

Review the repository handbook, CLI guidance, existing CLI prompt material, task board, and CLI architecture notes. Promote this idea into an `ITERATIVE` task for the first local CLI daemon slice: protocol shape, auth/session command flow, and a small testable IPC/status implementation in the intended CLI language. Keep playback panes, realtime websockets, messaging, and music generation out of scope for the first slice.


Review the repository handbook, CLI guidance, existing CLI prompt material, task board, and CLI architecture notes. For this next phase, ingest the tasking tickets for the CLI project and continue iterative development: at a high level, wire the daemon's transport layer so it polls the backend for playback state every 10 seconds, caches the result, and broadcasts `playback.state.changed` over IPC whenever the state changes. Add a `playback.state` IPC handler so the TUI can ask "what's playing right now?" and receive a cached response instantly without a backend round-trip. Update the TUI stub to display the current track below the session line.

Success Criteria & Goal:
log in from the TUI, and within 10 seconds the screen shows the
currently-playing track and artist (or "Not playing" if nothing is active).
Pause from another Juke client (web/mobile) and watch the TUI reflect it on
the next poll cycle.
