---
id: cli-phase5-direct-messaging
title: Juke CLI Phase 5 - Direct messaging pane
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
complexity: 4
updated_at: 2026-03-06
---

## Goal

Add the Messages nav entry: conversation list on the left, thread on the right,
input at the bottom. Shared tracks render as inline playable cards — select one,
hit Enter, it plays. Real-time message delivery over the WS transport (the
`MessageConsumer` from `backend-direct-messaging-foundation` sits on the
cli-phase2 `realtime/` rails).

## Scope

- `cli/internal/api/messaging.go` — REST client for the new `messaging/` Django
  app: list conversations, list messages in a conversation, send message,
  attach track to message. Shapes defined by
  `backend-direct-messaging-foundation`.
- `cli/internal/transport/ws.go` — extend the WS client to also subscribe to
  `ws/v1/messages/` (or whatever path the DM backend picks). Multiplex: one
  socket per endpoint is fine, reconnect loops are independent.
- `cli/internal/daemon/handlers_messaging.go` — IPC handlers
  `messages.conversations`, `messages.thread`, `messages.send`. Push event
  `messages.received` when the WS delivers a new message.
- `cli/internal/tui/panes/messages.go` — two-column layout inside the content
  area. Conversation list (bubbles/list) + thread viewport (bubbles/viewport).
  Message input (bubbles/textinput) at the bottom, hidden until `i` (insert
  mode). `Esc` leaves insert mode. Enter sends.
- Track-card rendering: messages with an attached track render a boxed
  mini-card (track name, artist, `▸ play`). Arrow keys in the thread viewport
  step between selectable cards; Enter on a selected card calls `playback.play`.
- `Ctrl+T` in insert mode opens a mini search overlay (reusing phase3's search
  model) to pick a track to attach.
- Unread indicator in the nav rail (`●` next to Messages) driven by
  `messages.received` pushes arriving while a different pane is focused.

## Out Of Scope

- Group conversations. 1:1 only, matching whatever the DM backend ships first.
- Message edit/delete. Send-only.
- Read receipts / typing indicators. Deferred.
- Image/audio attachments. Track-reference attachments only.

## Acceptance Criteria

- Messages nav entry opens the pane. Conversation list populates from the
  backend. Selecting a conversation loads its thread.
- `i` enters insert mode, typing works, Enter sends, the sent message appears
  in the thread immediately (optimistic) and is confirmed by the next
  `messages.thread` response.
- A message sent from the web app (once web DM exists) arrives over WS and
  appears in the thread without a poll cycle, with `●` shown on the nav rail
  if Messages isn't focused.
- A message with an attached track renders the mini-card. Enter on it plays the
  track. The playback bar updates.
- `Ctrl+T` → search → select track → the composed message shows an attachment
  preview → Enter sends both.
- Thread viewport scrolls with `j`/`k` (when not in insert mode) and auto-scrolls
  to bottom on new message.

## Execution Notes

- Program linkage: phase5 of the `cli` program. Parallel with phase4 and phase6
  once phase3 is done. Blocked on `backend-direct-messaging-foundation`.
- This is the most input-modal pane in the TUI. `i`-to-insert / `Esc`-to-normal
  is the vim pattern — the root model's focus router needs to know that in
  insert mode, **all** keys go to the textinput except `Esc` and `Ctrl+T`.
  Phase3's global-key interception (`space`, `n`, `p`, etc.) must be suppressed
  in insert mode or you'll pause playback every time you type a space in a DM.
- Read first:
  - `docs/arch/cli-juke-tux-designs.md` §Messages view — the conversation +
    thread + input mockup, the track-card box-drawing, the `Ctrl+T` attach flow.
  - The deliverable of `backend-direct-messaging-foundation` for endpoints,
    WS event shapes, and the attachment model.
- Key files:
  - `cli/internal/api/messaging.go`
  - `cli/internal/daemon/handlers_messaging.go`
  - `cli/internal/transport/ws.go` (extend)
  - `cli/internal/tui/panes/messages.go`
  - `cli/internal/tui/app.go` (insert-mode suppression of global keys)
- Commands:
  - `cd cli && go test -race ./...`
  - `./scripts/test_cli.sh`
- Risks:
  - **Insert-mode global-key suppression is the subtle one.** Write a test for
    it: send a `tea.KeyMsg{Type: tea.KeySpace}` to the root model while
    messages pane is focused and in insert mode, assert no `playback.pause`
    command was emitted.
  - The attach-track mini-search overlay reuses phase3's search model, but
    phase3's model returns control to the library pane on Enter. Need a
    callback/return-address mechanism so search can be invoked from two
    different call sites.
  - If the DM backend only ships REST (no `MessageConsumer`), this phase falls
    back to polling the thread endpoint. That's acceptable for v1 — check the
    backend task's deliverable at implementation time.

## Handoff

- Completed:
- Next:
- Blockers:
  - `cli-phase3-catalog-playback-tui` must be `done`.
  - `backend-direct-messaging-foundation` must be `done`.
