# TuneTrivia - Power Hour Android App Architecture

## 1. Overview

**TuneTrivia** is a native Android app that enables users to create and participate in Power Hour drinking game sessions. A Power Hour involves a shared playlist where a random 60-second (configurable) segment of each track plays before a transition audio clip signals players to drink and guess whose song it is.

The app integrates with the existing Juke backend platform for authentication, Spotify account linking, and music catalog access. It replicates the architecture and patterns established by the Juke Android app (`mobile/android/juke`) while adding session-oriented gameplay features.

---

## 2. System Architecture

```
+-----------------------------------------------------------+
|                  TuneTrivia Android App                      |
|  +-----------+  +------------+  +-----------------------+  |
|  |   Views   |  | ViewModels |  |      Services         |  |
|  | (Compose) |--| (MVVM)     |--|  (API, Audio, Share)  |  |
|  +-----------+  +------------+  +-----------------------+  |
|                                         |                   |
|  +--------------------------------------+                   |
|  |      Retrofit + OkHttp (HTTP/Token)  |                   |
|  +--------------------------------------+                   |
+----------------------------+--------------------------------+
                             | HTTPS
+----------------------------+--------------------------------+
|                   Juke Backend (Django)                      |
|  +------------+  +----------+  +--------------------------+ |
|  | juke_auth  |  |  catalog |  |   powerhour              | |
|  | (users,    |  | (tracks, |  | (sessions, players,      | |
|  |  profiles) |  |  search) |  |  playlists, config)      | |
|  +------------+  +----------+  +--------------------------+ |
|                        |                                     |
|  +---------------------+----------------------------------+  |
|  |          Spotify Web API / Playback SDK                |  |
|  +--------------------------------------------------------+  |
+--------------------------------------------------------------+
```

---

## 3. Tech Stack

| Layer | Technology | Purpose |
|-------|-----------|---------|
| Language | Kotlin | Primary language |
| UI Framework | Jetpack Compose + Material3 | Declarative UI |
| Architecture | MVVM | ViewModels + mutable state |
| DI | Service Locator (singleton object) | Dependency management |
| Networking | Retrofit 2.11 + OkHttp 4.12 | HTTP client |
| Serialization | kotlinx.serialization 1.7.1 | JSON parsing |
| Local Storage | DataStore Preferences 1.1.1 | Token/session persistence |
| Async | Kotlin Coroutines 1.9.0 + Flow | Concurrency |
| Navigation | Compose Navigation 2.8.0 | Screen routing |
| Image Loading | Coil Compose 2.7.0 | Async image loading |
| Build | Gradle Kotlin DSL | Build system |
| Target | Android API 36 (min 26) | Platform |

---

## 4. Project Structure

```
mobile/android/tunetrivia/
+-- app/
|   +-- build.gradle.kts
|   +-- proguard-rules.pro
|   +-- src/
|       +-- main/
|       |   +-- AndroidManifest.xml
|       |   +-- java/fm/tunetrivia/mobile/
|       |   |   +-- MainActivity.kt
|       |   |   +-- core/
|       |   |   |   +-- di/
|       |   |   |   |   +-- ServiceLocator.kt
|       |   |   |   +-- design/
|       |   |   |       +-- TuneTriviaTheme.kt
|       |   |   |       +-- TuneTriviaPalette.kt
|       |   |   |       +-- components/
|       |   |   |           +-- TuneTriviaButton.kt
|       |   |   |           +-- TuneTriviaInputField.kt
|       |   |   |           +-- TuneTriviaCard.kt
|       |   |   |           +-- TuneTriviaChip.kt
|       |   |   |           +-- TuneTriviaSpinner.kt
|       |   |   |           +-- TuneTriviaStatusBanner.kt
|       |   |   |           +-- TuneTriviaBackground.kt
|       |   |   |           +-- CountdownRing.kt
|       |   |   +-- data/
|       |   |   |   +-- network/
|       |   |   |   |   +-- TuneTriviaApiService.kt
|       |   |   |   |   +-- dto/
|       |   |   |   |   |   +-- AuthDtos.kt
|       |   |   |   |   |   +-- ProfileDtos.kt
|       |   |   |   |   |   +-- SessionDtos.kt
|       |   |   |   |   |   +-- CatalogDtos.kt
|       |   |   |   |   +-- ApiError.kt
|       |   |   |   +-- local/
|       |   |   |   |   +-- SessionStore.kt
|       |   |   |   +-- repository/
|       |   |   |       +-- AuthRepository.kt
|       |   |   |       +-- ProfileRepository.kt
|       |   |   |       +-- PowerHourRepository.kt
|       |   |   |       +-- CatalogRepository.kt
|       |   |   +-- model/
|       |   |   |   +-- Session.kt
|       |   |   |   +-- SessionTrack.kt
|       |   |   |   +-- SessionPlayer.kt
|       |   |   |   +-- MusicProfile.kt
|       |   |   |   +-- CatalogModels.kt
|       |   |   +-- ui/
|       |   |       +-- auth/
|       |   |       |   +-- AuthScreen.kt
|       |   |       |   +-- AuthViewModel.kt
|       |   |       +-- navigation/
|       |   |       |   +-- TuneTriviaApp.kt
|       |   |       |   +-- HomeScreen.kt
|       |   |       +-- session/
|       |   |       |   +-- AppSessionViewModel.kt
|       |   |       |   +-- create/
|       |   |       |   |   +-- CreateSessionScreen.kt
|       |   |       |   |   +-- CreateSessionViewModel.kt
|       |   |       |   +-- join/
|       |   |       |   |   +-- JoinSessionScreen.kt
|       |   |       |   |   +-- JoinSessionViewModel.kt
|       |   |       |   +-- lobby/
|       |   |       |   |   +-- SessionLobbyScreen.kt
|       |   |       |   |   +-- SessionLobbyViewModel.kt
|       |   |       |   +-- tracks/
|       |   |       |   |   +-- AddTracksScreen.kt
|       |   |       |   |   +-- AddTracksViewModel.kt
|       |   |       |   +-- playback/
|       |   |       |   |   +-- PlaybackScreen.kt
|       |   |       |   |   +-- PlaybackViewModel.kt
|       |   |       |   +-- ended/
|       |   |       |       +-- SessionEndScreen.kt
|       |   |       +-- profile/
|       |   |           +-- ProfileScreen.kt
|       |   |           +-- ProfileViewModel.kt
|       |   +-- res/
|       |       +-- drawable/
|       |       +-- raw/
|       |       |   +-- transition_airhorn.mp3
|       |       |   +-- transition_buzzer.mp3
|       |       |   +-- transition_bell.mp3
|       |       |   +-- transition_whistle.mp3
|       |       |   +-- transition_glass_clink.mp3
|       |       +-- mipmap-anydpi-v26/
|       |       |   +-- ic_launcher.xml
|       |       |   +-- ic_launcher_round.xml
|       |       +-- mipmap-hdpi/
|       |       +-- mipmap-mdpi/
|       |       +-- mipmap-xhdpi/
|       |       +-- mipmap-xxhdpi/
|       |       +-- mipmap-xxxhdpi/
|       |       +-- values/
|       |           +-- colors.xml
|       |           +-- strings.xml
|       |           +-- themes.xml
|       +-- test/
|           +-- java/fm/tunetrivia/mobile/
|               +-- core/di/ServiceLocatorTest.kt
|               +-- ui/auth/AuthViewModelTest.kt
|               +-- ui/session/
|               |   +-- CreateSessionViewModelTest.kt
|               |   +-- JoinSessionViewModelTest.kt
|               |   +-- SessionLobbyViewModelTest.kt
|               |   +-- PlaybackViewModelTest.kt
|               +-- data/repository/
|                   +-- PowerHourRepositoryTest.kt
+-- build.gradle.kts
+-- settings.gradle.kts
+-- gradle.properties
+-- gradlew
+-- gradlew.bat
+-- gradle/
+-- brand_assets/
+-- ARCHITECTURE.md
```

---

## 5. Backend API Integration

The app consumes the existing `powerhour` Django app endpoints, plus auth and catalog endpoints:

### 5.1 Authentication Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/v1/auth/login/` | Token login |
| POST | `/api/v1/auth/logout/` | Token logout |
| POST | `/api/v1/auth/accounts/register/` | User registration |

### 5.2 Profile Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/v1/music-profiles/me/` | Current user profile |
| GET | `/api/v1/music-profiles/{username}/` | View a profile |

### 5.3 Catalog Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| GET | `/api/v1/tracks/?search=query` | Search tracks |

### 5.4 Power Hour Session Endpoints

| Method | Endpoint | Purpose |
|--------|----------|---------|
| POST | `/api/v1/powerhour/sessions/` | Create a session |
| GET | `/api/v1/powerhour/sessions/` | List user's sessions |
| GET | `/api/v1/powerhour/sessions/{id}/` | Session detail |
| PATCH | `/api/v1/powerhour/sessions/{id}/` | Update session config |
| DELETE | `/api/v1/powerhour/sessions/{id}/` | Delete session |
| POST | `/api/v1/powerhour/sessions/join/` | Join via invite code |
| POST | `/api/v1/powerhour/sessions/{id}/start/` | Start session |
| POST | `/api/v1/powerhour/sessions/{id}/pause/` | Pause session |
| POST | `/api/v1/powerhour/sessions/{id}/resume/` | Resume session |
| POST | `/api/v1/powerhour/sessions/{id}/end/` | End session |
| POST | `/api/v1/powerhour/sessions/{id}/next/` | Next track |
| GET | `/api/v1/powerhour/sessions/{id}/tracks/` | List tracks |
| POST | `/api/v1/powerhour/sessions/{id}/tracks/` | Add track |
| DELETE | `/api/v1/powerhour/sessions/{id}/tracks/{track_pk}/` | Remove track |
| POST | `/api/v1/powerhour/sessions/{id}/tracks/import-session/` | Import from session |
| GET | `/api/v1/powerhour/sessions/{id}/players/` | List players |
| DELETE | `/api/v1/powerhour/sessions/{id}/players/{player_pk}/` | Remove player |
| GET | `/api/v1/powerhour/sessions/{id}/state/` | Poll current state |

---

## 6. Domain Models

### Session
```
PowerHourSession:
  id: UUID
  title: String
  invite_code: String (8 chars)
  admin: User reference
  status: lobby | active | paused | ended
  tracks_per_player: Int (default 3)
  max_tracks: Int (default 30)
  seconds_per_track: Int (default 60)
  transition_clip: airhorn | buzzer | bell | whistle | glass_clink
  hide_track_owners: Boolean (default false)
  current_track_index: Int
  created_at, started_at, ended_at: timestamps
  player_count, track_count: computed
```

### SessionPlayer
```
  id: UUID
  user: { id, username, display_name }
  is_admin: Boolean
  joined_at: timestamp
```

### SessionTrack
```
  id: UUID
  track_id: Int
  track_name: String
  track_artist: String
  track_album: String
  duration_ms: Int
  spotify_id: String
  preview_url: String?
  order: Int
  start_offset_ms: Int
  added_by_username: String
  added_at: timestamp
```

---

## 7. Navigation Flow

```
App Launch
    |
    v
+------------------+    Not authenticated    +------------------+
| TuneTriviaApp     | ----------------------> |   AuthScreen     |
| (session gate)   |                         | Login / Register |
+--------+---------+                         +------------------+
         | Authenticated
         v
+------------------+
|   HomeScreen     |<--------------------------------------------+
| (my sessions +   |                                             |
|  join/create)    |                                             |
+--------+---------+                                             |
         |                                                       |
         +-- Create --> CreateSessionScreen --> Lobby             |
         +-- Join ----> JoinSessionScreen ----> Lobby             |
         +-- Tap -----> SessionLobbyScreen                       |
                            |                                    |
                            +-- Add Tracks --> AddTracksScreen   |
                            |   (search / import from session)   |
                            +-- Share -------> SMS Intent         |
                            +-- Start -------> PlaybackScreen    |
                            |                      |             |
                            |                      +-- End ----> |
                            |                  SessionEndScreen  |
                            +-- Share Playlist -> SMS Intent     |
```

### Screen Descriptions

1. **AuthScreen** - Login/register form (mirrors Juke app exactly). Toggle between modes. Registration respects `DISABLE_REGISTRATION` flag.

2. **HomeScreen** - Lists sessions the user has created or joined. Two bottom tabs: Sessions (list) and Profile. Top-level actions: "New Power Hour" and "Join with Code".

3. **CreateSessionScreen** - Form to configure a new session: title, tracks per player, max tracks, seconds per track, transition clip selection, hide track owners toggle.

4. **JoinSessionScreen** - Enter invite code to join an existing session. Validates code against backend.

5. **SessionLobbyScreen** - Displays session details: invite code (tap to copy), player list, track list with progress bar (N/max_tracks). Admin sees controls: Share, Add Tracks, Start. Non-admin sees: Add Tracks, waiting state.

6. **AddTracksScreen** - Two tabs: "Search" (search catalog) and "Import" (copy from previous session). Search results show track name, artist, duration with add/remove buttons. Enforces tracks_per_player limit client-side.

7. **PlaybackScreen** - Countdown ring (seconds remaining), current track info (name, artist, track number), playback controls (pause/resume, skip, end). Admin-only controls. Polls session state every 3 seconds.

8. **SessionEndScreen** - Summary: total tracks played, session duration, player list. "Share Playlist" button generates SMS template. "Back to Sessions" returns to HomeScreen.

9. **ProfileScreen** - Current user's music profile (display name, favorite genres/artists, etc.). Mirrors Juke app profile screen.

---

## 8. Key Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| UI Framework | Jetpack Compose + Material3 | Matches Juke Android app |
| State Management | `mutableStateOf` + `StateFlow` | Same pattern as Juke |
| DI | ServiceLocator singleton | Same pattern as Juke (no Hilt/Dagger) |
| Networking | Retrofit + kotlinx.serialization | Same as Juke |
| Token Storage | DataStore Preferences | Same as Juke |
| Audio Playback | Android MediaPlayer | Built-in, handles short transition clips |
| Real-time Sync | Polling (3s interval when active) | Simple, no WebSocket infra needed |
| SMS Sharing | `Intent.ACTION_SENDTO` | Standard Android SMS intent |
| Navigation | Session-state-driven composable | Same pattern as Juke (sealed interface) |
| Package | `fm.tunetrivia.mobile` | Matches Juke convention (fm.*.mobile) |
| App ID | `fm.tunetrivia.mobile` | Unique Play Store identifier |

---

## 9. Design System

The Android app must be a pixel-accurate port of the existing iOS TuneTrivia app (`mobile/ios/tunetrivia/`). The iOS app uses the **"Neon Night"** palette and component library defined in `TuneTriviaDesignSystem.swift`. Every color, spacing value, corner radius, shadow, animation, and component behavior specified below is taken directly from the iOS implementation and must be reproduced in Compose.

### 9.1 Color Palette (`SCPalette` / `TuneTriviaPalette`)

| Token | Hex | Usage |
|-------|-----|-------|
| `Background` | `#0A0118` | App background, scaffold |
| `Panel` | `#140B2E` | Card backgrounds, surfaces |
| `PanelAlt` | `#1E1145` | Elevated surfaces, input fills |
| `Accent` | `#E11D89` | Primary actions, active states, neon glow |
| `AccentSoft` | `#F472B6` | Gradient endpoints, subtle highlights |
| `Secondary` | `#06B6D4` | Countdown ring, lobby status, secondary actions |
| `Text` | `#F8FAFC` | Primary text |
| `Muted` | `#94A3B8` | Secondary text, placeholders, labels |
| `Border` | `#FFFFFF` @ 6% opacity | Card/input/chip borders |
| `Success` | `#10B981` | Success banners, active session status |
| `Warning` | `#FBBF24` | Warning banners, paused session status |
| `Error` | `#F43F5E` | Error banners, destructive actions |

### 9.2 Typography

Map iOS system fonts to Android equivalents using `FontFamily.SansSerif`:

| Style | iOS Equivalent | Size | Weight |
|-------|---------------|------|--------|
| Display | `.system(size: 36)` | 36sp | Bold |
| Title | `.system(size: 24)` | 24sp | Bold |
| Title2 | `.title2` | 22sp | Bold |
| Title3 | `.title3` | 20sp | Bold |
| Headline | `.headline` | 17sp | SemiBold |
| Subheadline | `.subheadline` | 15sp | Regular |
| Body | `.body` | 17sp | Regular |
| Footnote | `.footnote` | 13sp | Regular |
| Caption | `.caption` | 12sp | Regular |
| Caption2 | `.caption2` | 11sp | Regular |
| Monospaced (invite codes) | `.system(size: 32, .monospaced)` | 32sp | Bold, Monospace |
| Input labels | `.caption` uppercase | 12sp | Regular, kerning 1.2, uppercase |

### 9.3 Spacing Scale

All spacing is based on a 4dp base unit, matching the iOS point values 1:1:

| Token | Value | Usage |
|-------|-------|-------|
| xs | 4dp | Tight text spacing |
| sm | 8dp | Chip horizontal padding, tight gaps |
| md | 12dp | Banner padding vertical, card gaps, status dot spacing |
| std | 16dp | Input padding, button vertical padding, standard gaps |
| lg | 20dp | Card inner padding (default), button horizontal padding |
| xl | 24dp | Screen horizontal padding, content group spacing |
| xxl | 32dp | Large section spacing, playback bottom padding |

### 9.4 Corner Radius

| Element | Radius | Style |
|---------|--------|-------|
| Cards & containers | 16dp | `RoundedCornerShape` (smooth) |
| Buttons (primary/ghost/destructive) | 16dp | `RoundedCornerShape` |
| Input fields | 14dp | `RoundedCornerShape` |
| Search result rows | 12dp | `RoundedCornerShape` |
| Status banners | 14dp | `RoundedCornerShape` |
| Chips | Fully rounded | `CircleShape` / `RoundedCornerShape(50%)` |
| Explicit badge | 3dp | `RoundedCornerShape` |

### 9.5 Borders & Strokes

- **Width**: 1dp (matching iOS `lineWidth: 1`)
- **Default color**: `SCPalette.Border` (white @ 6% opacity)
- **Error state**: `SCPalette.Error`
- Applied to: cards, input fields, ghost buttons, search rows, chips

### 9.6 Shadows

| Element | Color | Radius | Y Offset |
|---------|-------|--------|----------|
| Cards | `Black @ 40%` | 20dp | 12dp |
| Neon glow (layer 1) | `accent @ 50%` | 8dp | 0dp |
| Neon glow (layer 2) | `accent @ 20%` | 16dp | 0dp |
| Status dot glow | `variant color @ 60%` | 6dp | 0dp |

### 9.7 Background (`SCBackground` / `TuneTriviaBackground`)

Three-layer gradient stack matching iOS `SCBackground`:

1. **Base**: `LinearGradient` from `Background` to `Panel`, top to bottom
2. **Accent glow**: `RadialGradient` of `Accent @ 20%` centered at top-leading, radius 350dp
3. **Secondary glow**: `RadialGradient` of `Secondary @ 15%` centered at bottom-trailing, radius 400dp

All layers fill the entire screen and ignore safe area (edge-to-edge on Android).

### 9.8 Component Specifications

#### `TuneTriviaButton` (4 variants, matching iOS `SCButtonStyle`)

| Variant | Background | Foreground | Border |
|---------|-----------|------------|--------|
| PRIMARY | LinearGradient `Accent` to `AccentSoft` (leading→trailing) | White | None |
| SECONDARY | Solid `Secondary` | `Background` color | None |
| GHOST | `PanelAlt @ 50%` | `Text` | 1dp `Border` |
| DESTRUCTIVE | Solid `Error` | White | None |

- Padding: 16dp vertical, 20dp horizontal
- Font: Headline weight
- Press animation: 0.12s easeInOut, brightness -0.05, scale 0.98, opacity 0.85
- Corner radius: 16dp

#### `TuneTriviaInputField` (matching iOS `SCInputField`)

- Label: uppercase, caption size, `Muted` color, 1.2 letter spacing
- Background: `PanelAlt @ 65%`
- Border: 1dp (`Border` normal, `Error` on error state)
- Corner radius: 14dp
- Padding: 14dp vertical, 16dp horizontal
- Text color: `Text`
- Error text: footnote size, `Error` color

#### `TuneTriviaCard` (matching iOS `SCCard`)

- Padding: 20dp (default)
- Background: LinearGradient from `Panel @ 95%` to `PanelAlt @ 90%`, topLeading→bottomTrailing
- Border: 1dp `Border`
- Corner radius: 16dp
- Shadow: black @ 40%, radius 20dp, y-offset 12dp
- Max width: fill, alignment: leading

#### `TuneTriviaChip` (matching iOS `SCChip`)

- Shape: fully rounded (capsule)
- Padding: 8dp vertical, 16dp horizontal
- Font: subheadline
- **Selected**: background `color @ 20%`, border 1dp `color`, text `Text` + semibold
- **Unselected**: background transparent, border 1dp `Border`, text `Muted` + regular

#### `TuneTriviaSpinner` (matching iOS `SCSpinner`)

- 3 circles, 10dp each, 8dp gap
- Color: `Accent`
- Animation: scale 1→0.5, opacity 1→0.3, duration 0.7s, stagger 0.15s per dot

#### `TuneTriviaStatusBanner` (4 variants matching iOS `SCStatusBanner`)

- Variants: INFO (`Accent`), SUCCESS (`Success`), WARNING (`Warning`), ERROR (`Error`)
- Status dot: 10dp circle with glow shadow (color @ 60%, radius 6dp)
- Message: subheadline, `Text` color
- Background: variant color @ 12-18%
- Border: 1dp, variant color @ 30%
- Corner radius: 14dp
- Padding: 12dp vertical, 16dp horizontal

#### `CountdownRing` (matching iOS `SCCountdownRing`)

- Default size: 200dp x 200dp
- Line width: 20dp (16dp on playback screen)
- Background track: `PanelAlt` stroke
- Progress arc: AngularGradient from `Secondary` to `Accent`
- Glow ring: `Secondary @ 30%`, lineWidth + 8dp, blur 4dp
- Rotation: -90 degrees (12 o'clock start)
- Animation: linear 1s

#### Neon Glow Effect (matching iOS `NeonGlow` modifier)

Applied to accent-colored text (e.g., "TuneTrivia" logo):
- Shadow 1: `color @ 50%`, radius 8dp
- Shadow 2: `color @ 20%`, radius 16dp

### 9.9 Screen-Specific Layout (matching iOS views)

#### AuthScreen (matches `AuthView.swift`)
- Logo: "TuneTrivia" 36sp bold with neon glow in `Accent`
- Tagline: "Power Hour, powered up." in `Muted`
- Card with chip toggle (Login/Register), input fields, status banners, submit button
- Horizontal padding: 24dp

#### HomeScreen (matches `HomeView.swift`)
- Header: "TuneTrivia" 24sp bold with neon glow + greeting text
- Logout button top-right in `Accent`
- Action row: "New Session" (PRIMARY) + "Join" (SECONDARY)
- Session list with 12dp gaps
- Session cards: status dot (10dp, color by status), title (headline), stats (caption, muted), chevron
- Status colors: `Secondary`=lobby, `Success`=active, `Warning`=paused, `Muted`=ended
- Pull-to-refresh
- Join sheet as bottom modal with invite code input

#### CreateSessionScreen (matches `CreateSessionView.swift`)
- Title input field
- Sliders: tracks per player (1-10, default 3), max tracks (10-60, default 30, step 5), seconds per track (30-120, default 60, step 10)
- Transition sound chips in flow layout (8dp spacing): airhorn, buzzer, bell, whistle, glass_clink
- Trivia mode toggle
- Create button (PRIMARY)

#### SessionLobbyScreen (matches `SessionLobbyView.swift`)
- Invite code card: large monospaced text, copy button
- Config badges: 3-column layout (music note, person group, numbered list icons)
- Players section: list with admin crown icon, player initials
- Tracks section: numbered list with TrackRow component
- Add Tracks button (SECONDARY)
- Start button (conditional, disabled if no tracks)

#### PlaybackScreen (matches `PlaybackView.swift`)
- Track progress: "Track X of Y" top
- CountdownRing: 220dp size, 16dp line width, timer text 48sp bold monospaced
- Current track: name (title3 bold), artist (subheadline muted)
- Controls: Pause (64x64dp), Skip (56x56dp), End (56x56dp)
- Bottom spacing: 32dp
- Ended overlay: checkmark 72dp in `Success`, "Power Hour Complete!", Done button

#### AddTracksScreen (matches `AddTracksView.swift`)
- Search bar with magnifying glass icon and clear button
- Search result rows: track name + explicit badge, artist + album, duration, add button
- Row styling: `Panel @ 60%` background, 1dp border, 12dp radius, 10dp/14dp padding
- Explicit badge: "E" 9sp bold, `Muted` background, 3dp radius

### 9.10 Animations

| Animation | Duration | Curve | Properties |
|-----------|----------|-------|------------|
| Button press | 0.12s | easeInOut | opacity→0.85, scale→0.98 |
| Spinner dots | 0.7s | linear | scale 1→0.5, opacity 1→0.3, stagger 0.15s |
| Countdown ring | 1s | linear | trim progress |
| Tab/chip changes | default | default | state transition |

---

## 10. Feature Implementation Order

| # | Feature | Scope |
|---|---------|-------|
| 1 | Project scaffolding + design system | Gradle config, theme, palette, reusable components |
| 2 | Authentication | Login/register/logout with token persistence |
| 3 | Home screen + session list | Bottom-tab navigation, session cards, empty state |
| 4 | Create session | Configuration form with validation |
| 5 | Join session | Invite code entry and validation |
| 6 | Session lobby | Players list, tracks list, invite code display, share |
| 7 | Add/remove tracks | Catalog search, import from previous session |
| 8 | Share session invite | SMS intent with invite code template |
| 9 | Playback controls | Start/pause/resume/end/next with countdown ring |
| 10 | Session end + share playlist | Summary screen, SMS playlist share |
| 11 | Profile screen | User profile display |
| 12 | App icons + brand assets | Selected design rendered to mipmap densities |

---

## 11. Security Considerations

- All API calls require valid Token authentication (`Authorization: Token <key>`)
- Session modifications restricted to admin via backend permission checks
- Invite codes are 8-char alphanumeric, randomly generated server-side
- Track additions rate-limited by tracks_per_player (server-enforced)
- Max track limits enforced server-side; client shows progress
- Input validation on all forms (min lengths, required fields)
- Cleartext traffic allowed only for development (`usesCleartextTraffic=true`)
- `allowBackup=false` prevents data extraction
- No secrets stored in source code; BACKEND_URL injected via BuildConfig

---

## 12. Error Handling Strategy

- Network errors surfaced via `humanReadableMessage()` extension on Throwable
- Repository methods return `Result<T>` for explicit success/failure handling
- ViewModels expose `error: String?` in UI state for banner display
- HTTP 401 triggers automatic session invalidation and redirect to login
- HTTP 403 on session actions shows "admin required" message
- HTTP 404 on join shows "invalid invite code" message
- Offline state detected and shown via status banner

---

## 13. Build & Deployment

- **Build Script**: `scripts/build_and_run_android.sh -p tunetrivia`
- **App ID**: `fm.tunetrivia.mobile`
- **Scheme**: TuneTrivia
- **Emulator**: API 36 Google APIs arm64, Pixel 7 profile
- **Tests**: `./gradlew :app:testDebugUnitTest` (unit), `./gradlew :app:connectedDebugAndroidTest` (instrumented)
- **Icon Pipeline**: SVG from branding/tunetrivia/ rendered via scripts/render_icons.cjs into mipmap densities
