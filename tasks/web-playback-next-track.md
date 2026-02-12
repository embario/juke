---
id: web-playback-next-track
title: Fix playback to play the next track in the album
status: review
priority: p1
owner: unassigned
area: web
label: WEB
complexity: 2
updated_at: 2026-02-11
---

## Goal

Fix web playback so track progression advances to the next album track correctly.

## Scope

- Reproduce the current playback progression behavior.
- Identify where the next-track decision is computed.
- Implement and validate correct next-track progression logic.

## Out Of Scope

- Cross-client playback parity unless directly required for this web bug.
- New playback UX redesign.

## Acceptance Criteria

- When a track ends, playback advances to the intended next track in the album sequence.
- Regression tests cover progression behavior for normal and edge cases.
- Manual verification confirms behavior on the web client.

## Execution Notes

- Source label: `WEB`
- Source task line: `Fix playback to play the next track in the album`
- Likely touchpoints: web playback components/services and related tests.
- Risks: backend playback state expectations may differ from web assumptions.

## Handoff

- Completed:
- Added context-aware track playback for album progression by sending `context_uri` + `offset_uri` on web track play.
- Extended backend playback start endpoint/service to accept and forward Spotify playback offsets.
- Added backend API tests for context-offset playback validation and offset error cases.
- Added frontend unit coverage for playback request construction with and without context.
- Next:
- Run backend and web playback tests in CI/local containers and do quick manual web verification of album track progression.
- Blockers:
