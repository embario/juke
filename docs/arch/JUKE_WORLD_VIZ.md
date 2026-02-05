# Juke World — Architecture Document

**Version**: 1.2
**Date**: 2026-01-22
**Author**: Agent
**Status**: Pending Approval

---

## 1. Overview

Juke World is a new page in the Juke web app that renders an interactive 3D globe displaying all Juke users as geo-located drop-pins. Each pin's **size** reflects the user's "clout" (0–1 streaming metric) and its **color** reflects the user's top super-genre. Users can spin, zoom, hover, and click on pins to inspect other listeners and navigate to their full music profiles.

---

## 2. Technology Selection: 3D Globe Library

### Candidates Evaluated

| Library | Pros | Cons |
|---------|------|------|
| **Globe.GL / react-globe.gl** | Purpose-built for globe point-cloud rendering; Three.js-based; instanced geometry for 50K+ points; React wrapper; built-in zoom/spin/click; lightweight (~150KB gzipped) | Less suited for terrain/tile map overlays |
| CesiumJS | Full GIS engine; tiled imagery; terrain | Very heavy (~3MB); overkill for point-cloud; complex API; no React wrapper |
| Three.js (raw) | Maximum control | Requires building globe, camera, controls, picking from scratch |
| Mapbox GL JS | Great 2D/3D maps | Globe mode limited; point rendering caps; pricing tiers |

### Recommendation: **react-globe.gl**

`react-globe.gl` is the React wrapper around Globe.GL which is built on Three.js and WebGL. It provides:

- Declarative React API for point layers, labels, custom HTML tooltips
- Instanced mesh rendering (handles 100K+ points at 60fps)
- Built-in orbit controls (spin, zoom, pan)
- Point `altitude`, `radius`, and `color` bindings for each data point
- Click/hover callbacks per point
- Responsive canvas resizing
- MIT license, no API key required

**Package**: `react-globe.gl` (npm) — depends on `globe.gl`, `three`, `three-globe`

---

## 3. Backend Changes

### 3.1 Model Changes — `MusicProfile`

Add three new fields to the existing `MusicProfile` model in `backend/juke_auth/models.py`:

```python
class MusicProfile(models.Model):
    # ... existing fields ...

    # New fields for Juke World (city-level precision for privacy)
    city_lat = models.FloatField(null=True, blank=True, db_index=True,
        help_text="Latitude rounded to 2 decimal places (~1.1km / city-centroid precision)")
    city_lng = models.FloatField(null=True, blank=True, db_index=True,
        help_text="Longitude rounded to 2 decimal places (~1.1km / city-centroid precision)")
    clout = models.FloatField(default=0.0, help_text="Streaming clout metric, 0.0–1.0")
```

- `city_lat`/`city_lng`: Geo-coordinates **rounded to 2 decimal places** on write, snapping to city-centroid level (~1.1km precision). This prevents revealing exact user addresses while still positioning pins accurately on the globe. Nullable for users who have not opted in. Indexed for spatial bounding-box queries.
- `clout`: Normalized streaming metric (0.0 = no streaming, 1.0 = maximum streaming). Default 0.0.
- **Privacy enforcement**: The model's `save()` method rounds any incoming lat/lng values to 2 decimal places, ensuring precise coordinates can never be stored even if passed by the client.

**Note**: `top_genre` is derived from `favorite_genres[0]` at serialization time, not stored as a separate column, to keep the source of truth in the existing `favorite_genres` JSONField.

### 3.2 New API Action — Globe Points

A new `globe` list action on the **existing** `MusicProfileViewSet`, optimized for bulk geo-point retrieval with LOD filtering. No new Django app required.

```
GET /api/v1/music-profiles/globe/
```

**Query Parameters**:

| Param | Type | Description |
|-------|------|-------------|
| `min_lat` | float | Bounding box south latitude |
| `max_lat` | float | Bounding box north latitude |
| `min_lng` | float | Bounding box west longitude |
| `max_lng` | float | Bounding box east longitude |
| `zoom` | int (1–20) | Camera zoom level (higher = more zoomed in) |
| `limit` | int | Max points to return (default 5000, max 10000) |

**Response** (JSON array — lean payload, no envelope):

```json
[
  {
    "id": 42,
    "username": "melodyqueen",
    "lat": 40.71,
    "lng": -74.01,
    "clout": 0.87,
    "top_genre": "pop",
    "display_name": "Melody Queen"
  }
]
```

**LOD Strategy** (server-side):

| Zoom Level | Filter Rule |
|------------|-------------|
| 1–4 (globe view) | Only return points with `clout >= 0.5` |
| 5–8 (continent/country) | Only return points with `clout >= 0.2` |
| 9–12 (region/state) | Only return points with `clout >= 0.05` |
| 13+ (city level) | Return all points within bounding box |

This ensures the globe never renders more than ~10K points at any zoom level while progressively revealing lower-clout users as the camera zooms in.

**Ordering**: Points are returned ordered by `clout DESC` so the most prominent users appear first if the limit is hit.

### 3.3 User Detail — Existing Endpoint (Reused)

On-click drill-down reuses the **existing** profile endpoint with `clout` and `top_genre` added to the serializer:

```
GET /api/v1/music-profiles/<username>/
```

**Response** (existing fields + new `clout` and `top_genre`):

```json
{
  "id": 42,
  "username": "melodyqueen",
  "display_name": "Melody Queen",
  "avatar_url": "https://...",
  "tagline": "Pop princess from NYC",
  "location": "New York, NY",
  "clout": 0.87,
  "top_genre": "pop",
  "favorite_genres": ["pop", "r&b", "dance"],
  "favorite_artists": ["Taylor Swift", "Dua Lipa"],
  "favorite_albums": ["Midnights", "Future Nostalgia"],
  "favorite_tracks": ["Anti-Hero", "Levitating"],
  "created_at": "2025-06-15T...",
  "modified_at": "2026-01-20T...",
  "is_owner": false
}
```

No new endpoint needed — the existing `MusicProfileSerializer` is extended with `clout` and a computed `top_genre` field. This keeps the API surface minimal.

### 3.4 Database Migration

A single Django migration adding `city_lat`, `city_lng`, `clout` to `MusicProfile`. The migration is additive (no data loss, nullable fields with defaults).

### 3.5 Management Command — Seed Globe Data

A `manage.py seed_world_data` command that generates synthetic user data (50K+ users with random lat/lng, clout values, and genre distributions) for development and demo purposes.

---

## 4. Frontend Changes

### 4.1 New Feature Module

```
web/src/features/world/
├── components/
│   ├── JukeGlobe.tsx          # Main globe component (react-globe.gl wrapper)
│   ├── GlobeOverlayNav.tsx     # Transparent top nav bar (logo + back button)
│   ├── GlobeControls.tsx       # Zoom/reset controls overlay
│   ├── UserPinTooltip.tsx      # Hover tooltip (username + clout)
│   └── UserDetailModal.tsx     # Click modal (full profile detail)
├── hooks/
│   ├── useGlobePoints.ts       # Fetches points with LOD params
│   └── useUserDetail.ts        # Fetches single user detail on click
├── api/
│   └── worldApi.ts             # API client functions for /music-profiles/globe/
├── types.ts                    # GlobePoint, UserDetail types
├── constants.ts                # Genre color map, zoom thresholds
└── routes/
    └── JukeWorldRoute.tsx      # Full-screen route (no AppLayout wrapper)
```

### 4.2 Route Addition — Full-Screen Layout

The `/world` route is mounted **outside** the `AppLayout` wrapper so it is not constrained by the sidebar/header chrome. This gives the globe full viewport coverage.

Add to `web/src/router.tsx` as a **sibling** to the AppLayout route:

```tsx
const router = createBrowserRouter([
  {
    path: '/',
    element: <AppLayout />,
    children: [
      // ... existing routes (library, login, profiles, etc.)
    ],
  },
  {
    path: '/world',
    element: <JukeWorldRoute />,  // Full-screen, no AppLayout wrapper
  },
  {
    path: '*',
    element: <NotFoundRoute />,
  },
]);
```

**JukeWorldRoute** renders the globe at `100vw × 100vh` with a transparent **overlay navigation bar** positioned absolutely at the top. This bar contains:

- The Juke logo (links back to `/`)
- A "Back" or home icon button
- Consistent with the app's existing font family, color tokens, and design language

This ensures the page feels like part of the Juke app while giving the globe maximum screen real estate.

### 4.3 Navigation

Add "Juke World" link to the existing `Sidebar.tsx` navigation so users can navigate to the globe from the main app shell.

### 4.4 Genre Color Scheme

Each super-genre maps to a distinct, visually accessible color:

| Super Genre | Hex Color | Visual |
|-------------|-----------|--------|
| Pop | `#FF6B9D` | Hot Pink |
| Rock | `#E74C3C` | Red |
| Country | `#F39C12` | Amber |
| Rap/Hip-Hop | `#9B59B6` | Purple |
| Folk | `#27AE60` | Green |
| Jazz | `#3498DB` | Blue |
| Classical | `#1ABC9C` | Teal |
| Other/Unknown | `#95A5A6` | Gray |

Colors are chosen for high contrast against the dark globe background and for distinguishability from each other (including for common color-vision deficiencies).

### 4.5 Globe Component Behavior

**JukeGlobe.tsx** configuration:

- **Globe texture**: Stylized dark/minimal earth with subtle country boundaries (maximizes pin visibility against dark background) — bundled as a static asset
- **Point layer**: Each user rendered as a cylindrical pin with:
  - `pointAltitude`: Proportional to `clout` (range 0.01–0.15 globe radii)
  - `pointRadius`: Proportional to `clout` (range 0.05–0.4)
  - `pointColor`: Determined by `top_genre` → color map lookup
- **Hover**: Shows `UserPinTooltip` with username and clout percentage
- **Left-click**: Fetches user detail via existing `GET /api/v1/music-profiles/<username>/` and opens `UserDetailModal`
- **Controls**: Auto-rotate (slow, pauses on interaction), zoom via scroll/pinch, drag to spin
- **Camera change callback**: Debounced (300ms) — recalculates bounding box and zoom level, fetches new points

### 4.6 Level-of-Detail (LOD) — Client Side

The client computes the visible bounding box from the Three.js camera frustum and the current zoom level, then requests only the points within that viewport:

```
Camera change → debounce 300ms → compute bbox + zoom → GET /music-profiles/globe/?min_lat=...&zoom=...
```

Points are stored in a React state array and passed to the Globe component. On each fetch, the entire point set is replaced (no incremental merging, to keep logic simple and avoid stale data).

### 4.7 UserDetailModal

A slide-in or centered modal displaying:

- Avatar, display name, username
- Tagline
- Location
- Clout meter (visual bar/gauge)
- Top genres (colored chips)
- Favorite artists, albums, tracks (truncated lists)
- "View Full Profile" link → `/profiles/<username>`

Only one modal open at a time. Clicking another pin or clicking outside closes the current modal.

### 4.8 Performance Budget

| Metric | Target | Strategy |
|--------|--------|----------|
| Initial load (globe visible) | < 2s on 4G | Code-split route; lazy-load globe chunk |
| Point render (50K points) | 60fps | Instanced mesh via Globe.GL; no DOM per point |
| Frame drops during interaction | > 45fps | Debounced data fetches; GPU-only rendering |
| Memory | < 200MB | Point data as typed arrays; no full profile data until click |
| Network per LOD request | < 100KB | Lean JSON payloads (~120 bytes/point × 5K = 600KB max) |

### 4.9 Browser Compatibility & Responsiveness

The globe visualization targets the frontend web app only (no native mobile WebView integration for V1). The WebGL canvas fills its container and is inherently responsive:

- **Desktop browsers**: Chrome 120+, Safari 17+, Firefox 120+
- **Touch support**: Pinch-zoom and swipe-rotate are built into Globe.GL's orbit controls for tablet/mobile browser use
- **Responsive modal**: Full-screen layout on viewports < 768px, centered overlay on larger screens
- **Canvas sizing**: Automatically adapts to window resize events

---

## 5. Data Flow Diagram

```
┌─────────────┐         ┌──────────────────────┐         ┌───────────────┐
│   Browser    │──GET───▶│   Django Backend      │──SQL───▶│  PostgreSQL   │
│ (React App)  │         │  /music-profiles/     │         │ MusicProfile  │
│              │◀──JSON──│       globe/          │◀────────│ (city_lat/lng │
│  Globe.GL    │         │  LOD filtering        │         │  clout/genre) │
│  renderer    │         │  + bbox query         │         │               │
└─────────────┘         └──────────────────────┘         └───────────────┘
       │
       │ (on click)
       ▼
┌──────────────────────┐
│  GET /music-profiles/ │
│      <username>/      │
│      → Modal          │
└──────────────────────┘
```

---

## 6. File Change Summary

### Backend (modified/new files)

| File | Action | Description |
|------|--------|-------------|
| `backend/juke_auth/models.py` | Modify | Add `city_lat`, `city_lng`, `clout` fields + `save()` rounding |
| `backend/juke_auth/serializers.py` | Modify | Add `clout`, `top_genre` to `MusicProfileSerializer`; new `GlobePointSerializer` |
| `backend/juke_auth/views.py` | Modify | Add `globe` action to `MusicProfileViewSet` with LOD + bbox filtering |
| `backend/juke_auth/migrations/000X_*.py` | New | Migration for new fields |
| `backend/juke_auth/management/commands/seed_world_data.py` | New | Seeder for 50K synthetic users |

No new Django app, no new URL config files — everything extends the existing `juke_auth` module.

### Frontend (new/modified files)

| File | Action | Description |
|------|--------|-------------|
| `web/package.json` | Modify | Add `react-globe.gl`, `three` dependencies |
| `web/src/router.tsx` | Modify | Add `/world` route |
| `web/src/features/world/` | New (dir) | Entire world feature module |
| `web/src/features/world/routes/JukeWorldRoute.tsx` | New | Route component |
| `web/src/features/world/components/JukeGlobe.tsx` | New | Globe visualization |
| `web/src/features/world/components/GlobeOverlayNav.tsx` | New | Transparent top nav (logo + back) |
| `web/src/features/world/components/GlobeControls.tsx` | New | UI controls overlay |
| `web/src/features/world/components/UserPinTooltip.tsx` | New | Hover tooltip |
| `web/src/features/world/components/UserDetailModal.tsx` | New | Click detail modal |
| `web/src/features/world/hooks/useGlobePoints.ts` | New | LOD data fetching |
| `web/src/features/world/hooks/useUserDetail.ts` | New | User detail fetching |
| `web/src/features/world/api/worldApi.ts` | New | API client functions |
| `web/src/features/world/types.ts` | New | TypeScript types |
| `web/src/features/world/constants.ts` | New | Genre colors, thresholds |
| `web/src/features/app/components/Sidebar.tsx` | Modify | Add "Juke World" nav link |

### Static Assets

| File | Action | Description |
|------|--------|-------------|
| `web/public/earth-dark.jpg` | New | Dark earth texture for globe background |

---

## 7. Migration & Deployment Notes

1. Run `python manage.py makemigrations juke_auth` to generate migration for `city_lat`, `city_lng`, `clout`
2. Run `python manage.py migrate` to apply
3. Run `python manage.py seed_world_data` to populate 50K synthetic users for testing
4. Frontend: `npm install` to add `react-globe.gl` and `three` dependencies, then `npm run dev` to verify
5. Docker: No new services required. The `web` and `backend` containers handle everything.

---

## 8. Security & Privacy Considerations

- The `/music-profiles/globe/` endpoint requires authentication (`IsAuthenticated`) — no anonymous access to user locations
- **City-level privacy**: All coordinates are rounded to 2 decimal places (~1.1km) on `save()`, enforced at the model level. Precise addresses can never be stored or leaked.
- Latitude/longitude are voluntarily provided by users (not auto-detected)
- The detail on-click uses the existing `/music-profiles/<username>/` endpoint — no new attack surface
- Rate limiting on the globe endpoint (via Django REST throttling) to prevent scraping: 60 requests/minute per user

---

## 9. Future Considerations (Out of Scope)

- Real-time updates via WebSocket (live pin appearance)
- Clustering algorithms (server-side spatial aggregation)
- Heatmap layer alternative view
- User opt-out of globe visibility
- Geolocation auto-detect (browser Geolocation API)
- Native mobile WebView integration (iOS/Android)

---

## 10. Design Decisions (Resolved)

| # | Question | Decision |
|---|----------|----------|
| 1 | Globe texture style | Stylized dark/minimal (maximizes pin visibility) |
| 2 | Authentication on `/music-profiles/globe/` | Required (`IsAuthenticated`) |
| 3 | Seed data volume | 50K synthetic users (sufficient for demo) |
| 4 | Mobile native WebView | Not in scope — frontend web app only for V1 |
| 5 | Location privacy | City-level only — `city_lat`/`city_lng` rounded to 2 decimal places on save |
| 6 | API prefix | Reuse existing `/api/v1/music-profiles/` — no separate `/world/` app |
| 7 | Page layout | Full-screen (outside `AppLayout`); transparent overlay nav bar for consistency |

