# Juke Enhanced User Registration - Architecture Document
**Version:** 2.0
**Date:** 2026-01-24
**Status:** DRAFT - Awaiting Approval

---

## 1. Executive Summary

This document outlines the architecture for enhancing the Juke user registration experience with an interactive, multi-step onboarding flow that captures users' musical preferences to seed their Music Profile. The design prioritizes mobile-first responsiveness, keyboard accessibility, and delightful micro-interactions while integrating with the existing codebase patterns.

---

## 2. Current State Analysis

### Registration Flow (Investigated)
- **Endpoint**: `POST /api/v1/auth/accounts/register/`
- **Uses**: `rest_registration` library's `RegisterView` (see `juke_auth/views.py:227`)
- **Accepts**: `username`, `email`, `password`, `password_confirm` only
- **Behavior**: Creates `JukeUser` with `is_active=False`, sends verification email
- **MusicProfile**: NOT created during registration - created on first `GET /api/v1/music-profiles/me/` (line 114: `get_or_create`)

### Key Insight
The registration endpoint does NOT support additional profile fields. We need a **two-phase approach**:
1. Register user (creates inactive `JukeUser`)
2. After email verification + login, update `MusicProfile` via `PATCH /api/v1/music-profiles/me/`

### MusicProfile Model (from `juke_auth/models.py`)
```python
class MusicProfile(models.Model):
    favorite_genres = models.JSONField(default=list)      # Array of genre names
    favorite_artists = models.JSONField(default=list)     # Array of artist Spotify IDs
    favorite_albums = models.JSONField(default=list)
    favorite_tracks = models.JSONField(default=list)
    city_lat = models.FloatField(null=True)               # For Juke World placement
    city_lng = models.FloatField(null=True)
    location = models.CharField(max_length=120)           # Human-readable location
    # ... other fields
```

---

## 3. Registration vs. Onboarding Timing - Tradeoff Analysis

### Option A: Register First, Then Onboarding (RECOMMENDED)

```
[Account Setup] → [Email Sent] → [Verify Email] → [Login] → [Onboarding Wizard] → [Juke World]
```

**Pros:**
- User has account immediately, can resume onboarding later if interrupted
- Matches existing email verification requirement
- Profile data saved to real account (not lost on page refresh)
- Can track partially completed onboarding in analytics
- Lower risk of lost progress

**Cons:**
- Longer initial journey before "fun" onboarding questions
- User might verify email and never return for onboarding

### Option B: Onboarding First, Then Register

```
[Onboarding Wizard] → [Account Setup] → [Email Sent] → [Verify Email] → [Juke World]
```

**Pros:**
- User sees engaging content first (higher initial engagement)
- Feels more like "joining a community" than "filling out forms"

**Cons:**
- All onboarding progress lost if user abandons before completing registration
- Requires storing temporary data (localStorage) that could be lost
- More complex state management
- User might complete fun questions but bounce on registration form

### Recommendation: **Option A (Register First)** ✅ APPROVED
Users who complete email verification have demonstrated commitment. The onboarding wizard becomes a "reward" for joining, and profile data is safely stored. We can make the registration step quick and delightful to minimize friction.

### Registration Excitement Tagline
The registration form will include a teaser to build anticipation:

```
┌─────────────────────────────────────────────┐
│           Join the Juke Community           │
│                                             │
│  "After you sign up, we'll help you build   │
│   your music identity and place you on      │
│   the global map of music lovers."          │
│                                             │
│  [Username]  [Email]  [Password]            │
│                                             │
│         [ Create Account ]                  │
└─────────────────────────────────────────────┘
```

---

## 4. Proposed Solution Architecture

### 4.1 High-Level Flow

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           JUKE REGISTRATION JOURNEY                              │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                  │
│  PHASE 1: REGISTRATION          PHASE 2: ONBOARDING              PHASE 3: WELCOME│
│  ─────────────────────          ────────────────────             ────────────────│
│  • Username                     • Top 3 Genres (+images)         • Spotify OAuth │
│  • Email                        • Ride-or-Die Artist             • Zoom to user  │
│  • Password                     • Hated Genres                     on Juke World │
│  • [Submit → Verify Email]      • Rainy Day / Workout Vibes                      │
│                                 • Age Range / Location                            │
│  ↓                              • Music Discovery Style                           │
│  [Email Verification]           • Guilty Pleasure Genre                           │
│  ↓                                                                                │
│  [Auto-Login]                                                                     │
│                                                                                  │
└─────────────────────────────────────────────────────────────────────────────────┘
```

### 4.2 Genre Display Strategy

Per your feedback, genres will display with **top artists** from Spotify API:

```
┌─────────────────────────────────────────────────────────────────┐
│  TOP 10 GENRES (fetched from Spotify with representative artists)│
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐              │
│  │ [3 artist   │  │ [3 artist   │  │ [3 artist   │              │
│  │  images]    │  │  images]    │  │  images]    │              │
│  │             │  │             │  │             │              │
│  │   HIP-HOP   │  │    ROCK     │  │    POP      │              │
│  │  Drake,     │  │  Foo Fight, │  │  Taylor,    │              │
│  │  Kendrick,  │  │  Green Day, │  │  Dua Lipa,  │              │
│  │  J. Cole    │  │  Nirvana    │  │  The Weeknd │              │
│  └─────────────┘  └─────────────┘  └─────────────┘              │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

**API Flow:**
1. Fetch top 10 genres from Spotify: `GET /api/v1/genres/?limit=10`
2. For each genre, fetch top 3 artists: `GET /api/v1/artists/?genre={genre}&limit=3` (or new endpoint)
3. Display genre cards with artist images

**Backend Enhancement Needed:**
- New endpoint or param: `GET /api/v1/genres/featured/` returning genres with top artist images

---

## 5. Enhanced Question Set

### Core Questions (Required)

| # | Question | Input Type | Data Field | Notes |
|---|----------|------------|------------|-------|
| 1 | "Pick your top 3 genres" | Genre cards with artist images | `favorite_genres[]` | Spotify API, limit 10 options |
| 2 | "Is there one artist you'll live and die by?" | Artist search autocomplete | `favorite_artists[0]` | With artist image |
| 3 | "Any genres that make your ears bleed?" | Multi-select from remaining genres | `custom_data.hated_genres[]` | Excludes selected favorites |
| 4 | "Where are you located?" | City autocomplete | `location`, `city_lat`, `city_lng` | For Juke World placement |

### Contextual Questions (Optional - Stored in `custom_data`)

| # | Question | Input Type | Data Field | Purpose |
|---|----------|------------|------------|---------|
| 5 | "What do you reach for on a rainy day?" | Genre/mood cards | `custom_data.rainy_day_genre` | Filterable: "who listens to Soul on a rainy day?" |
| 6 | "What's your workout anthem vibe?" | Energy level cards | `custom_data.workout_vibe` | Filterable: "high-energy workout listeners" |
| 7 | "What's your age range?" | Pill selector | `custom_data.age_range` | Demographics, recommendations |
| 8 | "Guilty pleasure genre?" | Single select | `custom_data.guilty_pleasure` | Fun, community building |
| 9 | "How do you discover new music?" | Multi-select | `custom_data.discovery_methods[]` | Recommendations, features |

### Additional Questions (APPROVED)

| # | Question | Input Type | Data Field | Purpose |
|---|----------|------------|------------|---------|
| 10 | "What decade of music speaks to you most?" | Single-select pills | `custom_data.favorite_decade` | Era preferences for recommendations |
| 11 | "Are you a playlist person or album listener?" | Binary choice cards | `custom_data.listening_style` | Consumption patterns, feature personalization |

---

## 6. Onboarding State Persistence Strategy

### Approach: Hybrid localStorage Draft ✅ APPROVED

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        PERSISTENCE FLOW                                      │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Step 1 ──► React State + localStorage ──► Step 2 ──► ... ──► Final Step   │
│                     │                                              │         │
│                     │ (backup draft)                               │         │
│                     ▼                                              ▼         │
│              localStorage:                                  PATCH /me/       │
│              'juke-onboarding-draft'                        (atomic save)    │
│                     │                                              │         │
│                     │ (on page refresh)                            │         │
│                     ▼                                              ▼         │
│              Resume at saved step                         Clear draft       │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Implementation

```typescript
// hooks/useOnboardingState.ts
const STORAGE_KEY = 'juke-onboarding-draft';

type OnboardingDraft = {
  currentStep: number;
  completedAt?: string;
  data: {
    favoriteGenres: string[];
    rideOrDieArtist: { id: string; name: string; imageUrl: string } | null;
    hatedGenres: string[];
    rainyDayGenre: string | null;
    workoutVibe: string | null;
    ageRange: string | null;
    location: { name: string; lat: number; lng: number } | null;
    favoriteDecade: string | null;
    listeningStyle: 'playlist' | 'album' | null;
    discoveryMethods: string[];
    guiltyPleasure: string | null;
  };
};

export function useOnboardingState() {
  // Initialize from localStorage if draft exists
  const [state, dispatch] = useReducer(onboardingReducer, null, () => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      try {
        return JSON.parse(saved);
      } catch {
        return initialState;
      }
    }
    return initialState;
  });

  // Auto-save to localStorage on every state change
  useEffect(() => {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
  }, [state]);

  // Clear draft after successful API save
  const clearDraft = useCallback(() => {
    localStorage.removeItem(STORAGE_KEY);
  }, []);

  // Check if user has an incomplete draft
  const hasDraft = useCallback(() => {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (!saved) return false;
    const draft = JSON.parse(saved);
    return draft.currentStep > 0 && !draft.completedAt;
  }, []);

  return { state, dispatch, clearDraft, hasDraft };
}
```

### Resume Flow
1. User logs in → `useOnboardingState().hasDraft()` checks localStorage
2. If draft exists and incomplete → show "Continue your profile setup?" prompt
3. User clicks continue → redirect to `/onboarding` at saved step
4. User completes all steps → `PATCH /api/v1/music-profiles/me/` with all data
5. On success → `clearDraft()` removes localStorage entry

### Edge Cases
- **Draft older than 30 days**: Discard and start fresh
- **User manually navigates away**: Draft preserved, can resume later
- **API save fails**: Keep draft, show error, allow retry

---

## 7. Custom Data Indexing (Backend)

For the `custom_data` fields to be filterable ("who listens to Soul on a rainy day?"), we need:

### Option A: JSONField Indexing (PostgreSQL)
```sql
CREATE INDEX idx_rainy_day ON juke_auth_musicprofile
USING gin ((custom_data->'rainy_day_genre'));
```

### Option B: Dedicated Fields (Recommended for Frequent Queries)
Add explicit fields to `MusicProfile` model:
```python
rainy_day_genre = models.CharField(max_length=50, blank=True, db_index=True)
workout_vibe = models.CharField(max_length=50, blank=True, db_index=True)
age_range = models.CharField(max_length=20, blank=True, db_index=True)
```

**Recommendation:** Start with `custom_data` JSONField for flexibility, migrate to dedicated fields when query patterns are established.

---

## 7. Post-Onboarding: Juke World Welcome

After completing onboarding and Spotify connection:

```typescript
// Navigate to Juke World with user's coordinates
const userProfile = await api.getMusicProfile('me');
navigate('/world', {
  state: {
    welcomeUser: true,
    focusLat: userProfile.city_lat,
    focusLng: userProfile.city_lng,
    username: userProfile.username
  }
});
```

**JukeWorldRoute Enhancement:**
```typescript
// In JukeWorldRoute.tsx
const location = useLocation();
const globeRef = useRef<GlobeMethods>();

useEffect(() => {
  if (location.state?.welcomeUser && globeRef.current) {
    // Zoom to user's location with welcome animation
    globeRef.current.pointOfView(
      { lat: location.state.focusLat, lng: location.state.focusLng, altitude: 0.5 },
      2000 // 2 second animation
    );
    // Show welcome toast: "Welcome to Juke World! You're now on the map."
  }
}, [location.state]);
```

---

## 8. Component Architecture

```
src/features/auth/
├── components/
│   ├── RegisterForm.tsx              # Existing - Phase 1
│   ├── LoginForm.tsx                 # Existing
│   └── onboarding/                   # NEW - Phase 2
│       ├── OnboardingWizard.tsx      # Main wizard container
│       ├── WizardProgress.tsx        # Step indicator
│       ├── steps/
│       │   ├── GenreStep.tsx         # Top 3 genres with artist images
│       │   ├── ArtistStep.tsx        # Ride-or-die artist
│       │   ├── PreferencesStep.tsx   # Hated genres, rainy day, workout
│       │   ├── AboutYouStep.tsx      # Age, location, discovery style
│       │   └── ConnectStep.tsx       # Spotify OAuth + Juke World redirect
│       ├── components/
│       │   ├── GenreCard.tsx         # Genre with artist thumbnails
│       │   ├── ArtistSearchInput.tsx # Autocomplete with images
│       │   ├── MoodCard.tsx          # Rainy day / workout selectors
│       │   ├── CityAutocomplete.tsx  # Location with lat/lng
│       │   └── PillSelector.tsx      # Age range, discovery methods
│       └── hooks/
│           └── useOnboardingState.ts # Wizard state management
├── context/
│   └── OnboardingProvider.tsx        # Wizard state context
├── api/
│   ├── authApi.ts                    # Existing
│   └── onboardingApi.ts              # NEW: genre/artist fetching
└── routes/
    ├── RegisterRoute.tsx             # Existing - Phase 1
    └── OnboardingRoute.tsx           # NEW - Phase 2 (post-login)
```

---

## 9. API Requirements

### Existing Endpoints (No Changes)
- `POST /api/v1/auth/accounts/register/` - Create user
- `GET /api/v1/music-profiles/me/` - Get/create profile
- `PATCH /api/v1/music-profiles/me/` - Update profile
- `GET /api/v1/artists/?search={query}` - Artist search

### New/Enhanced Endpoints Needed

| Endpoint | Purpose | Response |
|----------|---------|----------|
| `GET /api/v1/genres/featured/` | Top 10 genres with representative artists | `[{name, spotify_id, top_artists: [{name, image_url}]}]` |
| `GET /api/v1/cities/autocomplete/?q={query}` | City search for location | `[{name, country, lat, lng}]` |

**Note:** City autocomplete could use a lightweight service like GeoNames or a static list of major cities.

---

## 10. Data Flow

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              USER JOURNEY                                    │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
     ┌────────────────────────────┼────────────────────────────────┐
     │                            │                                 │
     ▼                            ▼                                 ▼
┌─────────────┐           ┌─────────────┐                  ┌─────────────┐
│ REGISTER    │           │ ONBOARDING  │                  │ JUKE WORLD  │
│ (Phase 1)   │           │ (Phase 2)   │                  │ (Phase 3)   │
├─────────────┤           ├─────────────┤                  ├─────────────┤
│ POST        │  verify   │ GET genres  │  save profile    │ GET /globe  │
│ /register/  │ ───────►  │ GET artists │ ──────────────►  │ pointOfView │
│             │  + login  │ PATCH /me/  │                  │ (zoom)      │
└─────────────┘           └─────────────┘                  └─────────────┘
```

---

## 11. File Change Summary

### New Files (~18 files, ~2500 lines)
| File | Purpose | Est. Lines |
|------|---------|------------|
| `onboarding/OnboardingWizard.tsx` | Main wizard container | ~180 |
| `onboarding/WizardProgress.tsx` | Step progress indicator | ~80 |
| `onboarding/steps/GenreStep.tsx` | Genre selection with artist images | ~200 |
| `onboarding/steps/ArtistStep.tsx` | Ride-or-die artist search | ~150 |
| `onboarding/steps/PreferencesStep.tsx` | Hated genres, moods | ~180 |
| `onboarding/steps/AboutYouStep.tsx` | Age, location, discovery | ~160 |
| `onboarding/steps/ConnectStep.tsx` | Spotify + welcome | ~140 |
| `onboarding/components/GenreCard.tsx` | Genre with artist thumbnails | ~120 |
| `onboarding/components/ArtistSearchInput.tsx` | Artist autocomplete | ~150 |
| `onboarding/components/MoodCard.tsx` | Mood/vibe selectors | ~100 |
| `onboarding/components/CityAutocomplete.tsx` | Location picker | ~130 |
| `onboarding/components/PillSelector.tsx` | Age/discovery pills | ~90 |
| `context/OnboardingProvider.tsx` | State management | ~200 |
| `api/onboardingApi.ts` | API calls | ~80 |
| `routes/OnboardingRoute.tsx` | Route wrapper | ~60 |
| `onboarding/onboarding.css` | Styles | ~400 |

### Modified Files (~4 files)
| File | Change |
|------|--------|
| `router.tsx` | Add `/onboarding` route |
| `JukeWorldRoute.tsx` | Add welcome zoom logic |
| `types/profile.ts` | Add `custom_data` types |
| Backend: `juke_auth/views.py` | Add featured genres endpoint (optional) |

---

## 12. Visualization Framework

Per your confirmation, we'll implement **3 UI visualization options** using:
- **React + CSS** (native implementation)
- Leveraging existing CSS variable system
- No new dependencies required

The 3 options will showcase:
1. **Card Stack Wizard** - Full-screen cards that slide/stack
2. **Chat-Style Flow** - Conversational bubbles like messaging
3. **Single-Page Progressive** - Scrollable sections with sticky progress

---

## 13. Open Questions Resolved

| Question | Answer |
|----------|--------|
| Backend accepts profile fields? | No - separate PATCH after registration |
| Genre source? | Spotify API with top artists (top 10 genres) |
| Spotify OAuth timing? | After email verification, end of onboarding |
| Registration timing? | Before onboarding (Option A) |
| Custom data indexing? | Start with JSONField, migrate to dedicated fields as needed |

---

## 14. Next Steps

1. ✅ Architecture document v2 (this document)
2. ⏳ **Awaiting approval** before proceeding
3. ⏳ Create 3 UI/UX visualization implementations
4. ⏳ Select approved design direction
5. ⏳ Implement components
6. ⏳ Integration testing
7. ⏳ Final review

---

**Please review and approve to proceed with the 3 UI/UX visualizations.**
