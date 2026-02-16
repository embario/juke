---
id: shotclock-android-data-layer-recovery
title: Restore ShotClock Android data layer and compile baseline
status: ready
priority: p1
owner: unassigned
area: android
label: ANDROID
complexity: 3
updated_at: 2026-02-16
---

## Goal

Recover the missing ShotClock Android data layer so the app compiles, runs, and can be used as a parity target for future feature work.

## Scope

- Recreate or restore missing `data` package modules referenced by current UI and DI layers.
- Re-establish repository interfaces and concrete implementations used by auth, catalog, profile, and power-hour flows.
- Reconnect DTO mapping from network payloads into app domain models.
- Verify `ServiceLocator` wiring and app startup behavior.

## Out Of Scope

- New ShotClock features beyond restoring the existing intended flow.
- TuneTrivia Android implementation work.
- Major visual redesign.

## Acceptance Criteria

- `mobile/android/shotclock` compiles with `./gradlew :app:compileDebugKotlin`.
- `scripts/build_and_run_android.sh -p shotclock` launches successfully.
- Core user flows are manually verified: login, session list, session creation, and playback entry.
- Unit tests exist for restored repositories or mappers where missing code is recreated.

## Execution Notes

- Idea rank: `#4`
- Portfolio classification: `essential`
- Key files:
- `/Users/embario/Documents/juke/mobile/android/shotclock/app/src/main/java/fm/shotclock/mobile/core/di/ServiceLocator.kt`
- `/Users/embario/Documents/juke/mobile/android/shotclock/app/src/main/java/fm/shotclock/mobile/ui/**`
- `/Users/embario/Documents/juke/mobile/android/shotclock/app/src/main/java/fm/shotclock/mobile/data/**` (restore/create)
- Commands:
- `cd mobile/android/shotclock && ./gradlew :app:compileDebugKotlin`
- `scripts/build_and_run_android.sh -p shotclock`
- Risks:
- Backend contract drift since the original data layer was removed.
- Hidden compile/runtime errors in flows not covered by smoke validation.

## Handoff

- Completed:
- Task seeded from cross-client audit; missing `data` package references confirmed in source imports.
- Next:
- Rebuild data/local, data/network, and data/repository modules incrementally and restore compile.
- Blockers:

