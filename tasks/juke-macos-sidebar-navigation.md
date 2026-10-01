---
id: juke-macos-sidebar-navigation
title: Move Juke Mac section navigation into a sidebar
status: review
priority: p1
owner: codex
area: clients
label: CLIENTS
complexity: 2
updated_at: 2026-10-01
---

## Goal

Use a Mac sidebar for Radio, Library, Memories and Chat while preserving the
current integration branch's section routing, playback and theme behavior.

## Scope

- Sidebar navigation with accessible selected states and existing identifiers.
- Wordmark, appearance control and Settings access in the sidebar.
- Keep the content card and mini player inside the detail region.
- Spotify-only Radio confirmed for v1; iOS bottom navigation is future work.

## Out Of Scope

- Radio/Library/Memory controllers under active development by other agents.
- iOS changes, backend changes, deployment, App ID registration, or installation
  over the existing user application.

## Acceptance Criteria

- Mac section controls are in the sidebar rather than the top header.
- Command-1 through Command-4, section transitions, appearance and privacy lock work as before.
- Radio card fits the 1000×680 minimum window; mini player is centered in the detail.
- Mac build and default applicable unit suite pass; signed entitlement checks are
  distinguished from unsigned checks if the new App ID remains unprovisioned.

## Execution Notes

- Mode: ITERATIVE. User explicitly requested implementation after code inspection.
- Worktree: `/Users/embario/.codex/worktrees/juke-radio-listening-room/juke`.
- Base: merged latest `origin/integration/juke-app` (e60b2b4) into isolated branch.
- Files: `Views/Shell/JukeHeader.swift`, `JukeRootView.swift`, `App/JukeSection.swift`.
- Build outputs/logs/executable stay under this worktree's ignored `build/`.
- Risks: interference with active parallel slices; keep changes confined to shell.

## Handoff

- Specification written before implementation; existing designs preserved in a commit.
- No files in other worktrees changed. Prior design-only commit skipped the
  unrelated web hook because no web dependency install exists in this worktree;
  no web/backend code was modified by that commit.
- Implemented: sidebar destinations with section icons, selected state, appearance
  controls and native SettingsLink. Mini now-playing overlay belongs to the detail
  pane, preserving section routing, existing nav identifiers and Command-1…4.
- Verified: `CI=1 DERIVED_DATA_PATH="$PWD/build/DerivedData" bash scripts/test_macos.sh`
  builds successfully; 92 tests pass, zero failures. Existing Keychain tests are
  excluded by the script's unsigned CI mode. `git diff --check` passes.
- Output: `build/sidebar-tests.log`, executable under
  `build/DerivedData/Build/Products/Debug/Juke.app`. No installed app replaced.
- Signed entitlement validation and live UI/minimum-window visual verification
  remain pending. New App ID/profile provisioning is separate from unsigned build.
- Next: review and incorporate the shell change into integration alongside Claude's
  remaining Radio/Library/Memory slices. iOS navigation remains deferred.
