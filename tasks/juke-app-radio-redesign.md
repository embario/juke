---
id: juke-app-radio-redesign
title: Redesign Juke Vibe as the Juke App with Radio, Memories and Browse
status: done
priority: p1
owner: claude
area: clients
label: CLIENTS
complexity: 5
updated_at: 2026-10-01
---

## Goal

Converge on one design for the renamed **Juke App** (formerly Juke Vibe), centered
on a new Radio feature, then implement it. Turning radio on must be frictionless:
one tap the first time, auto-resume afterwards, and switching stations must never
interrupt the song that is playing.

## Scope

Design phase (current):
- Single-card interface: one spinning vinyl with the current artwork as its label,
  simple controls, low visual density, not a Spotify look-alike.
- Radio: a personal station ("My Station") that learns from plays, skips, loves
  and saves, plus user-created stations seeded by a song, an artist or a mood.
- Station switching queues the new station after the current song ("Up next"),
  with an explicit "Switch now" and "Undo".
- Memories and catalog Browse redesigned into the same single-card language;
  Browse results can start a station.
- Appearance control: Light / Dark / Match system, defaulting to Match system.
- An optional sponsor "station break" slot, explored as a design only.
- Storyboards for three directions: A Turntable, B Dial, C Stack.
  Canvas: https://claude.ai/artifact/9vZzRaNkXzpMxvN7bETvfZ

Implementation phase (after a direction is chosen):
- macOS app rename (display name, bundle, README) and the new UI.
- Backend station model and next-track endpoint (seeded by song/artist/mood plus
  the personal taste profile and memory signals), and a queue/continuous-play
  path through the existing Spotify playback provider.

## Out Of Scope

- Hosted/DJ commentary.
- Shared listening.
- Shipping paid advertising (needs policy/licensing review first; see Risks).
- Apple Music radio playback beyond what macOS automation already allows.

## Acceptance Criteria

- The user picks one direction (or a merge) from the canvas.
- First launch reaches playing music with one tap; later launches resume without a tap.
- Changing stations never stops or restarts the current song unless "Switch now" is chosen.
- Light, Dark and Match system all render with WCAG AA text contrast; the default is Match system.
- Memories and Browse work inside the single-card layout, and Browse can start a station.

## Execution Notes

- Mode: `ITERATIVE`. The user is refining the design while work proceeds; keep each
  slice narrow and update Handoff after each step.
- Worktree: `../juke-radio-design`, branch `design/juke-radio-redesign` (another
  agent works in the main checkout in parallel).
- Key files (implementation): `macos/jukevibe/JukeVibeMac/Views/*`,
  `Services/MusicDetectionController.swift`, `Services/PlaybackClient.swift`,
  `backend/catalog/services/playback.py`, `backend/recommender/*`,
  `backend/vibe/memory_services.py` (`memory_recommendation_context`).
- Existing building blocks: Spotify playback control, MLCore co-occurrence and
  metadata rankers (`/api/v1/recommendations/mlcore/`, no client yet), memory
  recommendation context, Apple Music local control on macOS.
- Risks:
  - Continuous play on Spotify needs a queue/"next track" loop; Spotify's Web API
    has no native radio, so Juke must supply each next track before the current one ends.
  - Ads: inserting paid ads around Spotify or Apple Music streams is likely restricted
    by their developer terms. Verify before building; a house/sponsor card between
    songs (no audio interruption) is the lower-risk option.
  - The Juke Vibe apps hardcode the Tailscale backend URL; fix during the rename.

## Handoff

- Completed: storyboards for three directions (A Turntable, B Dial, C Stack), each
  with tune-in, on-air, change-station, new-station, memories and browse frames, plus
  an A-only station-break frame and a live prototype with direction/screen/theme tweaks.
- Round 1 feedback (2026-10-01): pursue A Turntable with B's dial; the dial tunes by
  mouse drag, and a hard flick spins to the end to create a station; gentle
  transitions on every navigation; replace form-style station creation with
  artwork-first crate digging; compact multi-select emoji reactions (custom emoji
  allowed) on every song that feed recommendations and station picks.
- Round 2 on canvas page "Round 2": D Crate (emoji strip + horizontal crate),
  E Bin (React pill + vertical bin), F Vibe (emojis orbit the record + feeling-first
  creation). All share drag/flick dial, WAAPI fade/slide transitions, emoji → station
  suggestions, and Browse as the same crate.
- Round 2 feedback: card color follows artwork with animated transitions; hold a dial
  station to move it to a new frequency (frequency = station identity); dial shows
  three seed thumbnails per station; spin the record to seek, slide it into the sleeve
  to stop; sleeve click shows options; + click = emoji picker, + hold = words saved as
  reactions; drop the minus button and design include/exclude; selections listed as
  text; records and feelings are separate optional steps, either first; front-to-back
  flip is a user setting; no orbiting emoji.
- Round 3 on canvas page "Round 3 · Converged": one design with all of the above.
  Keep-out design: hold skip → skip once / not on this station / less of artist /
  never play artist; station sheet (click station name) → Built from, Feels like,
  Keep out (with restore), and a Keeps-learning switch.
- Round 3 approved with two tweaks (play cue on the dial instead of a status pane;
  crate panel narrows for front-to-back). Implementation continues in
  `tasks/juke-app-implementation.md`.
- Superseded next step: user reviews Round 3; then write the implementation slices (rename, Radio UI,
  station + frequency model, reaction/exclusion signals into recommendations,
  continuous playback, lyrics provider).
- Blockers: direction choice; ads policy check.
