---
id: shotclock-android-data-layer-recovery
title: Restore ShotClock Android data layer and compile baseline
status: review
priority: p1
owner: codex
area: android
label: ANDROID
complexity: 3
updated_at: 2026-03-01
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
- Restored the missing ShotClock Android compatibility layer under `app/src/main/java/fm/shotclock/mobile/data/`:
  - Added `ShotClockApiService` for power-hour endpoints while keeping `CoreApiService` inheritance for shared auth/profile/catalog calls.
  - Added session/request DTOs (`SessionDto`, `SessionPlayerDto`, `SessionTrackDto`, `CreateSessionRequest`, etc.).
  - Added local `CatalogRepository` and `ProfileRepository` wrappers that translate `JukeCore` models back into ShotClock’s existing domain models.
  - Added `PowerHourRepository` with session CRUD, playback controls, player/track listing, add/remove/import track flows, and token handling.
- Updated `SessionListRoute`, `SessionLobbyViewModel`, and `PlaybackViewModel` to use the authenticated username from `SessionSnapshot` for admin checks, matching the current `JukeCore` auth snapshot contract.
- Verified `cd mobile/android/shotclock && BACKEND_URL=http://localhost:8000 ./gradlew :app:compileDebugKotlin` succeeds.
- Verified `cd mobile/android/shotclock && BACKEND_URL=http://localhost:8000 ./gradlew :app:testDebugUnitTest` succeeds (`NO-SOURCE` for unit tests).
- Verified `scripts/build_and_run_android.sh -p shotclock` succeeds.
- Captured run artifacts:
  - Emulator PID: `56117`
  - App PID: `2844`
  - Emulator log: `logs/emulator-jukeApi36-20260301-095154.log`
  - Build/install log: `logs/android-build-shotclock-20260301-095154.log`
  - App logcat: `logs/logcat-shotclock-20260301-095154.log`
- Next:
- Manually verify login, session list, session creation, add tracks, and playback on emulator/device against a live backend.
- Add focused unit tests around the restored `PowerHourRepository` mapping/flow if ShotClock test coverage is being expanded.
- Blockers:
- None for compile/build baseline. Backend-connected manual flow verification is still pending.
