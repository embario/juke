# CLI Daemon IPC/Auth Foundation

Ecosystem goal: Start a durable power-user client architecture that can eventually support playback, discovery, messaging, and automation from the terminal.

Evaluation focus: Tests whether the model follows the intended Go-based CLI direction, creates a task spec before coding, and draws a clean seam between daemon protocol and future TUI work.

Review the repository handbook, CLI guidance, existing CLI prompt material, task board, and CLI architecture notes. Promote this idea into an `ITERATIVE` task for the first local CLI daemon slice: protocol shape, auth/session command flow, and a small testable IPC/status implementation in the intended CLI language. Keep playback panes, realtime websockets, messaging, and music generation out of scope for the first slice.

Follow-up playback-state work is a separate idea seed: `prompts/ab-eval-cli-daemon-playback-state.md`.
