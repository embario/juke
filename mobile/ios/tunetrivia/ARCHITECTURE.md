# TuneTrivia - Name That Tune iOS App Architecture

## 1. Overview

**TuneTrivia** is a native iOS app that enables users to host and participate in "Name That Tune" music trivia game sessions. Players listen to song clips and compete to correctly guess the artist and song title. The app supports two distinct game modes:

1. **Host Mode**: A single host/scribe manages the session, manually inputting player answers and tracking scores
2. **Party Mode**: Players join via invite code and submit their own answers in real-time

The app integrates with the existing Juke backend platform for authentication, Spotify account linking, music catalog access, and playback control. Optional AI-powered trivia questions add an extra layer of fun and bonus points.

---

## 2. System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                      TuneTrivia iOS App                              │
│  ┌──────────────┐  ┌──────────────┐  ┌─────────────────────────┐   │
│  │    Views     │  │  ViewModels  │  │       Services          │   │
│  │  (SwiftUI)   │──│   (MVVM)     │──│ (API, Audio, Scoring)   │   │
│  └──────────────┘  └──────────────┘  └─────────────────────────┘   │
│                                              │                       │
│  ┌───────────────────────────────────────────┐                      │
│  │          APIClient (HTTP/Token)           │                      │
│  └───────────────────────────────────────────┘                      │
└─────────────────────────────────┬───────────────────────────────────┘
                                  │ HTTPS
┌─────────────────────────────────┴───────────────────────────────────┐
│                      Juke Backend (Django)                           │
│  ┌───────────┐  ┌──────────┐  ┌─────────────────────────────────┐  │
│  │ juke_auth │  │  catalog │  │         tunetrivia (NEW)           │  │
│  │  (users,  │  │ (tracks, │  │  (sessions, players, rounds,    │  │
│  │ profiles) │  │  search) │  │   guesses, trivia, leaderboard) │  │
│  └───────────┘  └──────────┘  └─────────────────────────────────┘  │
│                       │                      │                       │
│  ┌────────────────────┴──────────────────────┴──────────────────┐   │
│  │         Spotify Web API / Playback SDK                        │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                               │                                      │
│  ┌────────────────────────────┴─────────────────────────────────┐   │
│  │              OpenAI API (ChatGPT for Trivia)                  │   │
│  └──────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 3. Backend Extension: `tunetrivia` Django App

### 3.1 New Models

```python
# backend/tunetrivia/models.py

import uuid
import string
import random
from django.conf import settings
from django.db import models


def generate_invite_code():
    chars = string.ascii_uppercase + string.digits
    return ''.join(random.choices(chars, k=6))


class TuneTriviaSession(models.Model):
    """A Name That Tune game session created by a host."""

    MODE_CHOICES = [
        ('host', 'Host Mode'),      # Host manually scores players
        ('party', 'Party Mode'),    # Players submit their own answers
    ]

    STATUS_CHOICES = [
        ('lobby', 'Lobby'),         # Waiting for players, configuring
        ('active', 'Active'),       # Game in progress
        ('paused', 'Paused'),       # Temporarily stopped
        ('ended', 'Ended'),         # Game complete
    ]

    DECADE_CHOICES = [
        ('60s', '1960s'),
        ('70s', '1970s'),
        ('80s', '1980s'),
        ('90s', '1990s'),
        ('00s', '2000s'),
        ('10s', '2010s'),
        ('20s', '2020s'),
        ('mix', 'Mixed'),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    host = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='hosted_tunetrivia_sessions',
    )
    title = models.CharField(max_length=200)
    invite_code = models.CharField(max_length=6, unique=True, default=generate_invite_code)

    # Game Mode
    mode = models.CharField(max_length=20, choices=MODE_CHOICES, default='party')

    # Configuration
    num_songs = models.PositiveIntegerField(default=10)              # 5-50 songs
    seconds_per_song = models.PositiveIntegerField(default=30)       # 10-30 seconds (uses Spotify preview)
    trivia_enabled = models.BooleanField(default=False)              # ChatGPT trivia (shown after reveal)

    # Auto-selection criteria (optional - if null, host selects manually)
    auto_select = models.BooleanField(default=False)
    decade = models.CharField(max_length=10, choices=DECADE_CHOICES, null=True, blank=True)
    genre = models.CharField(max_length=100, null=True, blank=True)  # e.g., "rock,pop"
    artists = models.JSONField(default=list, blank=True)             # e.g., ["spotify_id_1", ...]

    # Scoring Configuration
    points_artist = models.PositiveIntegerField(default=1)           # Points for correct artist
    points_song = models.PositiveIntegerField(default=1)             # Points for correct song title
    points_trivia = models.PositiveIntegerField(default=1)           # Points for trivia question

    # State
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='lobby')
    current_round = models.PositiveIntegerField(default=0)           # 0 = not started

    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(null=True, blank=True)
    ended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'TuneTrivia Session'
        verbose_name_plural = 'TuneTrivia Sessions'

    def __str__(self):
        return f"{self.title} ({self.invite_code})"


class TuneTriviaPlayer(models.Model):
    """A participant in a TuneTrivia session."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        TuneTriviaSession,
        on_delete=models.CASCADE,
        related_name='players',
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='tunetrivia_memberships',
        null=True,       # Null for Host Mode manual players (no account)
        blank=True,
    )
    display_name = models.CharField(max_length=50)                   # For Host Mode manual players
    is_host = models.BooleanField(default=False)
    is_manual = models.BooleanField(default=False)                   # True for Host Mode players (no leaderboard)

    # Aggregate scores (denormalized for leaderboard efficiency)
    total_score = models.PositiveIntegerField(default=0)
    correct_artists = models.PositiveIntegerField(default=0)
    correct_songs = models.PositiveIntegerField(default=0)
    correct_trivia = models.PositiveIntegerField(default=0)

    joined_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('session', 'user')
        ordering = ['-total_score', 'joined_at']

    def __str__(self):
        return f"{self.display_name} in {self.session.title}"


class TuneTriviaRound(models.Model):
    """A single round/song in a TuneTrivia session."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    session = models.ForeignKey(
        TuneTriviaSession,
        on_delete=models.CASCADE,
        related_name='rounds',
    )
    track = models.ForeignKey(
        'catalog.Track',
        on_delete=models.CASCADE,
    )
    round_number = models.PositiveIntegerField()                     # 1-indexed
    preview_url = models.URLField(null=True, blank=True)             # Spotify 30-sec preview URL

    # Trivia (if enabled) - shown AFTER song/artist reveal as bonus round
    trivia_question = models.TextField(null=True, blank=True)
    trivia_answer = models.CharField(max_length=255, null=True, blank=True)
    trivia_options = models.JSONField(default=list, blank=True)      # Multiple choice options

    # State
    is_revealed = models.BooleanField(default=False)                 # Answer revealed to players
    trivia_revealed = models.BooleanField(default=False)             # Trivia answer revealed
    played_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        unique_together = ('session', 'round_number')
        ordering = ['round_number']

    def __str__(self):
        return f"Round {self.round_number}: {self.track.name}"


class TuneTriviaGuess(models.Model):
    """A player's guess for a round (Party Mode only)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    round = models.ForeignKey(
        TuneTriviaRound,
        on_delete=models.CASCADE,
        related_name='guesses',
    )
    player = models.ForeignKey(
        TuneTriviaPlayer,
        on_delete=models.CASCADE,
        related_name='guesses',
    )

    # Guesses
    artist_guess = models.CharField(max_length=255, blank=True)
    song_guess = models.CharField(max_length=255, blank=True)
    trivia_guess = models.CharField(max_length=255, blank=True)

    # Scoring (computed after reveal)
    artist_correct = models.BooleanField(default=False)
    song_correct = models.BooleanField(default=False)
    trivia_correct = models.BooleanField(default=False)
    points_earned = models.PositiveIntegerField(default=0)

    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ('round', 'player')
        ordering = ['submitted_at']

    def __str__(self):
        return f"{self.player.display_name}'s guess for Round {self.round.round_number}"


class GlobalLeaderboard(models.Model):
    """
    Aggregated stats for global leaderboard (updated after each session).
    Only includes registered Juke users (Party Mode players).
    Host Mode manual players (is_manual=True) do NOT count toward leaderboard.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        primary_key=True,
        related_name='tunetrivia_leaderboard',
    )
    games_played = models.PositiveIntegerField(default=0)
    total_points = models.PositiveIntegerField(default=0)
    total_artist_correct = models.PositiveIntegerField(default=0)
    total_song_correct = models.PositiveIntegerField(default=0)
    total_trivia_correct = models.PositiveIntegerField(default=0)
    highest_game_score = models.PositiveIntegerField(default=0)

    last_played = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-total_points', '-games_played']

    def __str__(self):
        return f"{self.user.username}: {self.total_points} pts"
```

### 3.2 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| **Sessions** | | |
| POST | `/api/v1/tunetrivia/sessions/` | Create a new session |
| GET | `/api/v1/tunetrivia/sessions/` | List user's sessions (hosted + joined) |
| GET | `/api/v1/tunetrivia/sessions/{id}/` | Get session details |
| PATCH | `/api/v1/tunetrivia/sessions/{id}/` | Update session config (host only) |
| DELETE | `/api/v1/tunetrivia/sessions/{id}/` | Delete session (host only) |
| POST | `/api/v1/tunetrivia/sessions/join/` | Join via invite code (Party Mode) |
| **Game Control** | | |
| POST | `/api/v1/tunetrivia/sessions/{id}/start/` | Start game (host only) |
| POST | `/api/v1/tunetrivia/sessions/{id}/pause/` | Pause game (host only) |
| POST | `/api/v1/tunetrivia/sessions/{id}/resume/` | Resume game (host only) |
| POST | `/api/v1/tunetrivia/sessions/{id}/end/` | End game early (host only) |
| POST | `/api/v1/tunetrivia/sessions/{id}/next-round/` | Advance to next round (host only) |
| POST | `/api/v1/tunetrivia/sessions/{id}/reveal/` | Reveal answer for current round |
| **Rounds & Tracks** | | |
| GET | `/api/v1/tunetrivia/sessions/{id}/rounds/` | List session rounds |
| POST | `/api/v1/tunetrivia/sessions/{id}/rounds/` | Add round/track (manual selection) |
| DELETE | `/api/v1/tunetrivia/sessions/{id}/rounds/{round_id}/` | Remove round |
| POST | `/api/v1/tunetrivia/sessions/{id}/rounds/auto-generate/` | Auto-generate rounds based on criteria |
| POST | `/api/v1/tunetrivia/sessions/{id}/rounds/{round_id}/trivia/` | Generate trivia for round (ChatGPT) |
| **Players** | | |
| GET | `/api/v1/tunetrivia/sessions/{id}/players/` | List players and scores |
| POST | `/api/v1/tunetrivia/sessions/{id}/players/` | Add manual player (Host Mode) |
| DELETE | `/api/v1/tunetrivia/sessions/{id}/players/{player_id}/` | Remove player (host only) |
| **Guessing & Scoring** | | |
| POST | `/api/v1/tunetrivia/sessions/{id}/guess/` | Submit guess (Party Mode) |
| POST | `/api/v1/tunetrivia/sessions/{id}/score/` | Manual score entry (Host Mode) |
| GET | `/api/v1/tunetrivia/sessions/{id}/scoreboard/` | Get current scoreboard |
| **Leaderboard** | | |
| GET | `/api/v1/tunetrivia/leaderboard/` | Global leaderboard (paginated) |
| GET | `/api/v1/tunetrivia/leaderboard/me/` | Current user's rank and stats |
| **State** | | |
| GET | `/api/v1/tunetrivia/sessions/{id}/state/` | Real-time state polling |

### 3.3 Trivia Generation (ChatGPT Integration)

The trivia feature uses OpenAI's ChatGPT API to generate fun music-related questions for each song.

```python
# backend/tunetrivia/services/trivia.py

TRIVIA_PROMPT = """
Generate a fun music trivia question about the song "{song_title}" by {artist_name}.
The question should be about one of the following:
- The year the song was released
- The album it appeared on
- A fun fact about the song's creation or history
- Chart performance or awards
- Cultural impact or appearances in media

Format your response as JSON:
{{
  "question": "The trivia question",
  "answer": "The correct answer",
  "options": ["Option A", "Option B", "Option C", "Option D"]
}}

Make it fun and engaging for a party game setting!
"""
```

**Environment Variables:**
```bash
OPENAI_API_KEY=sk-...
TUNETRIVIA_TRIVIA_MODEL=gpt-4o-mini  # Cost-effective for trivia
```

### 3.4 Guess Matching Algorithm

Fuzzy matching for artist and song guesses using Levenshtein distance:

```python
# backend/tunetrivia/services/scoring.py

from difflib import SequenceMatcher

def is_match(guess: str, correct: str, threshold: float = 0.8) -> bool:
    """
    Check if a guess matches the correct answer using fuzzy matching.
    Handles common variations like "The Beatles" vs "Beatles".
    """
    # Normalize inputs
    guess_norm = normalize(guess)
    correct_norm = normalize(correct)

    # Direct match
    if guess_norm == correct_norm:
        return True

    # Fuzzy match
    ratio = SequenceMatcher(None, guess_norm, correct_norm).ratio()
    return ratio >= threshold


def normalize(text: str) -> str:
    """Normalize text for comparison."""
    text = text.lower().strip()
    # Remove common prefixes
    prefixes = ['the ', 'a ', 'an ']
    for prefix in prefixes:
        if text.startswith(prefix):
            text = text[len(prefix):]
    # Remove special characters
    text = ''.join(c for c in text if c.isalnum() or c.isspace())
    return text
```

---

## 4. iOS App Architecture

### 4.1 Project Structure

```
mobile/ios/tunetrivia/
├── TuneTrivia.xcodeproj/
├── TuneTrivia/
│   ├── TuneTriviaApp.swift                  # @main entry point
│   ├── ContentView.swift                    # Root navigation (auth gate)
│   ├── Info.plist
│   │
│   ├── Networking/
│   │   └── APIClient.swift                  # Shared HTTP client (mirrors juke)
│   │
│   ├── Models/
│   │   ├── User.swift                       # User & MusicProfile models
│   │   ├── TuneTriviaSession.swift                 # Game session model
│   │   ├── TuneTriviaRound.swift                   # Round with track, preview URL & trivia
│   │   ├── TuneTriviaPlayer.swift                  # Player with scores (is_manual flag)
│   │   ├── TuneTriviaGuess.swift                   # Guess submission
│   │   ├── LeaderboardEntry.swift           # Global leaderboard entry
│   │   └── CatalogModels.swift              # Track, Artist, Album for search
│   │
│   ├── Services/
│   │   ├── AuthService.swift                # Login/register/logout
│   │   ├── ProfileService.swift             # Profile fetch
│   │   ├── SessionService.swift             # CRUD for TuneTrivia sessions
│   │   ├── GameService.swift                # Game control (start/pause/reveal)
│   │   ├── GuessService.swift               # Submit and score guesses
│   │   ├── CatalogService.swift             # Track search
│   │   ├── LeaderboardService.swift         # Global leaderboard
│   │   └── ShareService.swift               # SMS/share sheet integration
│   │
│   ├── ViewModels/
│   │   ├── SessionStore.swift               # Auth state (token, profile)
│   │   ├── AuthViewModel.swift              # Login/register form
│   │   ├── HomeViewModel.swift              # Session list
│   │   ├── CreateSessionViewModel.swift     # Session configuration
│   │   ├── SessionLobbyViewModel.swift      # Waiting room
│   │   ├── AddTracksViewModel.swift         # Track selection
│   │   ├── GameViewModel.swift              # Active game state
│   │   ├── GuessViewModel.swift             # Player guess input
│   │   ├── ScoreboardViewModel.swift        # Live scoreboard
│   │   └── LeaderboardViewModel.swift       # Global leaderboard
│   │
│   ├── Views/
│   │   ├── Auth/
│   │   │   └── AuthView.swift               # Login/Register screen
│   │   ├── Home/
│   │   │   └── HomeView.swift               # Session list, create/join
│   │   ├── Session/
│   │   │   ├── CreateSessionView.swift      # Configuration form
│   │   │   ├── JoinSessionView.swift        # Enter invite code
│   │   │   ├── SessionLobbyView.swift       # Waiting room
│   │   │   └── AddTracksView.swift          # Track selection
│   │   ├── Game/
│   │   │   ├── HostGameView.swift           # Host Mode game screen
│   │   │   ├── PlayerGameView.swift         # Party Mode player screen
│   │   │   ├── GuessInputView.swift         # Answer submission form
│   │   │   ├── RoundRevealView.swift        # Show correct answer
│   │   │   ├── ScoreboardView.swift         # Live scores
│   │   │   └── GameEndView.swift            # Final results
│   │   ├── Leaderboard/
│   │   │   └── LeaderboardView.swift        # Global rankings
│   │   └── Components/
│   │       ├── TrackRow.swift               # Track list item
│   │       ├── PlayerScoreRow.swift         # Player score item
│   │       ├── AlbumArtView.swift           # Blurred/revealed artwork
│   │       ├── CountdownRing.swift          # Timer visualization
│   │       ├── ProgressBar.swift            # Round progress
│   │       └── InviteCodeDisplay.swift      # Shareable code display
│   │
│   ├── DesignSystem/
│   │   └── TuneTriviaDesignSystem.swift     # Colors, typography, components
│   │
│   ├── Resources/
│   │   └── Sounds/
│   │       ├── correct.mp3                  # Correct answer sound
│   │       ├── incorrect.mp3                # Wrong answer sound
│   │       ├── reveal.mp3                   # Answer reveal sound
│   │       └── victory.mp3                  # Game end celebration
│   │
│   ├── BrandAssets/
│   │   ├── icon_export.json
│   │   └── AppIcon.appiconset/
│   │
│   ├── Assets.xcassets/
│   └── Preview Content/
│
├── TuneTriviaTests/
│   ├── Services/
│   ├── ViewModels/
│   └── Mocks/
│       └── MockAPIClient.swift
│
└── TuneTriviaUITests/
    └── TuneTriviaUITests.swift
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
┌──────────────────┐
│    HomeView      │◄─────────────────────────────────────────────┐
│  (my sessions)   │                                               │
└──────┬───────────┘                                               │
       │                                                           │
       ├── Create ──► CreateSessionView                            │
       │                  │                                        │
       │                  ├── Configure settings                   │
       │                  ├── Auto-select OR manual tracks         │
       │                  └── ► SessionLobbyView                   │
       │                                                           │
       ├── Join ────► JoinSessionView                              │
       │                  │                                        │
       │                  └── Enter code ──► SessionLobbyView      │
       │                                                           │
       ├── Leaderboard ─► LeaderboardView                          │
       │                                                           │
       └── Tap session ─► SessionLobbyView                         │
                             │                                     │
                             ├── [Host] Add Tracks ──► AddTracksView
                             ├── [Host] Share Code ──► Share Sheet │
                             │                                     │
                             └── Start Game                        │
                                    │                              │
              ┌────────────────────┴────────────────────┐         │
              │                                          │         │
              ▼                                          ▼         │
       ┌─────────────┐                          ┌─────────────┐   │
       │HostGameView │                          │PlayerGameView│  │
       │             │                          │             │   │
       │ - See track │                          │ - See album │   │
       │ - See players                          │   art (blur)│   │
       │ - Manual score                         │ - Guess form│   │
       │ - Next round │                         │ - Timer     │   │
       └──────┬──────┘                          └──────┬──────┘   │
              │                                        │          │
              └──────────────┬─────────────────────────┘          │
                             │                                     │
                             ▼                                     │
                      ┌─────────────┐                              │
                      │RoundRevealView│                            │
                      │  (answer +   │                             │
                      │  scoreboard) │                             │
                      └──────┬──────┘                              │
                             │                                     │
                             ├── More rounds ──► Next Round        │
                             │                                     │
                             └── Game Over ──► GameEndView ────────┘
```

### 4.3 Game Flow States

```
                    ┌─────────────┐
                    │   LOBBY     │
                    │ (configure) │
                    └──────┬──────┘
                           │ Start
                           ▼
    ┌───────────────────────────────────────────┐
    │              ACTIVE ROUND                  │
    │  ┌─────────────────────────────────────┐  │
    │  │ 1. Play 30-sec Spotify preview       │  │
    │  │ 2. Collect guesses (Party Mode)      │  │
    │  │    OR score manually (Host Mode)     │  │
    │  │ 3. Host advances when ready          │  │
    │  │ 4. Reveal song/artist answer         │  │
    │  │ 5. Trivia bonus (if enabled)         │  │
    │  │ 6. Update scores                      │  │
    │  └─────────────────────────────────────┘  │
    │                    │                       │
    │         ┌──────────┼──────────┐           │
    │         ▼          ▼          ▼           │
    │      [Pause]   [Next Round] [End Early]   │
    │         │          │          │           │
    │         ▼          │          │           │
    │      PAUSED ───────┘          │           │
    │                               │           │
    └───────────────────────────────┼───────────┘
                                    │
                                    ▼
                             ┌─────────────┐
                             │    ENDED    │
                             │ (final scores│
                             │  leaderboard │
                             │   update)    │
                             └─────────────┘
```

### 4.4 Key Technical Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| UI Framework | SwiftUI | Matches existing Juke iOS app pattern |
| Architecture | MVVM | Consistent with Juke and ShotClock apps |
| State Management | `@StateObject` + `@EnvironmentObject` | Minimal dependencies, reactive |
| Networking | URLSession via shared `APIClient` | Same pattern, no external deps |
| Audio Playback | Spotify 30-sec preview URL | Free tier, no Premium required, plays in AVPlayer |
| Real-time Sync | Polling (3s interval when active) | Simple, reliable for game state |
| Guess Timing | Until host advances | No timer pressure, host controls flow |
| Token Storage | UserDefaults | Matches Juke (Keychain for production) |
| SMS Sharing | `MFMessageComposeViewController` | Native iOS SMS composition |
| Navigation | `NavigationStack` (iOS 16+) | Modern SwiftUI navigation |
| Min iOS | 16.0 | NavigationStack requirement |
| Target Devices | iPhone 16/17 Pro/Max | Latest generation |

### 4.5 Album Artwork Display

In Party Mode, album artwork is displayed to players with a blur effect during guessing to provide visual hints without revealing the answer:

```swift
struct AlbumArtView: View {
    let artworkURL: URL?
    let isRevealed: Bool

    var body: some View {
        AsyncImage(url: artworkURL) { image in
            image
                .resizable()
                .aspectRatio(contentMode: .fill)
                .blur(radius: isRevealed ? 0 : 20)
                .animation(.easeInOut(duration: 0.5), value: isRevealed)
        } placeholder: {
            Rectangle()
                .fill(TuneTriviaPalette.panel)
        }
        .frame(width: 280, height: 280)
        .cornerRadius(20)
        .overlay(
            RoundedRectangle(cornerRadius: 20)
                .stroke(TuneTriviaPalette.border, lineWidth: 1)
        )
    }
}
```

---

## 5. Feature Implementation Order

| # | Feature | Description | Priority |
|---|---------|-------------|----------|
| 1 | Project scaffolding + design system | Xcode project, palette, reusable components | P0 |
| 2 | Authentication | Login/register/logout matching Juke flows | P0 |
| 3 | Home screen | Session list with create/join entry points | P0 |
| 4 | Create session (basic) | Configuration form for game settings | P0 |
| 5 | Join session | Invite code entry and validation | P0 |
| 6 | Session lobby | Players list, waiting room | P0 |
| 7 | Add tracks (manual) | Search and add songs to session | P0 |
| 8 | Game flow (Host Mode) | Manual scoring, round progression | P0 |
| 9 | Game flow (Party Mode) | Player guessing, auto-scoring | P0 |
| 10 | Round reveal | Answer display with animations | P0 |
| 11 | Scoreboard | Live scores during and after game | P0 |
| 12 | Auto-select tracks | Based on decade/genre/artist criteria | P1 |
| 13 | Trivia integration | ChatGPT-generated questions | P1 |
| 14 | Global leaderboard | Rankings across all games | P1 |
| 15 | Share session invite | SMS template with invite code | P1 |
| 16 | Sound effects | Audio feedback for game events | P2 |
| 17 | App icons + brand assets | SVG render pipeline | P0 |

---

## 6. Security Considerations

- All endpoints require valid Token authentication
- Session modifications restricted to host via custom `IsSessionHost` permission
- Invite codes are 6-char alphanumeric, randomly generated
- Guesses can only be submitted during active round state
- Guesses are locked after round reveal
- Rate limiting on guess submissions (1 per round per player)
- Input validation and sanitization on all user-facing forms
- Fuzzy matching prevents exact answer enumeration
- Trivia API calls are server-side only (API key not exposed)

---

## 7. Scoring System

### Points Structure (Default)
- **Correct Artist**: 1 point
- **Correct Song Title**: 1 point
- **Correct Trivia Answer**: 1 point (bonus)

### Maximum Points Per Round
- Without trivia: 2 points
- With trivia: 3 points

### Fuzzy Matching Rules
- Case insensitive
- Ignores articles ("The", "A", "An")
- 80% similarity threshold
- Common variations accepted (e.g., "Springsteen" for "Bruce Springsteen")

---

## 8. Build & Deployment

- **Build Script**: `scripts/build_and_run_ios.sh` with `IOS_PROJECT_NAME=tunetrivia`
- **Bundle ID**: `embario.TuneTrivia`
- **Scheme**: `TuneTrivia`
- **Icon Pipeline**: SVG → `scripts/render_icons.cjs` → BrandAssets/AppIcon.appiconset/
- **Simulator**: iPhone 17 Pro (default target)
- **Backend URL**: Configurable via `BACKEND_URL` in Info.plist

---

## 9. Environment Variables (Backend)

```bash
# Existing Juke vars (required)
DJANGO_SECRET_KEY=...
POSTGRES_NAME=...
POSTGRES_USER=...
POSTGRES_PASSWORD=...
SOCIAL_AUTH_SPOTIFY_KEY=...
SOCIAL_AUTH_SPOTIFY_SECRET=...

# New for TuneTrivia
OPENAI_API_KEY=sk-...                    # For trivia generation
TUNETRIVIA_TRIVIA_MODEL=gpt-4o-mini            # OpenAI model to use
TUNETRIVIA_TRIVIA_ENABLED=true                  # Feature flag
TUNETRIVIA_MAX_SONGS_PER_SESSION=50             # Limit
TUNETRIVIA_PREVIEW_DURATION_SEC=30              # Spotify preview duration (fixed)
```

---

## 10. Testing Strategy

### Unit Tests
- Model validation and serialization
- Fuzzy matching algorithm
- Score calculation logic
- Game state transitions

### Integration Tests
- API endpoint responses
- Authentication flows
- Session lifecycle (create → play → end)
- Leaderboard updates

### UI Tests
- Navigation flows
- Form validation
- Game interaction sequences

### Manual Testing
- Spotify playback integration
- Multi-device Party Mode
- Network failure handling
- Edge cases (ties, empty rounds, etc.)
