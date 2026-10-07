---
id: juke-ios-app-port
title: Port the Juke macOS app (Radio, Library, New Station, Memories, Chat, Settings) to iOS
status: ready
priority: p1
owner: unassigned
area: clients
label: CLIENTS
complexity: 5
updated_at: 2026-10-07
---

## Goal

Ship an iOS app **Juke** (bundle ID `com.juke.app`, scheme `JukeApp`, `mobile/ios/jukeapp`)
that is a clone of the macOS Juke app (`macos/juke`, `com.juke.mac`), runnable on the
iOS 27.0 simulator (Xcode 27.0) and deployable to a physical iPhone. Today the iOS
target is only the old Vibe memories/chat app (~16 files) with no Radio, Library or
New Station. Parity should come from sharing code with macOS, not copying it.

Spec and design: `tasks/juke-app-implementation.md`,
`docs/design/juke-app/Round3.reference.html`. Backend `/api/v1/radio/` already exists
on the integration branch.

## Scope

- Move shared, platform-neutral code (models, radio API client, `RadioController`,
  design tokens) into a shared Swift package (`mobile/ios/Packages/JukeKit` or a new
  package) consumed by both `JukeMac` and `JukeApp`. Prefer moving over copying.
- iOS shell with Radio, Library (crate), New Station, Memories, Chat and Settings
  (including the backend URL setting), adapted for touch.
- Touch interactions for the sleeve, vinyl, FM dial and crate, delivered in later slices.
- Early investigation, reported before any playback code: how macOS plays (Spotify Web
  API / Connect queue through `SpotifyRadioPlayback`) and what iOS needs (active Spotify
  device versus the Spotify iOS SDK).
- Backend changes only if that investigation shows a need.

## Out Of Scope

- Merging or touching PR #177 (`integration/juke-app` -> `master`), or any change to `master`.
- `/srv/juke-dev`, `/srv/juke-prod`, and the existing dirty checkouts.
- Android, the other iOS apps (`juke`, `shotclock`, `tunetrivia`), and lyrics/ads.
- Committing signing secrets, tokens or `.env` files.

## Acceptance Criteria

- (a) `com.juke.app` builds and launches on the iOS 27.0 simulator via
  `scripts/build_and_run_ios.sh -p jukeapp`.
- (b) Radio, Library, New Station, Memories, Chat and Settings reach feature parity
  with `macos/juke`, adapted for touch.
- (c) Unit tests pass in GitHub CI. Local `xcodebuild test` has wedged before, so CI is
  the bar; locally use `scripts/test_mobile.sh -p jukeapp --ios-only -o 27.0`.
- (d) All PRs target `integration/juke-app` only, each code-reviewed with findings
  fixed, and are left open for the owner.
- macOS tests still pass after the shared-code move.

## Execution Notes

- Mode: `ASYNC`. Proceed autonomously; decide small tradeoffs and record them in the
  handoff notes. Escalate only true blockers: physical-iPhone signing/device setup,
  Spotify playback limits on iOS that need an owner decision, or anything needing a secret.
- Base: `origin/integration/juke-app` @ `66a8f5f`. Branch `juke-app/s8-ios-port`,
  worktree `/Users/embario/Documents/juke-agent-deck/ios-port`. Later slices branch
  `juke-app/<slice>` from the integration branch.
- Key files: `macos/juke/JukeMac/{Services/Radio,Services/API,Design,Models,Views}`,
  `mobile/ios/jukeapp/` (XcodeGen `project.yml`), `mobile/ios/Packages/JukeKit`.
- Commands: `scripts/build_and_run_ios.sh -p jukeapp`;
  `scripts/test_mobile.sh -p jukeapp --ios-only -o 27.0`.
- Backend: default URL `https://neptune.tail647b75.ts.net`; extra stack
  `/srv/juke-extra/juke-app` (port 8200). Any backend work uses
  `/home/mario/juke-agent-deck/backend` rebased onto `integration/juke-app`.
- Slice order: (1) playback investigation + shared package extraction, (2) iOS shell,
  (3) Radio/New Station touch, (4) Library crate, Memories, Chat, Settings parity.
- Risks: local xcodebuild wedging; Spotify iOS playback constraints; the shared-package
  move breaking macOS; device signing unconfirmed (`IOS_DEVELOPMENT_TEAM` unset; only a
  simulated iPhone 18 Pro is visible, no physical iPhone connected).

## Handoff

- Completed: spec written; worktree created at `66a8f5f`.
- Next: worker runs the playback investigation and reports before building playback.
- Blockers: none yet. Lead to add this task to `tasks/_index.md` (lead-only).
