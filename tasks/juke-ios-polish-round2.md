---
id: juke-ios-polish-round2
title: Juke iOS polish round 2 (owner feedback from second on-device test)
status: ready
priority: p2
owner: unassigned
area: clients
label: CLIENTS
complexity: 5
updated_at: 2026-10-08
---

## Goal

Resolve the 18 owner-reported items from the second on-device test of the iOS app (`com.juke.app`, iPhone 15 Pro), delivered as 16 PRs (A-P) into `integration/juke-app`. Sources: the approved proposal `ios-polish-round2` (agent-deck data directory) and the owner's device-testing round 2 notes (items 1-15 plus the clarifications and Codex severity ranking of 2026-10-08). The Mac app (`macos/juke`) and `docs/design/juke-app/Round3.reference.html` remain the visual reference.

## Scope

Execution mode: **ASYNC**. Follow `docs/agent-pr-pipeline-protocol.md`. Rank is Codex's ranking of the 18 items; sizes: S small, M medium, H heavy. Dependencies come before severity when ordering merges.

| PR | Rank | Sev | Size | Task | Depends on |
|---|---|---|---|---|---|
| A | 1 | P1 | H | Pause/resume and device recovery | none |
| B | 2 | P1 | S | Chat Done vs Send overlap | none |
| C | 3, 17 | P2 | M | Persistent player controls and island separation | none |
| D | 4 | P2 | H | Full artist catalog with pagination and filters | none |
| E | 5 | P2 | H | Reusable artist/album detail views | D |
| F | 6 | P2 | M | Recent-resource Library | E |
| G | 7 | P2 | S | Chronological next-memory playback | C |
| H | 8 | P2 | S | Delete memories | none |
| I | 9 | P2 | H | Shuffled card-deck Memories landing | H |
| J | 10, 18 | P2 | H | Memory detail enrichment and ringed Play button | I |
| K | 11 | P2 | M | Emoji hold/scrub slider | none |
| L | 12 | P3 | S | Dismissible connection-error overlay | A |
| M | 13 | P3 | S | Message-safety notice once per account | none |
| N | 14 | P3 | S | Chat replies default to 1-3 short sentences | none |
| O | 15 | P3 | S | New Station wizard top Back/Next | none |
| P | 16 | P3 | S | Vinyl slider spacing | none |

### PR groups

**A. Pause/resume and device recovery (P1, H).** A paused or transiently missing playback state must not show "open Spotify". Distinguish pause from an unavailable device. Starting points: `MiniPlayerPill` and `RadioController.refresh` (which maps every nil playback snapshot to `noActiveDevice`). Investigate and write down which Spotify permission/setup is needed for consistent in-app control (Premium, granted scopes `user-read-playback-state`, `user-read-currently-playing`, `user-modify-playback-state`, an available device).
- Acceptance: pausing keeps a paused state with a Resume control in Juke; "open Spotify" appears only for a genuinely unavailable device; transient nil snapshots do not flip state; unit tests cover pause, transient nil and no-device; a written findings section (PR body or this file's handoff) states precisely what is and is not verified, since agents cannot test playback on a real phone.

**B. Chat Done vs Send (P1, S).** The keyboard Done button overlaps Send.
- Acceptance: Done and Send have distinct, non-overlapping tap targets with the keyboard up, including small phones (e.g. iPhone 17e) and large text; screenshots with keyboard visible.

**C. Persistent player controls and island (P2, M; ranks 3 and 17).** Previous, play/pause and next are always visible on every screen and source, including memory browsing and detail. Today `MiniPlayerPill` shows controls only for `radio.isOnAir` with a radio track and otherwise renders `NowPlayingPill` with none; previous is absent though `PlaybackClient` supports it. Radio Previous replays the preceding station song. Stronger border and separation so the now-playing island floats above content.
- Acceptance: controls never disappear when the source changes; radio Previous replays the preceding station song; island border/shadow clearly separates it from content in light and dark; unit tests for the control-state logic.

**D. Full artist catalog (P2, H).** Browsing an artist fetches the full available catalog including provider pagination, not just cached albums. Release-type filters: albums, singles, EPs, compilations, live, appearances; albums and EPs first. Likely touches the backend.
- Acceptance: pagination reaches the end of a multi-page artist; filters work and default to albums/EPs first; backend changes are a separate PR or clearly separated commits with external services mocked and tests; UI handles loading, partial and error states.

**E. Reusable artist and album detail views (P2, H; needs D).** A downward swipe on an album reveals its tracklist within the same Library browsing context (not a separate page) with an animated transition; an upward return dismisses to the album pane. Artist details follow the same pattern. Both views are reusable and reachable from other workflows.
- Acceptance: gesture tracks the finger, is cancellable, and has an accessible non-gesture alternative; views open from at least Library plus one other entry point; screenshots of both states.

**F. Recent-resource Library (P2, M; needs E).** Library shows 10-20 recent unique resources (artists, albums, songs). "Browsed" means searched, detail-opened or played. When history is shorter, fill with recommended/similar resources.
- Acceptance: deduplicated, most-recent-first, capped 10-20; short history is padded with recommendations; unit tests for dedupe, ordering and fill.

**G. Chronological next-memory playback (P2, S; needs C).** In memory playback, Next plays the next memory chronologically.
- Acceptance: Next from a memory advances in chronological order, with defined behavior at the last memory; unit tests.

**H. Delete memories (P2, S).** Delete entries from the Memories page.
- Acceptance: delete with confirmation, calls the existing delete endpoint (or adds one in a separate backend PR), list updates; failure shows an error and keeps the item.

**I. Shuffled card-deck Memories landing (P2, H; needs H).** Replace the landing page (filename presentation and the artwork-less top Thought panel) with a beautiful shuffled deck of cards for existing memories; photos and music artwork are prominent.
- Acceptance: cards show photo or artwork, never filenames; shuffle is stable within a session; empty and single-memory states; deletion from H remains reachable; screenshots against the reference.

**J. Memory detail enrichment and ringed Play (P2, H; needs I; ranks 10 and 18).** Tags, description, photos and videos. Contacts tagging is deferred. Play button gets a visible ring and aligns to the right edge of its capsule. Likely touches the backend (memory fields).
- Acceptance: fields persist and round-trip; media renders; Play is ringed and right-aligned; a migration is never deployed to Neptune (see Risks); tests for new fields.

**K. Emoji slider (P2, M).** Replace the reaction strip under Radio/Now Playing controls: press and hold, scrub, enlarged preview of the highlighted emoji, release to choose. The chosen emoji moves to the leftmost slot and stays there until another selection changes recency order (ordered most to least recent).
- Acceptance: hold/scrub/release works; recency ordering unit-tested; a simple accessible alternative (VoiceOver and tap) is kept.

**L. Dismissible connection-error overlay (P3, S; needs A).** "Juke could not be reached" and similar errors become a transient overlay outside page layout (not the inline `IssueView` card) with an explicit X, retained until dismissed. The same dismissed error is not re-presented every poll.
- Acceptance: overlay does not affect layout; dismissal persists across polling cycles until the error changes or clears; unit tests for suppression.

**M. Message-safety notice once per account (P3, S).** The "Message is safe" dialog shows once per account, also across devices and relaunches; later sync failures do not repeat it. Likely needs a per-account flag on the backend.
- Acceptance: not shown again after relaunch or on a second device for the same account; backend part separated with tests.

**N. Short Chat replies (P3, S).** Default to 1-3 short sentences unless the user asks for detail. The limit is set in `backend/vibe/services.py` (OpenAI call, `max_tokens=180`).
- Acceptance: prompt and token settings updated; tests with the LLM call mocked.

**O. New Station wizard navigation (P3, S).** Remove the white footer rectangle (the `.bar` background footer). Back at top-left and Next at top-right as text controls, preserving progression and validation.
- Acceptance: no footer rectangle; validation still blocks Next; screenshots.

**P. Vinyl slider spacing (P3, S).** The front-to-back slider truncates the Songs / Artists / Albums selector.
- Acceptance: labels fully readable with no overlap or clipping on small phones and large text sizes; screenshots.

## Out Of Scope

- Spotify App Remote integration (needs the owner's Spotify developer registration and callback URI). If A shows it is required, send a `NEED:`; do not start it.
- Contacts tagging for memories (deferred).
- PR #177, master, `/srv/juke-dev`, `/srv/juke-prod`, `.github/workflows`.
- Testing playback on a real phone; entering credentials.
- Installing builds on the physical device (separate device-testing work).

## Acceptance Criteria

- All 16 PRs merged through the PR pipeline, CI green on `integration/juke-app`.
- Each PR carries exactly one severity label (P1/P2/P3), one author label, and `needs-review` on open; auto-merge stays on.
- UI PRs include side-by-side screenshots (Mac app or `Round3.reference.html` plus the iOS simulator, iPhone 18 Pro, iOS 27.0) and a "not verified on device" note. Logic has unit tests. Build with `scripts/build_and_run_ios.sh -p jukeapp`.
- Backend changes live in their own PR (or separated commits) with tests and mocked external services.

## Execution Notes

- Mode: ASYNC.
- Suggested split: implementer-1 B, H, L, M, N, O, P; implementer-2 A (raised profile), then I, J; implementer-3 C, D, E, F, G, K. Max 2 open P0/P1 PRs; sort queues P1 then P2 then P3.
- Key files: `MiniPlayerPill`, `NowPlayingPill`, `RadioController`, `PlaybackClient`, `IssueView`/`RadioScreen` (iOS app); `backend/vibe/services.py`; catalog and memory backend apps.
- Never use `--no-verify`.
- Risks:
  - A cannot be fully verified without a real device, Spotify Premium and an active device; state exactly what was verified.
  - Spotify Web API playback needs Premium, control scopes and an available device; App Remote still depends on the Spotify app lifecycle and is not an Apple entitlement.
  - Backend-touching PRs (D, J, M, N): a migration must not be deployed to the Neptune extra stack (shared dev database); send `NEED:` naming it. Radio-only migrations (`migrate radio`) are the exception. After a non-migration backend PR merges, deploy only to `/srv/juke-extra/juke-app` (fast-forward, restart that backend container, check the endpoint).
  - D to E to F and I to J are chains; ordering by dependency can delay P2 items behind each other.
  - Gesture-heavy UI (E, I, K) needs accessible alternatives and simulator-only verification.
  - Budget: roughly 2x round 1 across 16 PRs; pause new Claude tasks at 80% of the 5-hour window and all launches at 85% weekly.

## Handoff

- Completed: spec written (this file).
- Next: start A and B (P1), then queues per Execution Notes.
- Blockers: none.

### PR B — Chat keyboard controls (implementer-1)

- PR: #212 (`juke-app/chat-keyboard-done`), P1, author:codex, needs-review. Implements group B only; `Refs #210` leaves the overall round-2 issue open.
- Done has a dedicated leading row and a 44-point tap target in the bottom composer inset. Send stays beside the draft; its icon size is fixed so accessibility text does not push it outside its circle. Keyboard dismissal preserves the draft.
- The view and model share the whitespace/in-flight send guard. Three composer unit tests passed.
- Final UI tests passed: iPhone 18 Pro normal text; iPhone 17e normal and accessibility XXXL text. Checks cover 44-point targets, screen bounds, non-overlap, keyboard clearance, draft preservation and refocusing.
- Evidence: `docs/design/juke-app/ios-polish-r2/`, including multiline-draft keyboard screenshots and side-by-side Round3 comparisons. Round3 has no Chat screen; its static Radio view is the styling reference. Not verified on device; no live chat requests.
- Final builds used `scripts/build_and_run_ios.sh -p jukeapp` with explicit simulator targets. Initial host-memory-pressure stalls resolved by reducing simulator concurrency; no CoreSimulatorService restart. Both B simulators were shut down after verification; implementer-2's simulator was untouched.
- Next: finish CI/review/merge through the pipeline; other round-2 groups remain outstanding.
