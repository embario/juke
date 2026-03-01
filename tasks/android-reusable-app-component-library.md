---
id: android-reusable-app-component-library
title: Reusable App component library
status: review
priority: p2
owner: claude
area: android
label: ANDROID
complexity: 5
updated_at: 2026-02-26
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
- Feature 7 (Utilities & Test Infrastructure) — deferred to a follow-up session.

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
- Builds and unit tests pass for Juke and TuneTrivia. ShotClock compiles but has pre-existing missing data layer issues unrelated to this work.

## Next

- **Feature 7 (Utilities & Test Infrastructure)**: Extract `ShareUtils`, `DebouncedSearch`, `MainDispatcherRule`, `FakeAuthRepository`, `FakeSessionStore` into JukeCore. Low-risk, follows the same typealias migration pattern. Documented in `docs/arch/android-juke-core-architecture.md` under "Feature 7 Remaining Work".
- **ShotClock data layer recovery**: ShotClock still can't fully compile due to missing app-specific API service, DTOs, and repositories (tracked separately in `tasks/shotclock-android-data-layer-recovery.md`).

## Blockers

- None for completed features.
- Feature 7 deferred by user decision, not blocked.

## Handoff

- Completed: Features 1–6 (Networking, Auth, DI, Session, Profile/Catalog, UI Components)
- Next: Feature 7 (Utilities & Test Infra) in a follow-up session
- Blockers: None
