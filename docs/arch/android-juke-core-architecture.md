# JukeCore Android Library - Architecture Document

## Executive Summary

This document outlines the architecture for **JukeCore**, a shared Android library module
that encapsulates common and reusable components across all Juke Android applications
(Juke, ShotClock, and TuneTrivia). This refactoring will eliminate code duplication,
provide ShotClock's missing data layer, ensure consistent behavior, and reduce maintenance
overhead.

The library lives at `mobile/Packages/JukeCore/`, mirroring the iOS shared package
layout (`mobile/ios/Packages/JukeKit/`).

---

## Current State Analysis

### Code Distribution

| App | Kotlin Files (main) | Approx Lines | Package |
|-----|---------------------|-------------|---------|
| Juke | 38 | ~1,600 | `fm.juke.mobile` |
| ShotClock | 35 | ~2,900 | `fm.shotclock.mobile` |
| TuneTrivia | 44 | ~3,200 | `fm.tunetrivia.mobile` |
| **Total** | **117** | **~7,700** | |

### Critical Finding: ShotClock Missing Data Layer

ShotClock has **no `data/` directory** at all — no network service, no DTOs, no
repositories, no local session storage. Its ViewModels and ServiceLocator import from
packages that have no source files. JukeCore will **fill** these gaps rather than just
removing duplicates.

---

## Identified Duplication Categories

### 1. Authentication System (HIGHEST DUPLICATION)

| Component | Juke | ShotClock | TuneTrivia | Duplication |
|-----------|------|-----------|------------|-------------|
| AuthViewModel | 127 lines | 147 lines | 147 lines | ~90% identical |
| AuthScreen | 206 lines | 211 lines | 217 lines | ~85% identical |
| AuthRepository | 42 lines | MISSING | 42 lines | 95% identical |
| AuthRepositoryContract | 22 lines | MISSING | 22 lines | 100% identical |
| Auth DTOs | 29 lines | MISSING | 29 lines | 100% identical |
| SessionSnapshot | 7 lines | MISSING | 7 lines | 100% identical |
| SessionStore | 69 lines | MISSING | 51 lines | ~85% identical |

**Common functionality across all apps:**
- Login with username/password returning auth token
- Register with username/email/password/confirmation
- Logout with server-side session revocation and local store clear
- Session persistence via Android DataStore (token + username)
- Reactive session stream via `Flow<SessionSnapshot?>`
- Form validation (email format, password min-length 8, confirm match)
- `DISABLE_REGISTRATION` BuildConfig flag support

**Variations:**
- Juke's SessionStore has extra `onboardingCompletedAt` field
- AuthScreen branding text differs (app name, tagline)
- ShotClock's AuthViewModel is 20 lines longer (additional validation)

### 2. Networking & Error Handling (HIGH DUPLICATION)

| Component | Juke | ShotClock | TuneTrivia | Duplication |
|-----------|------|-----------|------------|-------------|
| NetworkErrors.kt | 35 lines | MISSING | 35 lines | 100% identical |
| OkHttp + Retrofit setup | ~60 lines | ~40 lines | ~35 lines | ~80% identical |
| Auth API endpoints | ~20 lines | MISSING | ~20 lines | 100% identical |
| Profile API endpoints | ~20 lines | MISSING | N/A | — |

**Common functionality:**
- `humanReadableMessage()` extension on `Throwable` — identical in Juke and TuneTrivia
- `ErrorEnvelope` data class for JSON error parsing (detail, nonFieldErrors, passwordConfirm)
- OkHttp client with logging interceptor (BODY in debug, BASIC in release)
- Retrofit builder with kotlinx.serialization JSON converter
- `normalizedBaseUrl()` helper ensuring trailing slash
- Auth endpoints: POST login, POST register, POST logout
- Profile endpoints: GET myProfile, PATCH profile, GET searchProfiles

### 3. Session State Management (HIGH DUPLICATION)

| Component | Juke | ShotClock | TuneTrivia | Duplication |
|-----------|------|-----------|------------|-------------|
| AppSessionViewModel | ~64 lines | 41 lines | 40 lines | ~90% identical |
| AppSessionUiState | sealed interface | sealed interface | sealed interface | 100% identical |
| Auth-gate in App composable | ~97 lines | ~51 lines | ~50 lines | ~90% identical |
| Splash screen | ~15 lines | ~15 lines | ~15 lines | 100% identical |

**Common auth-gate pattern (identical across all 3 apps):**
```
AppSessionUiState.Loading  → Splash (spinner + text)
AppSessionUiState.SignedOut → AuthRoute
AppSessionUiState.SignedIn  → HomeScreen
```

### 4. DI / Service Locator (HIGH DUPLICATION)

| Component | Juke | ShotClock | TuneTrivia | Duplication |
|-----------|------|-----------|------------|-------------|
| ServiceLocator | 150 lines | 92 lines | 82 lines | ~60% core identical |
| Application class | 16 lines | N/A | N/A | structural |
| MainActivity | 23 lines | 23 lines | 23 lines | 100% structural |

**Common functionality:**
- Singleton object with `init(context: Context)`
- JSON config: `kotlinx.serialization` with `ignoreUnknownKeys`, `explicitNulls = false`
- OkHttp client setup with logging interceptor
- Retrofit instance creation with base URL normalization
- Lazy `apiService`, `sessionStore`, `authRepository` initialization
- `ensureInitialized()` guard

### 5. UI Design System Components (HIGH DUPLICATION)

| Component | Juke | ShotClock | TuneTrivia | Duplication |
|-----------|------|-----------|------------|-------------|
| Spinner | 62 lines | 62 lines | 62 lines | ~95% identical |
| StatusBanner | 59 lines | 66 lines | 66 lines | ~90% identical |
| Card | 62 lines | 64 lines | 84 lines | ~80% identical |
| InputField | 100 lines | 104 lines | 101 lines | ~85% identical |
| Button | 124 lines | 104 lines | 87 lines | ~70% identical |
| Chip | 41 lines | 41 lines | 41 lines | ~95% identical |
| Background | 59 lines | 57 lines | 57 lines | ~95% identical |
| CountdownRing | N/A | 73 lines | 73 lines | 100% identical |
| Theme | 135 lines | 128 lines | 127 lines | ~50% structural |
| Palette | 23 lines | 19 lines | 21 lines | ~40% structural |

**Exact duplicates (byte-for-byte identical between ShotClock + TuneTrivia):**
- Spinner, Background, CountdownRing

**Component parameter variations:**
- Button variants: 3 (Juke) vs 4 (ShotClock: + SECONDARY, DESTRUCTIVE) vs 5 (TuneTrivia: + LINK)
- Card corner radius: 28dp (Juke), 16dp (ShotClock/TuneTrivia)
- Spinner easing: FastOutSlowIn/800ms (Juke) vs Linear/700ms (ShotClock/TuneTrivia)
- TuneTrivia Card adds optional accentColor header bar

### 6. Profile System (MEDIUM DUPLICATION)

| Component | Juke | ShotClock | TuneTrivia |
|-----------|------|-----------|------------|
| MusicProfile model | 51 lines | 34 lines | N/A |
| ProfileDtos | 34 lines | MISSING | N/A |
| ProfileRepository | 38 lines | MISSING | N/A |
| ProfileViewModel | 82 lines | 47 lines | N/A |
| ProfileScreen | 288 lines | 191 lines | N/A |

**Common functionality (Juke + ShotClock):**
- `MusicProfile` domain model with favorites (genres, artists, albums, tracks)
- DTO-to-domain mapping via `toDomain()` extension
- Profile loading with error handling in ViewModel
- Profile display with favorite shelves/chips
- `humanReadableMessage()` for error display

**Variations:**
- Juke has profile search, focus-on-user, and search results in its ProfileViewModel
- Juke's ProfileScreen has 100 more lines (search section, hero card)
- ShotClock's MusicProfile omits `name`, `avatarUrl`, `onboardingCompletedAt`

### 7. Catalog Search (MEDIUM DUPLICATION)

| Component | Juke | ShotClock | TuneTrivia |
|-----------|------|-----------|------------|
| CatalogModels (Track) | 96 lines | 30 lines | N/A |
| CatalogDtos | 71 lines | MISSING | N/A |
| CatalogRepository | 41 lines | MISSING | N/A |
| Search tracks API | in JukeApiService | MISSING | in TuneTriviaApiService |

**Common functionality:**
- `Track` domain model (id, name, duration, explicit, spotifyUri, previewUrl)
- Track search via Retrofit endpoint (`GET /api/v1/catalog/tracks/`)
- DTO-to-domain mapping with Spotify data extraction
- ShotClock and TuneTrivia both use `CatalogRepository` for track search in AddTracks flow

### 8. Shared Utility Patterns (NEW — found in re-audit)

| Pattern | Juke | ShotClock | TuneTrivia | Duplication |
|---------|------|-----------|------------|-------------|
| Share/Intent utility | N/A | 3 copies (~20 lines each) | N/A | 100% within ShotClock |
| Debounced search | N/A | 1 copy (AddTracksVM) | 1 copy (AddTracksVM) | ~90% identical |
| Polling mechanism | N/A | 2 VMs (5s, 3s) | 2 VMs (3s, 2s) | ~80% identical |
| MediaPlayer lifecycle | N/A | N/A | 1 copy (GamePlayScreen) | App-specific |
| Test: MainDispatcherRule | N/A | N/A | 23 lines | Reusable |
| Test: FakeAuthRepository | N/A | N/A | ~30 lines | Reusable |

**Share Intent utility (ShotClock — 3 identical copies):**
- Found in SessionLobbyScreen, PlaybackScreen, SessionEndScreen
- Builds track list text and launches `ACTION_SEND` intent
- Should be extracted to a single utility function

**Debounced search (ShotClock + TuneTrivia AddTracksViewModel):**
- Both cancel previous search job, delay 400ms, then execute
- Identical pattern, different repository calls

**Polling mechanism (ShotClock + TuneTrivia):**
- Job-based infinite loop with delay + state refresh
- Cleanup on `onCleared()` or state change
- ShotClock: 5s lobby, 3s playback
- TuneTrivia: 3s lobby, 2s gameplay

---

## Decisions (Resolved)

1. **CountdownRing** moves into JukeCore. Although Juke doesn't currently use it,
   ShotClock and TuneTrivia share it identically, and it may be useful for future Juke
   features.

2. **Theme/Palette** structures live in JukeCore as interfaces. Each app implements the
   `JukePlatformPalette` interface with its own colors. The shared components read from
   this interface rather than hard-coded colors.

3. **DNS-over-HTTPS** debug feature (Juke-only) does **not** move to JukeCore. It remains
   in Juke's app-level ServiceLocator.

4. **SessionStore extensibility** — JukeCore provides a base `SessionStore` (token +
   username). Juke subclasses it in its own app module to add `onboardingCompletedAt`.
   ShotClock and TuneTrivia use the base class directly.

5. **ShotClock's missing data layer** — built directly in JukeCore. No throwaway bridge
   code. ShotClock will depend on JukeCore immediately for its network, repository, DTO,
   and session storage needs.

6. **App-specific API services** — `CoreApiService` has auth + profile endpoints. Each
   app keeps its own independent Retrofit interface (e.g., `ShotClockApiService`,
   `TuneTriviaApiService`) for app-specific endpoints, sharing the OkHttp client and
   Retrofit instance from `NetworkModule`.

7. **Test migration** — `AuthViewModelTest`, `MainDispatcherRule`, and
   `FakeAuthRepository` move from TuneTrivia into JukeCore's test source set. They test
   shared code and should live alongside it.

---

## Proposed Library Structure

```
mobile/Packages/JukeCore/
├── build.gradle.kts                        # Android Library module
├── settings.gradle.kts                     # Standalone Gradle project
├── src/main/java/fm/juke/core/
│   ├── auth/
│   │   ├── AuthRepositoryContract.kt       # Interface for auth operations
│   │   ├── AuthRepository.kt              # Default implementation (login/register/logout)
│   │   ├── AuthViewModel.kt               # Shared auth form ViewModel
│   │   ├── AuthScreen.kt                  # Composable with app-customization hooks
│   │   └── dto/
│   │       └── AuthDtos.kt                # LoginRequest/Response, RegisterRequest/Response
│   ├── session/
│   │   ├── SessionSnapshot.kt            # data class (username, token)
│   │   ├── SessionStore.kt               # DataStore-based persistence
│   │   └── AppSessionViewModel.kt        # Auth-gate ViewModel (Loading/SignedOut/SignedIn)
│   ├── network/
│   │   ├── NetworkErrors.kt              # humanReadableMessage(), ErrorEnvelope
│   │   ├── CoreApiService.kt             # Retrofit interface (auth + profile endpoints)
│   │   └── NetworkModule.kt              # OkHttp client + Retrofit factory builder
│   ├── profile/
│   │   ├── MusicProfile.kt               # Domain model + DTO-to-domain mapping
│   │   ├── ProfileRepository.kt          # Profile fetch/search/patch operations
│   │   ├── ProfileViewModel.kt           # Profile loading ViewModel
│   │   └── dto/
│   │       └── ProfileDtos.kt            # MusicProfileDto, ProfileSearchEntry
│   ├── catalog/
│   │   ├── CatalogModels.kt              # Track, Artist, Album domain models
│   │   ├── CatalogRepository.kt          # Track/artist/album search
│   │   └── dto/
│   │       └── CatalogDtos.kt            # TrackDto, ArtistDto, SpotifyDataDto, etc.
│   ├── design/
│   │   ├── JukePlatformPalette.kt        # Palette interface for app-specific colors
│   │   ├── JukePlatformTheme.kt          # Theme wrapper accepting palette
│   │   └── components/
│   │       ├── PlatformSpinner.kt        # Animated loading spinner
│   │       ├── PlatformStatusBanner.kt   # Info/Success/Warning/Error banners
│   │       ├── PlatformCard.kt           # Gradient card with shadow
│   │       ├── PlatformInputField.kt     # Text input with label and error states
│   │       ├── PlatformButton.kt         # Button with variants (Primary/Secondary/Ghost/Destructive/Link)
│   │       ├── PlatformChip.kt           # Selectable pill/chip
│   │       ├── PlatformBackground.kt     # Gradient background with radial glows
│   │       └── CountdownRing.kt          # Canvas-based circular progress ring
│   ├── util/
│   │   ├── ShareUtils.kt                 # Share intent builder (extracted from ShotClock 3x dupe)
│   │   └── DebouncedSearch.kt            # Reusable debounce utility for search fields
│   └── di/
│       └── CoreServiceLocator.kt         # Shared DI (OkHttp, Retrofit, auth repos, core config)
├── src/test/java/fm/juke/core/
│   ├── testutil/
│   │   ├── MainDispatcherRule.kt         # Coroutine test dispatcher rule
│   │   └── FakeAuthRepository.kt         # Fake for testing auth flows
│   └── auth/
│       └── AuthViewModelTest.kt          # Shared auth ViewModel tests
└── src/main/AndroidManifest.xml           # Minimal library manifest
```

---

## Feature Extraction Plan

### Feature 1: Networking & Error Handling (Priority: HIGHEST — Foundation)

**What moves to JukeCore:**
- `NetworkErrors.kt` — `humanReadableMessage()` extension + `ErrorEnvelope`
- `NetworkModule.kt` — OkHttp client builder + Retrofit factory
- `CoreApiService.kt` — Auth endpoints (login/register/logout) + profile endpoints

**Design:**
```kotlin
object NetworkModule {
    fun buildOkHttpClient(isDebug: Boolean): OkHttpClient
    fun buildRetrofit(baseUrl: String, client: OkHttpClient, json: Json): Retrofit
    val json: Json  // ignoreUnknownKeys, explicitNulls=false
}
```

Apps create their own API service interfaces that extend beyond auth/profile, but share
the OkHttp client and Retrofit instance from `NetworkModule`.

**Estimated lines removed per app:**

| File | Juke | ShotClock | TuneTrivia |
|------|------|-----------|------------|
| NetworkErrors | -35 | FILLS GAP | -35 |
| ServiceLocator (network setup) | -60 | -40 | -35 |
| API Service (auth endpoints) | -20 | FILLS GAP | -20 |
| **Subtotal** | **-115** | **-40** | **-90** |

### Feature 2: Authentication (Priority: HIGHEST — Core value)

**What moves to JukeCore:**
- `AuthRepositoryContract` — interface (100% reusable)
- `AuthRepository` — default implementation parameterized by `CoreApiService`
- `AuthDtos` — LoginRequest/Response, RegisterRequest/Response
- `SessionSnapshot` — data class (username, token)
- `SessionStore` — DataStore persistence with reactive Flow
- `AuthViewModel` — shared auth form state management
- `AuthScreen` — composable parameterized by app name, tagline, palette

**Registration deep-link support:**
When `DISABLE_REGISTRATION` is true, the shared AuthScreen displays a CTA that launches
an Intent to open the Juke app's registration via deep-link (`juke://register`) or falls
back to the frontend URL's `/register` path. Apps supply `frontendUrl` via `CoreConfig`.

**App-specific remainders:**
- Juke: Extends `SessionStore` with `onboardingCompletedAt` in its own subclass
- Each app: Supplies its own palette and branding text to `AuthScreen`

**Estimated lines removed per app:**

| File | Juke | ShotClock | TuneTrivia |
|------|------|-----------|------------|
| AuthRepositoryContract | -22 | FILLS GAP | -22 |
| AuthRepository | -42 | FILLS GAP | -42 |
| AuthDtos | -29 | FILLS GAP | -29 |
| SessionSnapshot | -7 | FILLS GAP | -7 |
| SessionStore | -50 (keep onboarding ext) | FILLS GAP | -51 |
| AuthViewModel | -127 | -147 | -147 |
| AuthScreen | -206 | -211 | -217 |
| **Subtotal** | **-483** | **-358** | **-515** |

### Feature 3: DI / Service Locator Core (Priority: HIGH)

**What moves to JukeCore:**
- `CoreServiceLocator` — shared init for network, auth, session, profile dependencies

**Configuration model:**
```kotlin
data class CoreConfig(
    val backendUrl: String,
    val frontendUrl: String,       // for registration deep-links
    val disableRegistration: Boolean,
    val appContext: Context
)
```

Each app's `ServiceLocator` delegates to `CoreServiceLocator` for shared deps and adds
its own app-specific repositories (e.g., `PowerHourRepository`, `TuneTriviaRepository`).

**Estimated lines removed per app:**

| File | Juke | ShotClock | TuneTrivia |
|------|------|-----------|------------|
| ServiceLocator (core portion) | -100 | -60 | -55 |
| Application class | -16 | N/A | N/A |
| **Subtotal** | **-116** | **-60** | **-55** |

### Feature 4: Session State & Auth-Gate (Priority: HIGH)

**What moves to JukeCore:**
- `AppSessionViewModel` — sealed interface `AppSessionUiState` (Loading/SignedOut/SignedIn)
- `Splash` composable — shared spinner + configurable text

Each app's root composable (`JukeApp`, `ShotClockApp`, `TuneTriviaApp`) uses
`AppSessionViewModel` from JukeCore and delegates to the shared `Splash` composable
during loading. The auth-gate `when` block remains in each app since it routes to
app-specific `HomeScreen` implementations.

**Estimated lines removed per app:**

| File | Juke | ShotClock | TuneTrivia |
|------|------|-----------|------------|
| SessionViewModel / AppSessionViewModel | -50 | -41 | -40 |
| Splash composable | -15 | -15 | -15 |
| **Subtotal** | **-65** | **-56** | **-55** |

### Feature 5: Profile & Catalog Models (Priority: MEDIUM)

**What moves to JukeCore:**
- `MusicProfile` domain model + `MusicProfileDto.toDomain()` mapping
- `ProfileDtos` — serializable DTOs for profile API
- `ProfileRepository` — fetch/search/patch profile operations
- `ProfileViewModel` — base profile loading with error handling
- `CatalogModels` — Track, Artist, Album domain models
- `CatalogDtos` — SpotifyDataDto, TrackDto, ArtistDto, AlbumDto, etc.
- `CatalogRepository` — track/artist/album search

**Estimated lines removed per app:**

| File | Juke | ShotClock | TuneTrivia |
|------|------|-----------|------------|
| MusicProfile | -51 | -34 | N/A |
| ProfileDtos | -34 | FILLS GAP | N/A |
| ProfileRepository | -38 | FILLS GAP | N/A |
| ProfileViewModel | -50 | -47 | N/A |
| CatalogModels | -96 | -30 | N/A |
| CatalogDtos | -71 | FILLS GAP | N/A |
| CatalogRepository | -41 | FILLS GAP | N/A |
| **Subtotal** | **-381** | **-111** | **N/A** |

### Feature 6: UI Components (Priority: HIGH)

**What moves to JukeCore:**
All components parameterized by `JukePlatformPalette` interface:

```kotlin
interface JukePlatformPalette {
    val accent: Color
    val accentSoft: Color
    val secondary: Color
    val surface: Color
    val surfaceVariant: Color
    val onSurface: Color
    val onSurfaceVariant: Color
    val background: Color
    val error: Color
    val success: Color
    val warning: Color
}
```

Each app provides its own `object : JukePlatformPalette` implementation (e.g., orange for
Juke, pink for ShotClock, red for TuneTrivia) and a thin `JukePlatformTheme` wrapper that
provides the palette via `CompositionLocalProvider`.

**Button variant unification:**
The shared `PlatformButton` supports all 5 variants across the apps:
PRIMARY, SECONDARY, GHOST, DESTRUCTIVE, LINK. Each app uses whichever subset it needs.

**Estimated lines removed per app:**

| Component | Juke | ShotClock | TuneTrivia |
|-----------|------|-----------|------------|
| Spinner | -62 | -62 | -62 |
| StatusBanner | -59 | -66 | -66 |
| Card | -62 | -64 | -84 |
| InputField | -100 | -104 | -101 |
| Button | -124 | -104 | -87 |
| Chip | -41 | -41 | -41 |
| Background | -59 | -57 | -57 |
| CountdownRing | N/A | -73 | -73 |
| Theme/Palette (structural) | -135 | -128 | -127 |
| **Subtotal** | **-642** | **-699** | **-698** |

### Feature 7: Utilities & Test Infrastructure (Priority: MEDIUM)

**What moves to JukeCore:**
- `ShareUtils.kt` — share intent builder (deduplicate ShotClock's 3 copies)
- `DebouncedSearch.kt` — reusable debounce for search fields
- `MainDispatcherRule` — test coroutine dispatcher rule (from TuneTrivia)
- `FakeAuthRepository` — test fake for auth flows (from TuneTrivia)

**Estimated lines removed per app:**

| File | Juke | ShotClock | TuneTrivia |
|------|------|-----------|------------|
| Share utility (3 copies) | N/A | -40 | N/A |
| Debounced search | N/A | -10 | -10 |
| MainDispatcherRule | N/A | N/A | -23 |
| FakeAuthRepository | N/A | N/A | -30 |
| **Subtotal** | **N/A** | **-50** | **-63** |

---

## Total Estimated Impact

| App | Lines Removed | Gaps Filled | Current Total | Net Reduction |
|-----|--------------|-------------|---------------|---------------|
| Juke | ~1,802 | — | ~1,600 | Significant (most code moves to core) |
| ShotClock | ~1,374 | ~250+ (data layer) | ~2,900 | ~47% |
| TuneTrivia | ~1,476 | — | ~3,200 | ~46% |
| **Total consolidated** | **~4,652** | | | |

**Note:** Juke's high removal percentage reflects that most of its code is auth, profile,
catalog, and design system — which are all shared concerns. Its app-specific code
(onboarding, JukeWorld) is relatively small.

ShotClock benefits both from code removal AND gap filling — JukeCore provides the data
layer (network, repos, DTOs, session storage) that ShotClock is currently missing.

---

## Integration Strategy

### Gradle Setup

JukeCore is a standalone Gradle project consumed via composite builds:

```kotlin
// mobile/Packages/JukeCore/settings.gradle.kts
rootProject.name = "JukeCore"

// mobile/Packages/JukeCore/build.gradle.kts
plugins {
    id("com.android.library")
    id("org.jetbrains.kotlin.plugin.compose")
    id("org.jetbrains.kotlin.plugin.serialization")
}
android {
    namespace = "fm.juke.core"
    compileSdk = 36
    defaultConfig { minSdk = 26 }
}
```

```kotlin
// Each app's settings.gradle.kts (e.g., mobile/android/juke/settings.gradle.kts)
includeBuild("../../Packages/JukeCore") {
    dependencySubstitution {
        substitute(module("fm.juke:core")).using(project(":"))
    }
}

// Each app's app/build.gradle.kts
dependencies {
    implementation("fm.juke:core")
}
```

### Migration Order

1. **Feature 1: Networking & Error Handling** — Foundation layer, no UI dependencies
2. **Feature 2: Authentication** — Depends on networking; highest value
3. **Feature 3: DI / Service Locator Core** — Wires everything together
4. **Feature 4: Session State & Auth-Gate** — Depends on auth
5. **Feature 5: Profile & Catalog Models** — Depends on networking + DI
6. **Feature 6: UI Components** — Independent but last for stability
7. **Feature 7: Utilities & Test Infrastructure** — Final cleanup

### Compatibility Notes

- All three apps use identical Gradle plugin versions (AGP 9.0.0, Kotlin 2.2.10)
- All three apps target the same SDK levels (compileSdk 36, minSdk 26, JVM 21)
- All three apps use the same dependency versions (Retrofit 2.11, OkHttp 4.12,
  kotlinx.serialization 1.7.1, Compose BOM 2024.10.01, Coil 2.7.0)
- Each app's `BuildConfig` fields (`BACKEND_URL`, `DISABLE_REGISTRATION`) are passed
  to JukeCore via `CoreConfig` at runtime, not at compile time
- JukeCore does NOT use `BuildConfig` itself — all configuration is injected

---

## Refactoring Progress Log

| Feature | Status | Juke Lines Removed | ShotClock Lines Removed | TuneTrivia Lines Removed |
|---------|--------|-------------------|------------------------|-------------------------|
| Networking & Errors | DONE | -95 (ServiceLocator+NetworkErrors) | -32 (ServiceLocator+imports) | -55 (ServiceLocator+NetworkErrors) |
| Authentication | DONE | -150 (AuthRepo+DTOs+SessionStore+ServiceLocator) | -0 (fills gap: 4 typealias files) | -130 (AuthRepo+DTOs+SessionStore+ServiceLocator+Fakes) |
| DI / Service Locator | DONE | -25 (delegate to CoreServiceLocator) | -30 (delegate to CoreServiceLocator) | -25 (delegate to CoreServiceLocator) |
| Session State & Auth-Gate | DONE | -0 (Juke keeps own SessionViewModel) | -35 (typealias AppSessionViewModel) | -35 (typealias AppSessionViewModel) |
| Profile & Catalog Models | DONE | -280 (DTOs+models+repos+JukeApiService endpoints) | -0 (fills gap: DTO typealiases) | N/A (TuneTrivia has no profile/catalog) |
| UI Components | DONE | -120 (Spinner+Card+Chip+InputField+StatusBanner delegate to core; Background+Button stay app-specific) | -200 (all 8 components delegate to core; Button stays app-specific) | -200 (all 8 components delegate to core; Button stays app-specific) |
| Utilities & Test Infra | DEFERRED | — | — | — |

### Feature 7 Remaining Work (Deferred)

Feature 7 (Utilities & Test Infrastructure) was intentionally deferred. The following
items are candidates for extraction into JukeCore in a future session:

- **ShareUtils** — `ShareIntent` builder used in Juke and ShotClock for sharing links
- **DebouncedSearch** — Coroutine-based debounce helper used in profile/catalog search
- **MainDispatcherRule** — JUnit test rule that replaces `Dispatchers.Main` (identical across Juke + TuneTrivia)
- **FakeAuthRepository** — Test fake implementing `AuthRepositoryContract` (identical across Juke + TuneTrivia)
- **FakeSessionStore** — Test fake for `SessionStore` used in ViewModel tests

These are low-risk, high-value extractions that follow the same typealias migration pattern
established in Features 1–6.

---

*Document Version: 1.1*
*Last Updated: 2026-02-26*
