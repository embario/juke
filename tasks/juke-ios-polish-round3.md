---
id: juke-ios-polish-round3
title: Juke iOS polish round 3 (owner feedback from the third on-device test)
status: ready
priority: p2
owner: unassigned
area: clients
label: CLIENTS
complexity: 4
updated_at: 2026-10-10
---

## Goal

Resolve the 10 owner-reported items from the third on-device test of the iOS app (`com.juke.app`, iPhone 15 Pro, build from `integration/juke-app` 2c36164), delivered as 8 PRs (Q-X) into `integration/juke-app`. Source: Codex's notes "Next test-drive notes (2026-10-10)" in `/Users/embario/.codex/worktrees/ios-device-testing/juke/tasks/juke-ios-device-testing-round2.md` (read-only; do not copy anything else from that worktree) plus the approved proposal `ios-polish-round3` (agent-deck data directory). The Mac app (`macos/juke`) and `docs/design/juke-app/Round3.reference.html` remain the visual reference.

## Scope

Execution mode: **ASYNC**. Follow `docs/agent-pr-pipeline-protocol.md`. The owner wants as little involvement as possible: decide small product questions yourselves, state the decision in the PR body, and send a `NEED:` only for a real blocker. Sizes: S small, M medium, L large. Dependencies come before severity when ordering merges.

| PR | Rank | Sev | Size | Task | Notes | Depends on |
|---|---|---|---|---|---|---|
| Q | 1 | P1 | M | Every failed Next gives feedback | 1 | none |
| R | 2 | P2 | M | Library swipe-down opens details; song opens its album; tracklist always visible | 4, 5 | none |
| S | 3 | P2 | M | Station exhaustion and relevance investigation | 9, 1 | none |
| T | 4 | P2 | L | Compact emoji chooser (rework of the slider from #226) | 3 | none |
| U | 5 | P2 | L | Larger vinyl; tuner moves to a bottom drawer | 10 | none |
| V | 6 | P2 | L | Vinyl into the sleeve pauses playback and opens actions | 8 | U |
| W | 7 | P3 | S | Memory card media first; full image viewer | 6, 7 | none |
| X | 8 | P3 | S | Centered Previous / Play-Pause / Next | 2 | U |

U, X and V all change the Radio / Now Playing screen: merge them in the order U, X, V.

### PR groups

**Q. Feedback on every failed Next (P1, M).** After "nothing left in this station", pressing Next again gives no feedback. Every unsuccessful advance must say what happened, and a temporary recommendation failure must read differently from a genuinely exhausted station. The client may need a reason code from the radio endpoint; if so the backend part is a separate PR or clearly separated commits.
- Acceptance: each failed Next shows an outcome (retry vs exhausted vs offline) every time, not just the first; the message does not re-stack or flicker across polls; unit tests for the state mapping; screenshots of each state.

**R. Library gesture and song routing (P2, M).** A downward swipe opens album and artist details from Library, not only a tap (the round-2 views reveal by swipe only inside the detail view). Opening a song routes to its album detail with that song highlighted in the tracklist. The album tracklist is never collapsible; this supersedes the earlier collapsible reading (leaving the whole detail view stays separate). Include the round-2 reviewer's open note: an artist's album rows must open the album in Library.
- Acceptance: swipe and tap both open details from Library rows; a song opens its album with the song highlighted and scrolled into view; the tracklist has no collapse control; accessible non-gesture alternative kept; unit/UI tests and screenshots.

**S. Station exhaustion and relevance investigation (P2, M, ITERATIVE).** Find out why a continuing station runs out ("nothing left") and why songs feel disconnected from the chosen tags, feelings and music seeds. Read the backend (`backend/vibe/` radio selection, MLCore co-occurrence, the 4-second selection budget, recent/blocked exclusions) and Codex's findings in the source notes. Complete identity resolution is not assumed to be required.
- Deliverable: a findings document under `docs/` (the PR body links it) separating verified from unverified, naming the likely causes ranked, and proposing concrete fixes with sizes. Do not change radio behavior in this PR; fixes become follow-up tasks the owner approves. Verify the deployed backend revision on the Neptune extra stack before drawing conclusions about it, read-only.
- Acceptance: findings reproducible from named code paths and, where possible, a mocked test showing the exhaustion case; clear statement of what could not be checked.

**T. Compact emoji chooser (P2, L).** Replaces the slider from #226. At rest show only previously selected emojis plus one press-and-hold chooser button. Holding opens the full range, sliding previews the emoji, release selects with minimal effort. Order the full range emotions first, then objects, places and materials. A chosen emoji still moves to the leftmost slot and stays there until another selection changes recency. The fleet picks the emoji catalogue and groups itself and states it in the PR; the owner will not weigh in.
- Acceptance: hold / slide / release works including a plain tap; "In your words" reactions stay visible; recency ordering and category ordering unit-tested; accessible alternative kept; the Mac strip is not changed unless unavoidable (say so in the PR).

**U. Larger vinyl and tuner drawer (P2, L).** Substantially enlarge the Now Playing vinyl and move the radio tuner into an expandable and collapsible bottom drawer to free space. Merge first in its lane.
- Acceptance: vinyl is clearly larger on iPhone 18 Pro and iPhone 17e; the drawer opens and closes by drag and by tap, remembers nothing it must not, and does not hide the player island; the existing tuner functions still work from the drawer; large-text layout checked; screenshots.

**V. Vinyl into the sleeve (P2, L; needs U).** Sliding the record into its sleeve pauses playback and presents actions: start a new station, browse the album, save to favorites, save for later. Ship pause plus "start a new station" and "browse the album" now. "Save to favorites" and "save for later" need a data model that may not exist; implement them only if a suitable existing store is found, otherwise show them disabled with a short note and send one `NEED:`-free follow-up note in the PR body proposing the model. Do not invent a backend model in this PR.
- Acceptance: the gesture pauses playback and shows the sheet; each shipped action works; dismissing the sheet resumes or stays paused as documented in the PR; unit tests for the state logic; screenshots; "not verified on device".

**W. Memory media first, full image viewer (P3, S).** Use a memory's photos and videos as the main card media; keep music artwork elsewhere and use it as the default only when the memory has no media. Tapping any image opens a full image view.
- Acceptance: card media order verified with and without media; full-screen viewer opens from the card and the detail view and can be dismissed; zoom is optional; screenshots.

**X. Centered playback controls (P3, S; needs U).** Previous / Play-Pause / Next stay centered in the viewport regardless of surrounding widgets.
- Acceptance: controls are centered on iPhone 18 Pro and 17e, in Radio and memory playback, with widgets of varying width around them; screenshots.

## Out Of Scope

- Changing radio recommendation behavior (S only investigates).
- Favorites / save-for-later backend models (V ships without them if no store exists).
- Contacts tagging for memories; Spotify App Remote.
- PR #177, master, `/srv/juke-dev`, `/srv/juke-prod`, `.github/workflows`.
- Testing playback on a real phone; entering credentials; installing builds on the physical device (separate device-testing work).

## Acceptance Criteria

- All 8 PRs merged through the PR pipeline, CI green on `integration/juke-app`.
- Each PR carries exactly one severity label (P1/P2/P3), one author label, and `needs-review` on open; auto-merge stays on. Reference the round issue with `Refs #<issue>` (not a closing keyword) until the last PR.
- UI PRs include side-by-side screenshots (Mac app or `Round3.reference.html` plus the iOS simulator, iPhone 18 Pro, iOS 27.0) and a "not verified on device" note. Logic has unit tests. Build with `scripts/build_and_run_ios.sh -p jukeapp`.
- Backend changes live in their own PR (or separated commits) with tests and mocked external services.

## Execution Notes

- Mode: ASYNC. Decide small questions yourself; state the decision in the PR body.
- Suggested split: implementer-1 (Luna): T, W, X; implementer-2 (Claude, raised to Opus 5.5 for Q): Q, then S; implementer-3 (Claude): R, U, then V. Max 2 open P0/P1 PRs; sort queues P1 then P2 then P3.
- Key files: `RadioController`, `RadioScreen`, `MiniPlayerPill`, library and memory views in the iOS app; the detail views and reaction strip from round 2; `backend/vibe/` for radio selection.
- Never use `--no-verify`. Keep simulator concurrency low (earlier rounds hit host memory pressure).
- Risks:
  - U, X, V share one screen; merge order U, X, V avoids conflicts.
  - T reworks recently merged code (#226) and can regress taps; keep the tap test.
  - S may find the cause is backend-side and large; it ends in a proposal, not a fix.
  - Backend-touching PRs (Q possibly): a migration must not be deployed to the Neptune extra stack; send `NEED:` naming it. After a non-migration backend PR merges, deploy only to `/srv/juke-extra/juke-app` (fast-forward, restart that backend container, check the endpoint).
  - Budget: smaller than round 2 (8 PRs); pause new Claude tasks at 80% of the 5-hour window and all launches at 85% weekly.

## Handoff

- Completed: spec written (this file).
- Next: start Q (P1), then queues per Execution Notes.
- Blockers: none.
