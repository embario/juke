# Juke Catalog Redesign - Architecture Document

## Executive Summary

This document outlines the architecture for redesigning the Juke Music Platform catalog experience to create an intuitive, navigable music discovery interface with specialized views for different resource types (Genre, Artist, Album, Track) and integrated Spotify playback capabilities.

### 🚧 CURRENT IMPLEMENTATION STATUS
**Date**: 2026-02-02
**Phase**: Phase 1 - Backend Setup (71% Complete)
**Status**: 5 of 7 tasks complete - Ready for next agent

**✅ COMPLETED**:
- Architecture documentation (all 19 decisions approved)
- Search history models (migrated to database)
- Search history API endpoint (fully functional)
- Detail enrichment service (ready for integration)

**🔲 REMAINING**:
- Task #6: Enhance catalog viewsets for detail endpoints (2-3 hours)
- Task #7: Add backend tests (3-4 hours)

**📖 FOR NEXT AGENT**: Read `docs/arch/HANDOFF_INSTRUCTIONS.md` first for complete handoff details.

### Approved Design Decisions
- **UI Design**: Card-Based Navigation (Option 1) with Spotify-inspired layout
- **Theme**: Match current Juke web app theme and color palette
- **Platform Priority**: Desktop-first development (mobile uses native apps)
- **Resource Descriptions**: 3-5 sentence lorem ipsum placeholders (LLM hydration is future task)
- **Related Albums**: Use existing recommender engine
- **Caching**: Database-level using custom_data fields (follows existing backend pattern)
- **Search History**: Models in catalog app, hybrid POST strategy
- **Deployment**: Replace current /catalog route with new design

## Current State Analysis

### Existing Implementation
- **Frontend**: React 18 + TypeScript with Vite build system
- **Current Catalog Features**:
  - Search bar with filter chips (albums, artists, tracks)
  - Flat list display of search results
  - Basic cards for Artist, Album, and Track resources
  - No Genre support in UI (backend has Genre endpoint but frontend doesn't use it)
  - No detailed views for any resource type
  - No navigation history or breadcrumb system
  - No search history tracking

### Pain Points
1. All resources displayed identically (flattened experience)
2. No resource-specific detailed views
3. No navigation between related resources
4. Spotify playback integration incomplete
5. No search history persistence
6. Generic UX that doesn't promote discovery

## Proposed Architecture

### 1. Frontend Component Architecture

#### 1.1 Navigation & Routing Structure

```
/catalog (LibraryRoute - Home/Search View)
  ├── SearchBar with Genre support
  ├── Navigation Stack Display (Breadcrumbs)
  └── Current View (Search Results or Detail View)

/catalog/genre/:id (GenreDetailView)
  ├── Genre blurb/description
  ├── Top 5 artists by popularity
  └── Related resources

/catalog/artist/:id (ArtistDetailView)
  ├── Artist blurb/bio
  ├── Discography (navigable albums)
  ├── Related artists
  ├── Related genres
  └── Playback controls (top 5 hits if Spotify connected)

/catalog/album/:id (AlbumDetailView)
  ├── Album blurb/description
  ├── Track list (playable)
  ├── Related albums
  └── Playback controls (play full album if Spotify connected)

No Track detail view - Album is the base of navigation stack
```

#### 1.2 Core Component Structure

```
web/src/features/catalog/
├── routes/
│   ├── LibraryRoute.tsx (updated - search home)
│   ├── GenreDetailRoute.tsx (new)
│   ├── ArtistDetailRoute.tsx (new)
│   └── AlbumDetailRoute.tsx (new)
├── components/
│   ├── SearchBar.tsx (updated - add Genre support)
│   ├── NavigationStack.tsx (new - breadcrumb navigation)
│   ├── ResultsPanel.tsx (updated)
│   ├── GenreCard.tsx (new)
│   ├── ArtistCard.tsx (updated - clickable)
│   ├── AlbumCard.tsx (updated - clickable)
│   ├── TrackCard.tsx (updated - clickable, playback)
│   ├── GenreDetailView.tsx (new)
│   ├── ArtistDetailView.tsx (new)
│   ├── AlbumDetailView.tsx (new)
│   ├── RelatedResources.tsx (new - reusable)
│   ├── PlaybackControls.tsx (new)
│   └── ResourceBlurb.tsx (new)
├── context/
│   ├── CatalogSearchContext.tsx (updated)
│   ├── NavigationStackContext.tsx (new)
│   └── SearchHistoryContext.tsx (new)
├── hooks/
│   ├── useCatalogSearch.ts (updated)
│   ├── useNavigationStack.ts (new)
│   ├── useSearchHistory.ts (new)
│   ├── useGenreDetail.ts (new)
│   ├── useArtistDetail.ts (new)
│   ├── useAlbumDetail.ts (new)
│   └── useSpotifyPlayback.ts (new)
├── api/
│   ├── catalogApi.ts (updated - add Genre, detail endpoints)
│   ├── searchHistoryApi.ts (new)
│   └── playbackApi.ts (new)
└── types.ts (updated - add navigation types)
```

### 2. State Management Architecture

#### 2.1 Navigation Stack
The navigation stack tracks the user's discovery journey:

```typescript
type NavigationStackItem = {
  resourceType: 'search' | 'genre' | 'artist' | 'album';
  resourceId?: string | number;
  resourceName: string;
  searchQuery?: string; // For search view
  timestamp: number;
};

type NavigationStack = NavigationStackItem[];
```

**Behavior**:
- Stack starts empty (home/search view)
- Clicking a resource pushes it onto the stack
- Back button pops from stack
- Close (X) button clears stack and returns to home
- Stack is maintained in context, not URL (for UX reasons)
- Stack is used to build breadcrumb navigation

#### 2.2 Search History Tracking

```typescript
type SearchHistoryEntry = {
  searchQuery: string;
  timestamp: string;
  engagedResources: Array<{
    resourceType: 'genre' | 'artist' | 'album' | 'track';
    resourceId: string | number;
    resourceName: string;
  }>;
};
```

**Behavior**:
- Track all resources clicked during a search session
- Session ends when:
  - User performs a new search
  - User clicks unrelated resource (not from current search results)
  - User clicks close (X) to return home
- When session ends, POST to `/api/v1/search-history/` endpoint
- Frontend buffers the current search session in context

### 3. Backend API Architecture

#### 3.1 New Endpoints

**Search History Endpoint**
```
POST /api/v1/search-history/
Body: {
  search_query: string,
  engaged_resources: Array<{
    resource_type: 'genre' | 'artist' | 'album' | 'track',
    resource_id: number,
    resource_name: string
  }>
}
Response: 201 CREATED
```

**Enhanced Detail Endpoints**
```
GET /api/v1/genres/:id/?external=true
Response: {
  id, name, spotify_id, spotify_data,
  description: string, // Generated/fetched
  top_artists: Artist[], // Top 5 by popularity
  related_genres: Genre[]
}

GET /api/v1/artists/:id/?external=true
Response: {
  id, name, spotify_id, spotify_data,
  bio: string, // From Spotify or generated
  albums: Album[], // Discography
  top_tracks: Track[], // Top 5 for playback
  related_artists: Artist[],
  genres: Genre[]
}

GET /api/v1/albums/:id/?external=true
Response: {
  id, name, spotify_id, spotify_data,
  description: string, // Album details
  tracks: Track[], // Full track list
  artists: Artist[],
  related_albums: Album[] // Similar albums
}

GET /api/v1/tracks/:id/?external=true
Response: {
  // Same as current, track detail not needed in UI
  // But used for playback
}
```

#### 3.2 Backend Implementation Plan

**Search History Models (in catalog app)**
```python
# backend/catalog/models.py
class SearchHistory(models.Model):
    user = models.ForeignKey(JukeUser, on_delete=models.CASCADE)
    search_query = models.CharField(max_length=500)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-timestamp']
        indexes = [
            models.Index(fields=['user', '-timestamp']),
        ]

class SearchHistoryResource(models.Model):
    search_history = models.ForeignKey(
        SearchHistory,
        related_name='engaged_resources',
        on_delete=models.CASCADE
    )
    resource_type = models.CharField(
        max_length=20,
        choices=[
            ('genre', 'Genre'),
            ('artist', 'Artist'),
            ('album', 'Album'),
            ('track', 'Track'),
        ]
    )
    resource_id = models.IntegerField()
    resource_name = models.CharField(max_length=500)
```

Note: Search history models are part of the catalog app to keep related functionality together and follow YAGNI principle.

**Enhanced Catalog Services**
```python
# backend/catalog/services/detail_enrichment.py
class ResourceDetailService:
    @staticmethod
    def enrich_genre(genre):
        """
        Enrich genre with description and top 5 artists.
        Uses database caching via custom_data field.
        """
        # Check if description exists in custom_data
        if not genre.custom_data.get('description'):
            genre.custom_data['description'] = generate_lorem_ipsum(3, 5)
            genre.save()

        # Get top 5 artists by Spotify popularity
        top_artists = Artist.objects.filter(
            genres__contains=genre.name
        ).order_by('-spotify_data__popularity')[:5]

        return {
            'description': genre.custom_data['description'],
            'top_artists': top_artists
        }

    @staticmethod
    def enrich_artist(artist):
        """
        Enrich artist with bio, albums, top tracks, related artists.
        Uses database caching via custom_data field.
        """
        # Check if bio exists in custom_data
        if not artist.custom_data.get('bio'):
            artist.custom_data['bio'] = generate_lorem_ipsum(3, 5)
            artist.save()

        # Get discography
        albums = Album.objects.filter(
            artists__id=artist.id
        ).order_by('-release_date')

        # Get top tracks (from Spotify API if not cached)
        if not artist.custom_data.get('top_tracks_ids'):
            # Fetch from Spotify and cache IDs
            pass

        # Get related artists (from Spotify API if not cached)
        if not artist.custom_data.get('related_artist_ids'):
            # Fetch from Spotify and cache IDs
            pass

        return {
            'bio': artist.custom_data['bio'],
            'albums': albums,
            'top_tracks': [],  # Fetch based on cached IDs
            'related_artists': []  # Fetch based on cached IDs
        }

    @staticmethod
    def enrich_album(album):
        """
        Enrich album with description, tracks, related albums.
        Uses database caching and recommender engine for related albums.
        """
        # Check if description exists in custom_data
        if not album.custom_data.get('description'):
            album.custom_data['description'] = generate_lorem_ipsum(3, 5)
            album.save()

        # Get tracks
        tracks = Track.objects.filter(album=album).order_by('track_number')

        # Get related albums from recommender engine
        # TODO: Integrate with recommender/services
        related_albums = []

        return {
            'description': album.custom_data['description'],
            'tracks': tracks,
            'related_albums': related_albums
        }
```

Note: This follows the existing backend pattern of checking database first (custom_data field) before making external API calls. Lorem ipsum descriptions are temporary placeholders for future LLM-generated content.

### 4. Spotify Integration Architecture

#### 4.1 Playback Integration Points

**Check Spotify Connection**
```typescript
// Frontend checks user auth state for Spotify credentials
const { hasSpotifyAuth } = useAuth();
```

**Playback Controls**
```typescript
// Use existing PlaybackViewSet endpoints
POST /api/v1/catalog/playback/play/
Body: {
  track_uri?: string,      // For single track
  context_uri?: string,    // For album/artist
  device_id?: string,
  provider: 'spotify'
}
```

**Conditional UI Rendering**
```typescript
if (hasSpotifyAuth) {
  // Show play buttons on tracks, albums, artists
  // Enable playback controls
} else {
  // Show "Connect Spotify to play" message
  // Disable playback buttons
}
```

### 5. UI/UX Flow Architecture

#### 5.1 Primary User Journey

```
1. User lands on home (/catalog)
   - Sees search bar
   - Can search for any resource (now including Genres)
   - Empty navigation stack

2. User searches "jazz"
   - Results show: Genres, Artists, Albums, Tracks matching "jazz"
   - Search session begins tracking

3. User clicks "Jazz" genre
   - Navigation stack: [Search: "jazz"] → [Genre: Jazz]
   - Genre detail view shows:
     - Description of Jazz genre
     - Top 5 jazz artists (clickable)
     - Breadcrumb: Home > Search: "jazz" > Genre: Jazz
     - Close (X) button in top right

4. User clicks artist "Miles Davis"
   - Navigation stack: [Search: "jazz"] → [Genre: Jazz] → [Artist: Miles Davis]
   - Artist detail view shows:
     - Miles Davis bio
     - Discography (albums as cards)
     - Related artists
     - Related genres
     - If Spotify connected: Play top 5 hits button
     - Breadcrumb: Home > Search: "jazz" > Genre: Jazz > Artist: Miles Davis
     - Back button (goes to Genre: Jazz)
     - Close (X) button (goes to Home)

5. User clicks album "Kind of Blue"
   - Navigation stack: [Search: "jazz"] → [Genre: Jazz] → [Artist: Miles Davis] → [Album: Kind of Blue]
   - Album detail view shows:
     - Album description
     - Full track list (each track playable if Spotify connected)
     - Related albums
     - If Spotify connected: Play album button
     - Breadcrumb with full path
     - Back button (goes to Artist: Miles Davis)
     - Close (X) button (goes to Home)

6. User clicks close (X)
   - Returns to home
   - Search history entry created and POSTed to backend:
     {
       search_query: "jazz",
       engaged_resources: [
         { type: 'genre', id: 123, name: 'Jazz' },
         { type: 'artist', id: 456, name: 'Miles Davis' },
         { type: 'album', id: 789, name: 'Kind of Blue' }
       ]
     }
   - Navigation stack cleared
```

#### 5.2 Search History Tracking Rules

**Start new session when**:
- User performs a new search
- Previous session is POSTed

**Track resource engagement**:
- User clicks any Genre, Artist, Album, or Track card
- Add to current session's engaged_resources array

**End session and POST when**:
- User performs new search (POST old session, start new)
- User clicks close (X) button (POST session, clear)
- User navigates to unrelated resource (edge case, POST session)

### 6. Data Flow Architecture

```
User Action (Search "jazz")
    ↓
SearchBar component
    ↓
useCatalogSearch hook
    ↓
catalogApi.fetchAllCatalogResources()
    ↓
Backend: GET /api/v1/{genres,artists,albums,tracks}/?search=jazz&external=true
    ↓
Backend calls Spotify API via controller
    ↓
Returns results to frontend
    ↓
ResultsPanel displays Genre, Artist, Album, Track cards
    ↓
User clicks Genre "Jazz"
    ↓
NavigationStack.push({ type: 'genre', id: 123, name: 'Jazz' })
    ↓
SearchHistory.trackEngagement({ type: 'genre', id: 123, name: 'Jazz' })
    ↓
Navigate to GenreDetailRoute
    ↓
useGenreDetail hook fetches genre details
    ↓
Backend: GET /api/v1/genres/123/?external=true
    ↓
Backend enriches with description, top_artists via ResourceDetailService
    ↓
GenreDetailView displays content
    ↓
User clicks close (X)
    ↓
SearchHistory.endSession() → POST to /api/v1/search-history/
    ↓
NavigationStack.clear()
    ↓
Navigate to home
```

### 7. Resource Blurb/Description Strategy

For each resource type, descriptions/blurbs will be sourced as follows:

**Genres**:
- Check if Genre.custom_data contains 'description'
- Otherwise, generate a brief description based on genre characteristics
- Could integrate with Spotify Web API (no direct genre description, but can infer from top artists)
- Fallback: "Explore the {genre_name} genre"

**Artists**:
- Spotify Web API doesn't provide artist bios directly
- Use Spotify data (popularity, genres, follower count) to create a summary
- Could integrate third-party APIs (MusicBrainz, Last.fm) for richer bios
- Store in Artist.custom_data['bio'] once fetched
- Fallback: "Artist in the {genres} genre(s)"

**Albums**:
- Use Spotify album data (release date, label, total tracks)
- Could fetch additional metadata from MusicBrainz
- Store in Album.custom_data['description']
- Fallback: "Album by {artists}, released {date}"

**Implementation Approach (Approved)**:
- **Genres**: 3-5 sentence lorem ipsum stored in `Genre.custom_data['description']`
- **Artists**: 3-5 sentence lorem ipsum stored in `Artist.custom_data['bio']`
- **Albums**: 3-5 sentence lorem ipsum stored in `Album.custom_data['description']`
- **Fallback**: Show "Description unavailable" if custom_data is empty
- **Future**: LLM-generated descriptions will replace lorem ipsum in a future task

### 8. Related Resources Strategy

**Genre → Top Artists (Approved)**:
- Query `Artist.objects.filter(genres__contains=genre.name)`
- Order by Spotify popularity score: `.order_by('-spotify_data__popularity')`
- Return top 5 artists
- Popularity score from Spotify data is the ranking criteria

**Artist → Related Artists**:
- Spotify API: GET /artists/{id}/related-artists
- Cache IDs in `Artist.custom_data['related_artist_ids']`
- Fetch full Artist objects from database for display
- Follows existing database-first caching pattern

**Artist → Genres**:
- Already available: `Artist.genres` relationship

**Album → Related Albums (Approved)**:
- **Primary**: Use existing recommender engine (Option A)
- **Fallback**: If recommender unavailable, use simple heuristics:
  - Albums by same artist
  - Albums in same genre with similar popularity
- Limit to 5-10 albums for UI display

### 9. Technology Stack Decisions

#### Frontend Dependencies (Additions)
- **None required** - leverage existing React Router, Context API, fetch API
- Optional: `react-query` for better caching/state management (if UX needs it)

#### Backend Dependencies (Additions)
- **None required for MVP** - use existing Django, DRF, Celery stack
- Optional Phase 2: Third-party metadata APIs (Last.fm, MusicBrainz)

### 10. Testing Strategy

#### Frontend Testing
```
web/src/features/catalog/tests/
├── NavigationStack.test.tsx
├── SearchHistory.test.tsx
├── GenreDetailView.test.tsx
├── ArtistDetailView.test.tsx
├── AlbumDetailView.test.tsx
├── PlaybackControls.test.tsx
└── integration/
    └── CatalogFlow.test.tsx
```

#### Backend Testing
```
backend/tests/api/
├── test_search_history_api.py
├── test_genre_detail_api.py
├── test_artist_detail_api.py
└── test_album_detail_api.py

backend/tests/unit/
└── test_detail_enrichment_service.py
```

### 11. Performance Considerations

**Frontend**:
- Lazy load detail views (code splitting)
- Cache search results in context (avoid refetch on back navigation)
- Debounce search input
- Virtualize long track lists on album detail

**Backend (Approved Caching Strategy)**:
- **Database-level caching**: Store enriched data in `custom_data` JSON fields
- Check `custom_data` first before making external API calls
- Use `select_related`/`prefetch_related` for Django ORM queries
- Add database indexes on search fields
- Follows existing backend pattern: DB first, then Spotify API if needed
- **No Redis caching required** - existing pattern is sufficient

**Search History (Approved)**:
- Hybrid approach: Buffer in localStorage, POST on session end or every N resources
- POST asynchronously (don't block UI)
- Keep indefinitely for long-term analytics

### 12. Accessibility Considerations

- Breadcrumb navigation with proper ARIA labels
- Keyboard navigation support (arrow keys, enter, escape)
- Screen reader announcements for navigation changes
- Focus management when navigating between views
- Sufficient color contrast for all UI elements
- Alt text for all images (album art, artist photos)

### 13. Responsive Design (Approved)

**Development Priority**: Desktop-first
- Primary development and testing on desktop
- Mobile web will use same card-based design
- Mobile users primarily use native apps (iOS/Android)
- Responsive breakpoints for tablet/mobile web as secondary priority

**Card-based design works across devices**:
- Cards stack vertically on smaller screens
- Breadcrumb navigation remains consistent
- Touch-friendly tap targets for mobile web users
- Bottom sheet for playback controls if on mobile web

### 14. Error Handling

**Frontend**:
- Graceful degradation if Spotify API fails
- Fallback UI for missing images/descriptions
- Clear error messages for failed searches
- Retry mechanism for API failures

**Backend**:
- Proper error responses with status codes
- Logging for debugging
- Fallback to cached data if external API fails
- Rate limiting for search history endpoint

### 15. Security Considerations

**Search History**:
- Ensure user can only POST their own search history
- Validate resource_type enum on backend
- Sanitize search_query input
- Rate limit to prevent abuse

**Spotify Playback (Approved)**:
- Verify user owns Spotify credentials before playback
- **Premium Check**: Show upgrade prompt if user lacks Spotify Premium
- Users can search and browse catalog without Premium
- Playback requires Premium (Spotify Web Playback SDK requirement)
- **Device Selection**: Auto-play on user's active Spotify device
- Use existing OAuth flow (already implemented)
- Don't expose Spotify tokens to frontend beyond what's necessary

### 16. Migration & Rollout Plan

**Phase 1: Backend Setup**
1. Add SearchHistory models to catalog app
2. Create and run migrations
3. Implement search history API endpoint
4. Create detail enrichment service
5. Enhance detail endpoints with enrichment
6. Add tests
7. Deploy to staging

**Phase 2: Frontend Core**
1. Update types and API client
2. Implement navigation stack context
3. Implement search history context
4. Update SearchBar to support Genres
5. Update existing card components (make clickable)
6. Add tests

**Phase 3: Detail Views**
1. Implement GenreDetailRoute and view
2. Implement ArtistDetailRoute and view
3. Implement AlbumDetailRoute and view
4. Add navigation breadcrumbs
5. Add tests

**Phase 4: Playback Integration**
1. Implement PlaybackControls component
2. Add playback to Track cards
3. Add playback to Album detail
4. Add playback to Artist detail (top tracks)
5. Add tests

**Phase 5: Polish & Deploy**
1. Styling and animations
2. Performance optimization
3. Accessibility audit
4. End-to-end testing
5. Deploy to production

### 17. Approved Decisions Summary

All key architectural decisions have been approved:

1. **Design Style**: Card-Based Navigation (Option 1)
2. **Theme**: Match current Juke web app theme and color palette
3. **Platform Priority**: Desktop-first development
4. **Resource Descriptions**: 3-5 sentence lorem ipsum (future: LLM-generated)
5. **Related Albums**: Use recommender engine (Option A)
6. **Top Artists Ranking**: Spotify popularity score
7. **Caching Strategy**: Database-level using custom_data fields
8. **Search History Location**: Models in catalog app (not separate app)
9. **Search History POST**: Hybrid approach with localStorage
10. **Navigation Stack Limit**: Cap at 10 items
11. **Missing Descriptions**: Show "Description unavailable"
12. **No Spotify Premium**: Show upgrade prompt, allow browse but not playback
13. **Playback Device**: Auto-play on active device
14. **Search History Retention**: Keep indefinitely
15. **Image URLs**: Use Spotify CDN URLs directly
16. **Pagination**: Show first 10 + "View All" button
17. **Implementation Scope**: All resource types (Genre, Artist, Album) in parallel
18. **Testing Focus**: Navigation stack, search history tracking, playback integration
19. **Current Catalog**: Replace with new design on /catalog route

### 18. Success Metrics

**User Engagement**:
- Average navigation depth (resources clicked per search)
- Search-to-click rate
- Time spent in catalog
- Return visit rate

**Feature Adoption**:
- % of users with Spotify connected who use playback
- Average tracks played per session
- Genre exploration rate

**Technical**:
- Page load time for detail views
- API response times
- Search history API success rate
- Frontend error rate

## Conclusion

This architecture provides a comprehensive foundation for redesigning the Juke Music Platform catalog into an intuitive, navigable music discovery experience. The design leverages existing infrastructure while adding new capabilities for detailed resource views, navigation tracking, and integrated playback.

Key strengths:
- Clean separation of concerns
- Scalable component architecture
- Backward compatible with existing APIs
- Performance-conscious design
- Comprehensive tracking for future personalization

Next steps:
- Review and approve this architecture
- Design UI/UX mockups
- Begin Phase 1 implementation
