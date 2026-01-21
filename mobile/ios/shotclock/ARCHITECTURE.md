# ShotClock - Power Hour iOS App Architecture

## 1. Overview

**ShotClock** is a native iOS app that enables users to create and participate in Power Hour drinking game sessions. A Power Hour involves a shared playlist where a random 60-second (configurable) segment of each track plays before a transition audio clip signals players to drink and guess whose song it is.

The app integrates with the existing Juke backend platform for authentication, Spotify account linking, and music catalog access.

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────┐
│                   ShotClock iOS App                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────────────────┐  │
│  │   Views   │  │ ViewModels│  │     Services         │  │
│  │ (SwiftUI) │──│  (MVVM)  │──│ (API, Audio, Share)  │  │
│  └──────────┘  └──────────┘  └──────────────────────┘  │
│                                        │                 │
│  ┌──────────────────────────────────────┐               │
│  │         APIClient (HTTP/Token)        │               │
│  └──────────────────────────────────────┘               │
└──────────────────────────────────────┬──────────────────┘
                                       │ HTTPS
┌──────────────────────────────────────┴──────────────────┐
│                  Juke Backend (Django)                    │
│  ┌───────────┐  ┌──────────┐  ┌─────────────────────┐  │
│  │ juke_auth │  │  catalog  │  │    powerhour (NEW)   │  │
│  │ (users,   │  │ (tracks,  │  │ (sessions, players, │  │
│  │  profiles)│  │  search)  │  │  playlists, config)  │  │
│  └───────────┘  └──────────┘  └─────────────────────┘  │
│                       │                                  │
│  ┌────────────────────┴─────────────────────────────┐   │
│  │         Spotify Web API / Playback SDK            │   │
│  └──────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────┘
```

---

## 3. Backend Extension: `powerhour` Django App

### 3.1 New Models

```python
# backend/powerhour/models.py

class PowerHourSession(models.Model):
    """A Power Hour game session created by an admin user."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    admin = models.ForeignKey(JukeUser, on_delete=models.CASCADE, related_name='hosted_sessions')
    title = models.CharField(max_length=200)
    invite_code = models.CharField(max_length=8, unique=True)  # Short shareable code

    # Configuration
    tracks_per_player = models.PositiveIntegerField(default=3)
    max_tracks = models.PositiveIntegerField(default=30)
    seconds_per_track = models.PositiveIntegerField(default=60)
    transition_clip = models.CharField(max_length=50, default='airhorn')  # preset key
    hide_track_owners = models.BooleanField(default=False)  # trivia mode

    # State
    status = models.CharField(max_length=20, choices=[
        ('lobby', 'Lobby'),
        ('active', 'Active'),
        ('paused', 'Paused'),
        ('ended', 'Ended'),
    ], default='lobby')
    current_track_index = models.IntegerField(default=-1)

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)


class SessionPlayer(models.Model):
    """A participant in a Power Hour session."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    session = models.ForeignKey(PowerHourSession, on_delete=models.CASCADE, related_name='players')
    user = models.ForeignKey(JukeUser, on_delete=models.CASCADE, related_name='session_memberships')
    joined_at = models.DateTimeField(auto_now_add=True)
    is_admin = models.BooleanField(default=False)

    class Meta:
        unique_together = ('session', 'user')


class SessionTrack(models.Model):
    """A track added to a Power Hour session playlist."""
    id = models.UUIDField(primary_key=True, default=uuid.uuid4)
    session = models.ForeignKey(PowerHourSession, on_delete=models.CASCADE, related_name='tracks')
    added_by = models.ForeignKey(JukeUser, on_delete=models.CASCADE)
    track = models.ForeignKey('catalog.Track', on_delete=models.CASCADE)

    order = models.PositiveIntegerField()
    start_offset_ms = models.PositiveIntegerField(default=0)

    added_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('session', 'track')
        ordering = ['order']
```

### 3.2 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/api/v1/powerhour/sessions/` | Create a new session |
| GET | `/api/v1/powerhour/sessions/` | List user's sessions (hosted + joined) |
| GET | `/api/v1/powerhour/sessions/{id}/` | Get session details |
| PATCH | `/api/v1/powerhour/sessions/{id}/` | Update session config (admin only) |
| DELETE | `/api/v1/powerhour/sessions/{id}/` | Delete session (admin only) |
| POST | `/api/v1/powerhour/sessions/join/` | Join via invite code |
| POST | `/api/v1/powerhour/sessions/{id}/start/` | Start playback (admin) |
| POST | `/api/v1/powerhour/sessions/{id}/pause/` | Pause playback (admin) |
| POST | `/api/v1/powerhour/sessions/{id}/resume/` | Resume playback (admin) |
| POST | `/api/v1/powerhour/sessions/{id}/end/` | End session (admin) |
| POST | `/api/v1/powerhour/sessions/{id}/next/` | Skip to next track (admin) |
| GET | `/api/v1/powerhour/sessions/{id}/tracks/` | List session tracks |
| POST | `/api/v1/powerhour/sessions/{id}/tracks/` | Add track(s) |
| DELETE | `/api/v1/powerhour/sessions/{id}/tracks/{track_id}/` | Remove track |
| POST | `/api/v1/powerhour/sessions/{id}/tracks/import-session/` | Copy tracks from a previous session |
| POST | `/api/v1/powerhour/sessions/{id}/tracks/import-playlist/` | Import tracks from a Spotify playlist |
| GET | `/api/v1/powerhour/sessions/{id}/players/` | List players |
| DELETE | `/api/v1/powerhour/sessions/{id}/players/{player_id}/` | Remove player (admin) |
| GET | `/api/v1/powerhour/sessions/{id}/state/` | Real-time state polling |

### 3.3 Transition Audio Clips (Bundled Presets)

- `airhorn` - Classic air horn blast
- `buzzer` - Game show buzzer
- `bell` - Boxing ring bell
- `whistle` - Referee whistle
- `glass_clink` - Glass clinking sound

---

## 4. iOS App Architecture

### 4.1 Project Structure

```
mobile/ios/shotclock/
├── ShotClock.xcodeproj/
├── ShotClock/
│   ├── ShotClockApp.swift              # @main entry point
│   ├── ContentView.swift               # Root navigation (auth gate)
│   ├── Info.plist
│   │
│   ├── Networking/
│   │   └── APIClient.swift             # Shared HTTP client (mirrors juke)
│   │
│   ├── Models/
│   │   ├── User.swift                  # User & MusicProfile models
│   │   ├── Session.swift               # PowerHourSession model
│   │   ├── SessionTrack.swift          # Track in session context
│   │   ├── SessionPlayer.swift         # Player model
│   │   └── CatalogModels.swift         # Track, Artist, Album for search
│   │
│   ├── Services/
│   │   ├── AuthService.swift           # Login/register/logout
│   │   ├── ProfileService.swift        # Profile fetch
│   │   ├── SessionService.swift        # CRUD for Power Hour sessions
│   │   ├── CatalogService.swift        # Track search
│   │   └── ShareService.swift          # SMS/share sheet integration
│   │
│   ├── ViewModels/
│   │   ├── SessionStore.swift          # Auth state (token, profile)
│   │   ├── AuthViewModel.swift         # Login/register form
│   │   ├── HomeViewModel.swift         # Session list
│   │   ├── CreateSessionViewModel.swift
│   │   ├── SessionLobbyViewModel.swift
│   │   ├── AddTracksViewModel.swift
│   │   └── PlaybackViewModel.swift
│   │
│   ├── Views/
│   │   ├── Auth/
│   │   │   └── AuthView.swift
│   │   ├── Home/
│   │   │   └── HomeView.swift
│   │   ├── Session/
│   │   │   ├── CreateSessionView.swift
│   │   │   ├── SessionLobbyView.swift
│   │   │   ├── AddTracksView.swift
│   │   │   ├── PlaybackView.swift
│   │   │   └── SessionEndView.swift
│   │   └── Components/
│   │       ├── TrackRow.swift
│   │       ├── PlayerChip.swift
│   │       └── CountdownRing.swift
│   │
│   ├── DesignSystem/
│   │   └── ShotClockDesignSystem.swift
│   │
│   ├── Resources/
│   │   └── TransitionClips/
│   │       ├── airhorn.mp3
│   │       ├── buzzer.mp3
│   │       ├── bell.mp3
│   │       ├── whistle.mp3
│   │       └── glass_clink.mp3
│   │
│   ├── BrandAssets/
│   │   ├── icon_export.json
│   │   └── AppIcon.appiconset/
│   │
│   ├── Assets.xcassets/
│   └── Preview Content/
│
├── ShotClockTests/
│   ├── Services/
│   ├── ViewModels/
│   └── Mocks/
│       └── MockAPIClient.swift
│
└── ShotClockUITests/
    └── ShotClockUITests.swift
```

### 4.2 Navigation Flow

```
App Launch
    │
    ▼
┌──────────────┐     Not authenticated      ┌──────────────┐
│ ContentView  │ ──────────────────────────► │   AuthView   │
│ (auth gate)  │                             │ Login/Register│
└──────┬───────┘                             └──────────────┘
       │ Authenticated
       ▼
┌──────────────┐
│   HomeView   │◄──────────────────────────────────────┐
│ (my sessions)│                                        │
└──────┬───────┘                                        │
       │                                                │
       ├── Create ──► CreateSessionView ──► Lobby       │
       ├── Join ────► (enter code) ──────► Lobby        │
       └── Tap ────► SessionLobbyView                   │
                         │                              │
                         ├── Add Tracks ► AddTracksView  │
                         │   (search / import session /  │
                         │    import Spotify playlist)   │
                         ├── Share ─────► SMS Sheet     │
                         ├── Start ─────► PlaybackView  │
                         │                    │         │
                         │                    └─ End ──►│
                         │                     SessionEndView
                         └── Share Playlist ► SMS Sheet
```

### 4.3 Key Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| UI Framework | SwiftUI | Matches existing Juke iOS app pattern |
| State Management | `@StateObject` + `@EnvironmentObject` | Matches Juke, minimal dependencies |
| Networking | URLSession via shared `APIClient` | Same pattern, no external deps |
| Audio Playback | AVFoundation (`AVAudioPlayer`) | Built-in, handles short clips |
| Real-time Sync | Polling (5s interval when active) | Simple, no WebSocket infra needed |
| Token Storage | UserDefaults | Matches Juke (Keychain for production) |
| SMS Sharing | `MFMessageComposeViewController` | Native iOS SMS composition |
| Navigation | `NavigationStack` (iOS 16+) | Modern SwiftUI navigation |
| Min iOS | 16.0 | NavigationStack requirement |
| Target Devices | iPhone 17 Air/Pro/Max | Latest generation |

---

## 5. Feature Implementation Order

| # | Feature | Description |
|---|---------|-------------|
| 1 | Project scaffolding + design system | Xcode project, palette, reusable components |
| 2 | Authentication | Login/register/logout matching Juke flows |
| 3 | Home screen | Session list with create/join entry points |
| 4 | Create session | Configuration form (tracks, timing, clip) |
| 5 | Join session | Invite code entry and validation |
| 6 | Session lobby | Players list, tracks list, real-time updates |
| 7 | Add/remove tracks | Search via catalog, import from previous session or Spotify playlist |
| 8 | Share session invite | SMS template with invite code |
| 9 | Playback controls | Start/pause/end with countdown timer |
| 10 | Share playlist | Post-game SMS with track list |
| 11 | App icons + brand assets | SVG → render pipeline → .appiconset |

---

## 6. Security Considerations

- All endpoints require valid Token authentication
- Session modifications restricted to admin via custom `IsSessionAdmin` permission
- Invite codes are 8-char alphanumeric, randomly generated
- Track additions rate-limited server-side
- Max track limits enforced server-side
- Input validation on all user-facing forms

---

## 7. Build & Deployment

- **Build Script**: `scripts/build_and_run_ios.sh` with `IOS_PROJECT_NAME=shotclock`
- **Bundle ID**: `embario.ShotClock`
- **Scheme**: `ShotClock`
- **Icon Pipeline**: SVG → `scripts/render_icons.cjs` → BrandAssets/AppIcon.appiconset/
- **Simulator**: iPhone 17 Pro (default target)
