# Juke Catalog Redesign - Implementation Task List

## Overview

This document tracks all implementation tasks across 5 phases for the catalog redesign project.

**Estimated Timeline**: 4-6 weeks
**Status**: Phase 1 - Backend Setup (In Progress)

---

## Phase 1: Backend Setup (3-5 days)

### 1.1 Database Models
- [ ] Add SearchHistory model to backend/catalog/models.py
- [ ] Add SearchHistoryResource model to backend/catalog/models.py
- [ ] Create migration file
- [ ] Run migrations in development environment
- [ ] Test models in Django shell

### 1.2 Serializers
- [ ] Create SearchHistorySerializer in catalog/serializers.py
- [ ] Create SearchHistoryResourceSerializer
- [ ] Add validation for resource_type choices
- [ ] Test serializers with sample data

### 1.3 Search History API
- [ ] Create SearchHistoryViewSet in catalog/views.py
- [ ] Implement POST endpoint for creating search history
- [ ] Add authentication requirement (IsAuthenticated)
- [ ] Associate search history with request.user
- [ ] Register viewset in catalog/urls.py
- [ ] Test endpoint with curl/Postman

### 1.4 Detail Enrichment Service
- [ ] Create catalog/services/detail_enrichment.py
- [ ] Implement ResourceDetailService class
- [ ] Implement enrich_genre() method (description + top 5 artists)
- [ ] Implement enrich_artist() method (bio + albums + related)
- [ ] Implement enrich_album() method (description + tracks + related)
- [ ] Create helper: generate_lorem_ipsum() utility
- [ ] Add database-first caching logic (check custom_data)
- [ ] Test enrichment methods

### 1.5 Enhanced Detail Endpoints
- [ ] Update GenreViewSet.retrieve() to return enriched data
- [ ] Update ArtistViewSet.retrieve() to return enriched data
- [ ] Update AlbumViewSet.retrieve() to return enriched data
- [ ] Update serializers to include new fields (description, top_artists, etc.)
- [ ] Test detail endpoints with ?external=true
- [ ] Verify caching behavior (custom_data population)

### 1.6 Spotify API Integration
- [ ] Add method to fetch artist's top tracks from Spotify
- [ ] Add method to fetch related artists from Spotify
- [ ] Cache Spotify IDs in custom_data fields
- [ ] Handle rate limiting gracefully
- [ ] Add error handling for failed API calls

### 1.7 Recommender Engine Integration
- [ ] Check if recommender engine supports album recommendations
- [ ] Integrate recommender for related albums in enrich_album()
- [ ] Add fallback heuristics if recommender unavailable
- [ ] Test related albums response

### 1.8 Backend Tests
- [ ] Create tests/api/test_search_history_api.py
- [ ] Test POST /api/v1/catalog/search-history/
- [ ] Test authentication requirement
- [ ] Test resource validation
- [ ] Create tests/unit/test_detail_enrichment.py
- [ ] Test enrich_genre() logic
- [ ] Test enrich_artist() logic
- [ ] Test enrich_album() logic
- [ ] Test caching behavior (custom_data)
- [ ] Update existing catalog tests for new serializer fields
- [ ] Run full test suite: `docker compose exec backend python manage.py test`

### 1.9 Documentation & Deployment
- [ ] Update backend/catalog/README.md (if exists)
- [ ] Add API documentation for search history endpoint
- [ ] Deploy to staging environment
- [ ] Smoke test all new endpoints on staging
- [ ] Review with stakeholder

---

## Phase 2: Frontend Core (5-7 days)

### 2.1 Type Definitions
- [ ] Update web/src/types/catalog.ts with Genre support
- [ ] Add NavigationStackItem type
- [ ] Add SearchHistoryEntry type
- [ ] Add enriched resource types (GenreDetail, ArtistDetail, AlbumDetail)
- [ ] Export all new types

### 2.2 API Client Updates
- [ ] Update catalogApi.fetchAllCatalogResources() to include genres
- [ ] Add catalogApi.fetchGenreDetail(id)
- [ ] Add catalogApi.fetchArtistDetail(id)
- [ ] Add catalogApi.fetchAlbumDetail(id)
- [ ] Create searchHistoryApi.ts with postSearchHistory()
- [ ] Test API client methods

### 2.3 Navigation Stack Context
- [ ] Create context/NavigationStackContext.tsx
- [ ] Implement push() to add items to stack
- [ ] Implement pop() to go back one level
- [ ] Implement clear() to reset to home
- [ ] Implement getPath() for breadcrumb generation
- [ ] Cap stack at 10 items
- [ ] Create hooks/useNavigationStack.ts
- [ ] Test navigation logic

### 2.4 Search History Context
- [ ] Create context/SearchHistoryContext.tsx
- [ ] Implement startSession() on new search
- [ ] Implement trackEngagement() on resource click
- [ ] Implement endSession() to POST to backend
- [ ] Add localStorage backup for reliability
- [ ] Implement hybrid batching logic
- [ ] Create hooks/useSearchHistory.ts
- [ ] Test tracking and POST logic

### 2.5 Router Updates
- [ ] Update web/src/router.tsx
- [ ] Add route: /catalog/genre/:id → GenreDetailRoute
- [ ] Add route: /catalog/artist/:id → ArtistDetailRoute
- [ ] Add route: /catalog/album/:id → AlbumDetailRoute
- [ ] Keep existing /catalog route for LibraryRoute
- [ ] Test routing navigation

### 2.6 SearchBar Updates
- [ ] Update components/SearchBar.tsx
- [ ] Add "Genres" to filter options
- [ ] Update filter state management
- [ ] Ensure genre filter is included in API calls
- [ ] Test search with genre filter enabled

### 2.7 Card Component Updates
- [ ] Create components/GenreCard.tsx (new)
- [ ] Update ArtistCard.tsx to be clickable (wrap in Link)
- [ ] Update AlbumCard.tsx to be clickable (wrap in Link)
- [ ] Update TrackCard.tsx to be clickable (if needed)
- [ ] Add onClick handlers to track engagement
- [ ] Test card click navigation

### 2.8 ResultsPanel Updates
- [ ] Update components/ResultsPanel.tsx
- [ ] Add genres section to display genre cards
- [ ] Update layout to show genres first
- [ ] Ensure existing sections still work
- [ ] Test with genre results included

### 2.9 Frontend Tests
- [ ] Test NavigationStack context (push/pop/clear)
- [ ] Test SearchHistory context (track/post)
- [ ] Test updated SearchBar with genres
- [ ] Test card components are clickable
- [ ] Test ResultsPanel shows all resource types
- [ ] Run: npm test

---

## Phase 3: Detail Views (7-10 days)

### 3.1 Navigation Breadcrumb Component
- [ ] Create components/NavigationStack.tsx
- [ ] Display breadcrumb trail from navigation context
- [ ] Make each breadcrumb item clickable (navigate backwards)
- [ ] Add Close (X) button to clear stack
- [ ] Style consistently with current Juke theme
- [ ] Handle long paths gracefully
- [ ] Test breadcrumb navigation
- [ ] Add tests for NavigationStack component

### 3.2 Resource Blurb Component
- [ ] Create components/ResourceBlurb.tsx
- [ ] Display description text
- [ ] Handle "Description unavailable" fallback
- [ ] Style with appropriate typography
- [ ] Make reusable across resource types
- [ ] Test with and without description

### 3.3 Related Resources Component
- [ ] Create components/RelatedResources.tsx
- [ ] Accept resource type and list as props
- [ ] Display as horizontal scrollable card list
- [ ] Make each item clickable
- [ ] Add "View All" button if list is truncated
- [ ] Style consistently
- [ ] Test with different resource types

### 3.4 Genre Detail View
- [ ] Create routes/GenreDetailRoute.tsx
- [ ] Create components/GenreDetailView.tsx
- [ ] Create hooks/useGenreDetail.ts to fetch data
- [ ] Display genre name and icon
- [ ] Display description using ResourceBlurb
- [ ] Display top 5 artists (ranked by popularity)
- [ ] Each artist card is clickable → navigates to artist detail
- [ ] Add NavigationStack breadcrumb at top
- [ ] Add Back button
- [ ] Add Close (X) button
- [ ] Handle loading state
- [ ] Handle error state
- [ ] Style with Juke theme
- [ ] Test genre detail view
- [ ] Add tests

### 3.5 Artist Detail View
- [ ] Create routes/ArtistDetailRoute.tsx
- [ ] Create components/ArtistDetailView.tsx
- [ ] Create hooks/useArtistDetail.ts to fetch data
- [ ] Display artist photo (large)
- [ ] Display artist name and genres
- [ ] Display follower count
- [ ] Display bio using ResourceBlurb
- [ ] Display discography (albums as cards)
- [ ] Display related artists using RelatedResources
- [ ] Display genres as clickable chips
- [ ] Add NavigationStack breadcrumb at top
- [ ] Add Back button
- [ ] Add Close (X) button
- [ ] Handle loading state
- [ ] Handle error state
- [ ] Style with Juke theme
- [ ] Test artist detail view
- [ ] Add tests

### 3.6 Album Detail View
- [ ] Create routes/AlbumDetailRoute.tsx
- [ ] Create components/AlbumDetailView.tsx
- [ ] Create hooks/useAlbumDetail.ts to fetch data
- [ ] Display album cover art (large)
- [ ] Display album name, artists, year
- [ ] Display description using ResourceBlurb
- [ ] Display track list (numbered)
- [ ] Display related albums using RelatedResources
- [ ] Add NavigationStack breadcrumb at top
- [ ] Add Back button
- [ ] Add Close (X) button
- [ ] Handle loading state
- [ ] Handle error state
- [ ] Style with Juke theme
- [ ] Test album detail view
- [ ] Add tests

### 3.7 Detail View Polish
- [ ] Ensure consistent spacing and layout across all detail views
- [ ] Add smooth transitions (fade in, slide in)
- [ ] Optimize for desktop (primary target)
- [ ] Test responsive behavior on mobile web (secondary)
- [ ] Add skeleton loading states
- [ ] Polish error messages
- [ ] Accessibility audit (keyboard nav, focus management)

---

## Phase 4: Playback Integration (3-5 days)

### 4.1 Spotify Auth Check
- [ ] Update auth context/hooks to expose hasSpotifyAuth
- [ ] Add hasSpotifyPremium check if API supports it
- [ ] Create utility to check active Spotify device
- [ ] Test auth state detection

### 4.2 Playback Controls Component
- [ ] Create components/PlaybackControls.tsx
- [ ] Accept track/album/context URI as props
- [ ] Show play button if Spotify Premium
- [ ] Show "Upgrade to Premium" if no Premium
- [ ] Implement play action (call backend playback API)
- [ ] Handle playback errors gracefully
- [ ] Style consistently with Juke theme
- [ ] Test playback controls

### 4.3 Playback API Integration
- [ ] Create api/playbackApi.ts wrapper
- [ ] Implement playTrack(track_uri)
- [ ] Implement playAlbum(context_uri)
- [ ] Implement playArtistTopTracks(track_uris)
- [ ] Use existing /api/v1/catalog/playback/play/ endpoint
- [ ] Auto-detect active device or use web player
- [ ] Handle device selection if needed
- [ ] Test API calls

### 4.4 Track Playback
- [ ] Update components/TrackCard.tsx
- [ ] Add play button (icon)
- [ ] Show only if hasSpotifyPremium
- [ ] Implement onClick to play track
- [ ] Show loading indicator during playback request
- [ ] Test track playback

### 4.5 Album Playback
- [ ] Update components/AlbumDetailView.tsx
- [ ] Add "Play Album" button in header
- [ ] Show only if hasSpotifyPremium
- [ ] Implement onClick to play full album
- [ ] Show loading indicator
- [ ] Test album playback

### 4.6 Artist Top Tracks Playback
- [ ] Update components/ArtistDetailView.tsx
- [ ] Add "Play Top Tracks" button in header
- [ ] Show only if hasSpotifyPremium
- [ ] Fetch top 5 tracks from enriched data
- [ ] Implement onClick to play top tracks as playlist
- [ ] Show loading indicator
- [ ] Test artist top tracks playback

### 4.7 Global Playback Bar (Optional)
- [ ] Create components/GlobalPlaybackBar.tsx (if not exists)
- [ ] Display currently playing track info
- [ ] Add playback controls (play/pause/skip)
- [ ] Position at bottom of screen
- [ ] Persist across navigation
- [ ] Test global playback state

### 4.8 Playback Tests
- [ ] Test play button only shows for Premium users
- [ ] Test upgrade prompt for non-Premium users
- [ ] Test track playback functionality
- [ ] Test album playback functionality
- [ ] Test artist top tracks playback
- [ ] Test error handling (device unavailable, etc.)
- [ ] Integration test: search → navigate → play

---

## Phase 5: Polish & Deploy (3-5 days)

### 5.1 Styling & Theme Consistency
- [ ] Audit all new components against Juke theme
- [ ] Ensure color palette matches existing app
- [ ] Check typography consistency (fonts, sizes, weights)
- [ ] Verify spacing and padding consistency
- [ ] Check button styles match existing patterns
- [ ] Test dark mode if applicable
- [ ] Review with designer/stakeholder

### 5.2 Animations & Transitions
- [ ] Add fade-in for detail views
- [ ] Add slide-in transition for navigation
- [ ] Add smooth scroll for long content
- [ ] Add hover effects on cards
- [ ] Add loading skeleton animations
- [ ] Keep animations subtle and performant
- [ ] Test animation performance

### 5.3 Responsive Design
- [ ] Test on desktop (1920px, 1440px, 1024px)
- [ ] Test on tablet (768px)
- [ ] Test on mobile web (375px, 414px)
- [ ] Adjust card sizes for different breakpoints
- [ ] Ensure breadcrumbs work on small screens
- [ ] Test touch interactions on mobile
- [ ] Fix any layout issues

### 5.4 Accessibility
- [ ] Full keyboard navigation test (Tab, Enter, Escape)
- [ ] Screen reader test (VoiceOver/NVDA)
- [ ] Focus management on route changes
- [ ] ARIA labels on all interactive elements
- [ ] Alt text on all images
- [ ] Color contrast check (WCAG AA)
- [ ] Skip to content link
- [ ] Fix any accessibility issues

### 5.5 Performance Optimization
- [ ] Lazy load detail view routes
- [ ] Optimize images (use srcset if needed)
- [ ] Check bundle size (avoid bloat)
- [ ] Test API response times
- [ ] Verify caching is working (custom_data)
- [ ] Check for memory leaks (navigation stack)
- [ ] Profile with React DevTools
- [ ] Optimize slow components

### 5.6 Cross-Browser Testing
- [ ] Test on Chrome (latest)
- [ ] Test on Firefox (latest)
- [ ] Test on Safari (latest)
- [ ] Test on Edge (latest)
- [ ] Fix any browser-specific issues

### 5.7 Testing & QA
- [ ] Run full backend test suite
- [ ] Run full frontend test suite
- [ ] End-to-end test: complete user flow (search → genre → artist → album → play)
- [ ] Test search history POST functionality
- [ ] Test navigation stack edge cases (10 item limit)
- [ ] Test error states and edge cases
- [ ] Perform exploratory testing
- [ ] Fix any bugs found

### 5.8 Documentation
- [ ] Update web/README.md with new features
- [ ] Document navigation stack behavior
- [ ] Document search history tracking
- [ ] Add code comments where needed
- [ ] Update API documentation
- [ ] Create user-facing changelog

### 5.9 Deployment
- [ ] Merge feature branch to staging
- [ ] Deploy backend to staging
- [ ] Run migrations on staging
- [ ] Deploy frontend to staging
- [ ] Smoke test on staging environment
- [ ] Get stakeholder approval
- [ ] Merge to main branch
- [ ] Deploy backend to production
- [ ] Run migrations on production
- [ ] Deploy frontend to production
- [ ] Smoke test on production
- [ ] Monitor for errors
- [ ] Announce feature release

---

## Task Summary by Phase

| Phase | Tasks | Estimated Days |
|-------|-------|----------------|
| Phase 1: Backend Setup | 43 tasks | 3-5 days |
| Phase 2: Frontend Core | 41 tasks | 5-7 days |
| Phase 3: Detail Views | 65 tasks | 7-10 days |
| Phase 4: Playback Integration | 30 tasks | 3-5 days |
| Phase 5: Polish & Deploy | 45 tasks | 3-5 days |
| **Total** | **224 tasks** | **21-32 days** |

---

## Current Status

**Phase**: 1 (Backend Setup)
**In Progress**: Creating search history models
**Next Up**: Search history API endpoint

---

## Notes

- All tasks will be tracked in this document and via the task management system
- Each completed task should be checked off
- Blockers should be documented as they arise
- Timeline may adjust based on complexity and findings during implementation
- Regular check-ins with stakeholder after each phase completion
