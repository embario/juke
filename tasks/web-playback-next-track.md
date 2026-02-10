---
id: web-playback-next-track
title: Fix playback to play the next track in the album
status: ready
priority: p1
owner: unassigned
area: web
label: WEB
complexity: 2
updated_at: 2026-02-10
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
- Next:
- Blockers:
