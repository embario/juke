---
id: android-reusable-app-component-library
title: Reusable App component library
status: review
priority: p2
owner: codex
area: android
label: ANDROID
complexity: 5
updated_at: 2026-03-01
---

## Goal

Establish a reusable Android app component library.

## Scope

- Define reusable UI component primitives/patterns for Android.
- Refactor repeated UI patterns into shared components.
- Document component usage and conventions.

## Out Of Scope

- Full visual redesign unrelated to component reuse.
- iOS/web component library implementation (tracked separately).

## Acceptance Criteria

- A reusable component library exists and is consumed by app screens.
- Duplicate UI implementations are reduced in key feature flows.
- Documentation/examples exist for component usage.
- Android tests/build pass after refactor.

## Execution Notes

- Architecture document: `docs/arch/android-juke-core-architecture.md`
- Shared library location: `mobile/Packages/JukeCore/`
- Build verification: `BACKEND_URL=... ./gradlew app:assembleDebug` and `app:testDebugUnitTest` per app
- Full run: `scripts/build_and_run_android.sh -p <project>`
- Risks: large refactor surface; likely iterative rollout required.

## Completed Work

### Feature 1: Networking & Error Handling
- Extracted `NetworkModule` (OkHttp + Retrofit builder, JSON config), `NetworkErrors` (`humanReadableMessage()`, `ErrorEnvelope`), and `CoreApiService` into JukeCore.
- All three apps delegate networking to `CoreServiceLocator`.

### Feature 2: Authentication
- Extracted `AuthRepositoryContract`, `AuthRepository`, `AuthViewModel`, `SessionSnapshot`, `SessionStore` (open class), and auth DTOs into JukeCore.
- Juke keeps `JukeSessionStore` subclass (adds onboarding fields). ShotClock's missing data layer was filled with typealiases. TuneTrivia fully migrated.

### Feature 3: DI / Service Locator Core
- Created `CoreConfig` and `CoreServiceLocator` in JukeCore.
- All three app `ServiceLocator` objects delegate to `CoreServiceLocator.init()`.

### Feature 4: Session State & Auth-Gate
- Extracted `AppSessionViewModel` and `AppSessionUiState` sealed interface into JukeCore.
- Juke keeps its own `SessionViewModel` (onboarding logic). ShotClock + TuneTrivia use typealias/direct import.
- Note: Kotlin typealiases cannot access nested types of sealed interfaces — callers import `AppSessionUiState` directly from `fm.juke.core.session`.

### Feature 5: Profile & Catalog Models
- Created superset DTOs (`MusicProfileDto`, `SpotifyDataDto`, `ArtistDto`, `AlbumDto`, `TrackDto`) and domain models in JukeCore.
- Created `ProfileRepository` (open class) and `CatalogRepository` in JukeCore.
- Juke uses `JukeProfileRepository` subclass (onboarding side-effect). `JukeApiService` was deleted entirely — all endpoints now live on `CoreApiService`.

### Feature 6: UI Components
- Created `JukePlatformPalette` interface (12 color properties) + `LocalJukePlatformPalette` CompositionLocal in JukeCore.
- Created 8 shared parameterized components in `fm.juke.core.design.components`:
  - `PlatformSpinner` — parameterized animation (easing, duration, dot size, alpha range)
  - `PlatformBackground` — 2-glow pattern (accent top-left, secondary bottom-right)
  - `PlatformCard` — parameterized (padding, corner radius, elevation, shadow alpha, optional accent header bar)
  - `PlatformChip` — parameterized (accent color, padding)
  - `PlatformInputField` — composable label slot, parameterized (corner radius, background alpha, border widths)
  - `PlatformStatusBanner` — parameterized (corner radius, dot size, dot shadow, accent override)
  - `CountdownRing` — palette-aware circular progress (track, glow, gradient colors)
- Each app's palette object (`JukePalette`, `ShotClockPalette`, `TuneTriviaPalette`) implements `JukePlatformPalette`.
- Each app's theme composable provides `LocalJukePlatformPalette` via `CompositionLocalProvider`.
- All app components rewritten as thin wrappers that delegate to core, preserving exact existing function signatures.
- Exceptions kept app-specific: `JukeBackground` (structurally different glow layout), all three app Buttons (variant systems differ too much to unify).
- Builds and unit tests pass for Juke and TuneTrivia. ShotClock's compile gap was resolved in follow-up recovery work, and the reusable-library compatibility layer now builds across all three Android apps.

### Feature 7: Utilities & Test Infrastructure
- Added shared Android text-sharing helpers in `JukeCore` (`fm.juke.core.share.shareSmsOrText`) and moved ShotClock's duplicated share-launch logic behind a single app-local helper file that keeps ShotClock-specific copy in the app module.
- Added shared `DebouncedSearch` in `JukeCore` and switched ShotClock's add-tracks flow to use it instead of maintaining its own ad hoc debounce job.
- Enabled `JukeCore` `testFixtures` and extracted reusable Android test helpers into `fm.juke.core.testing`:
  - `MainDispatcherRule`
  - `FakeAuthRepository`
  - `FakeSessionStore`
- Updated TuneTrivia's tests to consume the shared test fixtures instead of app-local copies.
- Moved shared auth/session tests into `JukeCore` (`AuthViewModelTest`, `AppSessionViewModelTest`) and deleted redundant app-wrapper tests from Juke and TuneTrivia.

### Follow-up Boundary Cleanup
- Removed app-local compatibility shims for shared auth/session/catalog/profile types across `juke`, `shotclock`, and `tunetrivia`.
- Updated app code and tests to import shared `JukeCore` types directly where the implementation is genuinely common.
- Kept app-only code in app modules:
  - `juke`: `JukeSessionStore`, onboarding flow, profile specialization, world UI.
  - `shotclock`: power-hour API surface, DTOs/models, repositories, and session/playback flows.
  - `tunetrivia`: trivia API surface, DTOs/models, repository, and game flows.
- Converted each app auth view model into a thin app wrapper over `fm.juke.core.auth.AuthViewModel`, so common auth state/logic only exists once in `JukeCore`.
- Deleted stale wrapper files that only re-exported `JukeCore` types from app packages, including old auth/session aliases, DTO aliases, model aliases, network error re-exports, and the unused `JukeApiService`.
- Verified all three Android apps still compile, pass unit tests, and launch via `scripts/build_and_run_android.sh`.

## Next

- **Boundary hardening**: add lint or architecture checks if we want to prevent future app-package re-export shims for `JukeCore` classes.
- **ShotClock runtime validation**: backend-connected manual flow validation is still tracked in `tasks/shotclock-android-data-layer-recovery.md`.

## Blockers

- None for completed features.

## Handoff

- Completed: Features 1–6 (Networking, Auth, DI, Session, Profile/Catalog, UI Components)
- Completed follow-up: shared/core boundary cleanup across all three Android apps
- Verification:
  - `cd mobile/Packages/JukeCore && BACKEND_URL=http://localhost:8000 ./gradlew test`
  - `cd mobile/android/juke && BACKEND_URL=http://localhost:8000 ./gradlew :app:compileDebugKotlin`
  - `cd mobile/android/juke && BACKEND_URL=http://localhost:8000 ./gradlew :app:testDebugUnitTest`
  - `cd mobile/android/shotclock && BACKEND_URL=http://localhost:8000 ./gradlew :app:compileDebugKotlin`
  - `cd mobile/android/shotclock && BACKEND_URL=http://localhost:8000 ./gradlew :app:testDebugUnitTest`
  - `cd mobile/android/tunetrivia && BACKEND_URL=http://localhost:8000 ./gradlew :app:compileDebugKotlin`
  - `cd mobile/android/tunetrivia && BACKEND_URL=http://localhost:8000 ./gradlew :app:testDebugUnitTest`
  - `scripts/build_and_run_android.sh -p juke` -> emulator PID `39334`, app PID `2588`, logs in `logs/android-build-juke-20260301-180824.log` and `logs/logcat-juke-20260301-180824.log`
  - `scripts/build_and_run_android.sh -p shotclock` -> emulator reused on `emulator-5554`, app PID `4126`, logs in `logs/android-build-shotclock-20260301-181442.log` and `logs/logcat-shotclock-20260301-181442.log`
  - `scripts/build_and_run_android.sh -p tunetrivia` -> emulator reused on `emulator-5554`, app PID `4028`, logs in `logs/android-build-tunetrivia-20260301-181442.log` and `logs/logcat-tunetrivia-20260301-181442.log`
- Next: architecture guardrails if we want CI to prevent future `JukeCore` re-export shims
- Blockers: None
