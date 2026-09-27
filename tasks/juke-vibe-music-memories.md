---
id: juke-vibe-music-memories
title: Build authenticated multimedia music memories in Juke Vibe
status: in_progress
priority: p1
owner: codex
area: clients
label: CLIENTS/BACKEND
complexity: 5
updated_at: 2026-09-17
---

## Goal

Make Juke Vibe an authenticated, personal music-memory experience with multimedia
creation, chronological exploration, reusable tags, and backend connections that
support thoughtful prompts and music discovery.

## Scope

- Require Juke authentication to use the memory experience.
- Attach multiple songs, photos, videos, optional prose, people, and places.
- Observe Spotify and Apple Music through supported integrations.
- Associate memories with the authenticated music profile.
- Provide a Jev integration boundary before database persistence; live model hookup is deferred.
- Allow review/removal of generated tags and reusable user-defined tags.
- Provide chronological multimedia browsing and provider-backed listening.
- Coordinate backend implementation and verification with agents on Neptune.

## Out Of Scope

- iPhone changes in this phase, new catalog browsing, full in-app streaming, Android, or publication.
- Training a substitute for Jev or pretending a heuristic classifier is Jev.
- Automatically uploading prior private chat history for classification.

## Acceptance Criteria

- Signed-out users cannot access another user's memory content or attachments.
- An authenticated user can create and retrieve a memory with multiple songs,
  photo/video attachments, optional prose, and edited tags.
- Saved custom tags are offered on subsequent memories for that same user.
- The classification boundary runs before persistence; unconfigured Jev returns an explicit unavailable status without fabricated tags.
- Memories belong to the user's music profile and supply traceable connections,
  a thoughtful creation prompt, and recommendation-ready signals.
- Chronological browsing renders attachments and song listening actions.
- Focused backend and client tests plus an authenticated end-to-end journey are
  executed, with fixture tests distinguished from live provider/model checks.

## Execution Notes

- Execution mode: ITERATIVE; macOS first, Jev integration boundary only, and both provider opening and playback/segment controls confirmed by the user.
- This request supersedes the older Vibe task's exclusion of memories/timelines.
- Primary paths: `backend/vibe`, `macos/jukevibe`, and macOS integration tests.
- Use Docker on Neptune for backend checks; preserve unrelated local changes.
- Risks: Jev contract/deployment availability;
  provider playback authorization; media storage and account ownership; genuine
  live authenticated E2E credentials and interactive permissions.

## Handoff

- Implemented the macOS-first memory composer, optional text, multiple songs and
  segments, private photo/video attachments, people/place metadata, tag review,
  reusable vocabulary, tag editing, and a searchable chronological multimedia
  catalog with connections and a contextual question. Saved memories open in
  detail immediately; app locking masks sheets and pauses private videos.
- Existing Juke PKCE authentication and encrypted chat are preserved. Memory
  state and cached attachments are cleared on logout; stale attachments are
  removed on launch. Production builds cannot enter the authenticated UI-test
  seam. The iPhone app is unchanged.
- Implemented profile-owned backend memories, authenticated media, Jev adapter
  boundary, prompts/connections, and recommendation-context signals. Jev remains
  unconfigured by explicit user direction; no classifier output is fabricated.
  Ranking/training consumers are not automatically enabled by this slice.
- Verification: 44 macOS unit/contract tests and 25 backend tests pass. Debug and
  Release builds compile; the UI-test bundle builds. The production Swift client
  passed real Juke login → photo/video uploads → multi-song segmented memory →
  list/readback → authenticated image/video decoding → tag edits/reuse → profile
  connections against the isolated Docker backend. Reproduce with
  `scripts/test_vibe_memories_live.sh` and private disposable credentials.
- Live integration caught and fixed uppercase Swift UUID URLs rejected by
  Django's lowercase UUID routes. Other hardening includes account-switch race
  guards, cache cleanup, safe provider references, finite segment bounds,
  chronology pagination, and preservation of explicit tag exclusions.
- UI execution was attempted but failed to initialize automation because the Mac
  is locked (also confirmed by computer-use inspection). User was asked to unlock;
  mouse/keyboard journeys and visual layout checks are still pending. The
  dedicated live UI test is gated and compiled, not claimed as executed.
- Neptune connectivity is restored. The memory backend and both migrations are
  deployed and verified through the real HTTPS endpoint; see deployment record below.
- Playback limits: Spotify controls require connected playback credentials and
  an active device; segment endings use verified polling. Apple Music automatic
  segments require a local library persistent ID and Automation permission;
  catalog links hand off to Music with an explicit explanation.
- Next: complete GUI/visual checks and normal browser-based sign-in and live
  Spotify/Apple Music verification. Keep the task in review until these checks.

### Backend verification and isolated stack handoff

- Implemented authenticated memory APIs, private media, editable/reusable tags,
  Jev boundary, connections/prompts, and recommendation context. API contract and
  complete fresh Docker setup commands: `backend/vibe/MEMORIES.md`.
- Both `ssh Neptune` and `ssh mario@neptune-ext` timed out on port 22. Work and
  tests used the authorized local fallback; nothing was deployed to Neptune.
- Isolated containers: `juke-vibe-test-backend`, `juke-vibe-test-db`, on
  `juke-vibe-test-net`. HTTP endpoint: `http://127.0.0.1:8765`. No workers or
  ingestion jobs were started. Python 3.14 / PostgreSQL 18; source-built psycopg2
  was replaced with psycopg2-binary only inside the disposable test container.
- Exact focused test command for the current running stack:
  ```sh
  docker exec -e MLCORE_PG_HOT_TABLESPACE_HOST_PATH=/tmp/juke-vibe-hot -e MLCORE_PG_COLD_TABLESPACE_HOST_PATH=/tmp/juke-vibe-cold juke-vibe-test-backend python manage.py test tests.api.test_vibe_memories tests.api.test_vibe_api --noinput
  ```
- Additional checks: `docker exec juke-vibe-test-backend python manage.py makemigrations --check --dry-run vibe`,
  `docker exec juke-vibe-test-backend ruff check vibe/memory_models.py vibe/memory_services.py vibe/memory_serializers.py vibe/memory_views.py vibe/urls.py vibe/models.py tests/api/test_vibe_memories.py`.
- Temporary authenticated test account credentials are in
  `/tmp/juke-vibe-test-credentials.json` (mode 600); do not print or commit them.
  Server logs: `docker exec juke-vibe-test-backend tail /tmp/vibe-server.log`.
  Server uses `--noreload`; it was restarted after final backend refinements and
  the production Swift client integration passed again against the latest code.
- Ownership, title-only rejection, supported upload signatures/content headers,
  video byte roundtrip, unattached media cleanup, Jev timeout behavior, segment
  bounds, partial edits, tag vocabulary, and recommendation context are covered.
  Jev itself is unconfigured by design; provider streaming is outside these tests.
- Memory PATCH now locks the owner record while merging partial edits and
  classifying to avoid lost updates across devices. A classification request may
  hold this lock for the configured timeout (default 8 seconds).
- Final backend verification: **25 tests passed** (13 memory tests and 12 existing
  Vibe/auth tests), including 60-character Unicode tags whose casefold expands.
  Ruff, Django system checks, migration drift, and whitespace checks passed.
  Migration `0003_widen_normalized_memory_tag` expands normalized storage to 180
  characters and has been applied to the isolated live test database.

### Connectivity restored and local stack stopped

- Neptune Tailscale reauthentication completed by the user. Verified SSH via
  `mario@neptune-ext` and Neptune `/api/v1/health` HTTP 200.
- Running Mac app targets Neptune. Its `/api/v1/vibe/memories/` route returns
  HTTP 404: local memory backend changes still need deployment and migrations.
- At user request, stopped local `juke-vibe-test-backend` and
  `juke-vibe-test-db`; containers/data retained. No local containers remain
  running. Neptune services were left running.

### Neptune deployment verified — 2026-09-17 00:51 UTC

- User authorized deployment. Staged against Neptune base commit
  `475e55a9c74ec6dcc3cd5e57b27dd5e132478f42`; 25 backend tests passed in an
  isolated database using the live image. Ruff, Django checks and migration drift passed.
- Deployed the 11 scoped backend files to `/srv/juke-dev`; applied Vibe migrations
  0002 and 0003. Django autoreloaded; backend/database containers were not restarted.
  Environment and proxy settings were preserved.
- Rollback source backup and manifest:
  `/home/mario/.local/state/juke-deployments/vibe-memories-20260917T005111Z`.
- Production Swift MemoryClient integration passed against Neptune HTTPS:
  real login, photo/video upload and decoding, multi-song segmented memory,
  readback, tag editing/reuse, and profile connections. Temporary smoke account,
  profile, memories, media and credentials were removed afterward.
- Health returns 200; protected memory routes return 401 unsigned instead of 404.
  Jev remains intentionally unconfigured. Live provider playback and GUI testing
  are not claimed by this API integration test.
- Local Docker containers remain stopped. Running Mac app and its draft were preserved.

### Inline scrapbook redesign — 2026-09-17 (ITERATIVE)

- Goal: replace modal form intake with a playful inline photo/song/story canvas.
- Scope: remove name/place/people/song text fields from creation; description is
  the sole text input. Reuse songs and tags through selections, allow custom
  hashtags in the description. Infer capture dates/location from selected media,
  optionally enrich selected assets with authorized PhotoKit metadata. Never infer
  identities from faces; offer known profile people as selections.
- Acceptance: composer lives in main window; previews, date shortcuts/calendar,
  removable inferred place, tag review, multi-song and media saving work. Manual
  date choices survive later imports; removed media cannot retain stale metadata.
- Out of scope: face recognition/private Photos databases, catalog browsing,
  backend schema changes and live Jev integration.
- Risks: missing/stripped metadata, denied Photos permission, iCloud downloads,
  asynchronous import cancellation; retain file import and story-only paths.
- Verify: metadata/policy tests, Mac unit suite, build, and inline UI journeys.

### Scrapbook redesign handoff — 2026-09-17

- Implemented inline composition and embedded Apple Photos picker, drag/file import,
  tilted media previews, description-only writing, current/reused song selections,
  snippet steppers, feeling chips, and reusable custom hashtags. Removed name,
  place, people, song metadata and tag text boxes from creation. Existing detail
  tag editing remains available. Saved memories receive an inline acknowledgment.
- Added `MemoryMediaImport.swift`: bounded Transferable file import, ImageIO EXIF
  date/GPS, video capture metadata/thumbnails, selected-asset PhotoKit enrichment,
  and MapKit city/region lookup. Permission is requested only through the optional
  Photos-details action. Named Photos people are not accessible through the public
  asset API, so existing profile people are selectable without identity guessing.
- Added explicit date precedence and removal recomputation; Today/Yesterday and
  an inline calendar replace time entry. Review scrolls to the feeling choices.
  Accessibility containers preserve action identifiers. Reduced Motion suppresses
  animations/tilts. Imports are cancelled/cleaned up when leaving the composer.
- Validation: signed Release build and signature verification pass. 50 unit tests
  pass in an isolated bundle; excluded the pre-existing Keychain roundtrip test,
  which requires the production provisioning/Keychain entitlement absent from the
  isolated ad-hoc signed test copy. The first attempted full run demonstrated that
  expected entitlement failure; no production Keychain code or entitlement removed.
- Three fixture UI journeys pass (create/save/retag/reuse, content requirement,
  date shortcut/song-only memory). Fixed test scrolling to account for clipped
  controls after a failed calendar click. Manual synthetic-photo journey verifies
  July 4 2021 EXIF date, New York GPS lookup, manual date preservation, photo-date
  reset, selected tag, photo-only save and rendered detail. Fixture media remains
  local to the isolated test session, with no user-memory writes for these checks.
- Installed verified signed build at `/Users/embario/Applications/Juke Vibe.app`.
  Opened it normally: real Juke session restored, Neptune memories loaded, and
  current Spotify song appeared. Verified embedded Photos privacy picker in the
  real app without selecting or uploading any user photo or granting library-wide
  access. Left the empty inline composer open for the user.
- Logs: `/tmp/juke-vibe-scrapbook-unit-final.log`,
  `/tmp/juke-vibe-scrapbook-ui-tests.log` (two successful journeys and earlier
  calendar failure), `/tmp/juke-vibe-scrapbook-calendar-ui.log` (calendar passes),
  `/tmp/juke-vibe-scrapbook-release.log`. Validation app uses separate bundle ID
  `com.juke.vibe.scrapbookvalidation`; only the actual app was installed.
- Backend unchanged, Neptune deployment remains active, local Docker remains
  stopped. Full library permission/selected PHAsset enrichment and iCloud-only
  downloads are not live-tested; file metadata and the embedded picker are verified.

### Guided journey correction — 2026-09-17
- User rejected the scrollable scrapbook and embedded system Photos browser.
- Replace with one-screen-at-a-time Photo → Song → Story → Keep flow, original
  SwiftUI illustrations, animated transitions, and a focused completion state.
- Replace native embedded picker/Finder imports with a custom PhotoKit thumbnail
  gallery (one-time permission, chronological groups, incremental loading,
  selection before upload). Denial offers skip/drag without blocking creation.
- Keep date/place inference, tags, snippets and people behind optional review
  controls. Hide the global player while composing to remove competing controls.
- Verify transitions, back-state preservation, content guards and save with tests;
  signed build plus visual inspection at minimum window size. Never auto-grant Photos access.

#### Guided revision build blocker / next handoff
- Source changes are written but NOT built, tested, or installed. The installed
  `/Users/embario/Applications/Juke Vibe.app` is still the earlier scrapbook build.
- Xcode now refuses builds with: "You have not agreed to the Xcode license
  agreements." `xcodebuild -checkFirstLaunchStatus` exits 69. Git via Apple's
  command-line tools is blocked too. User was asked to open Xcode and personally
  review/accept the agreement; never accept it on their behalf.
- Continue after license acceptance: build signed Release, resolve compiler issues,
  copy source to the isolated validation project (different bundle ID; retain its
  ad-hoc signing configuration), run 50 applicable unit tests and the three revised
  UI journeys, inspect screenshots at 900×640, and test custom gallery/denied state
  without granting Photos permissions on the user's behalf. Then install/open the
  verified release. Earlier test results do not validate this revision.
- New files: `Services/MemoryPhotoLibrary.swift`, `Views/MemoryJourneyIllustration.swift`.
  Updated composer, root/player visibility, app state, usage description and UI tests.
  Photo selection includes year filtering and selected-only view; PHAsset references
  retain selections across filters. Oversized downloads cancel at 50 MB. No embedded
  PhotosPicker or Finder/fileImporter remains in the composer.
- Inspect minimum-height illustration sizing, gallery import/cancellation, and the
  optional detail subpages during runtime verification. Backend/Docker untouched.

#### Guided revision built and installed — 2026-09-18
- Xcode license blocker is cleared. The first Release build crashed the Swift compiler
  (assertion in TypeCheckDecl) because `catch { error = error.localizedDescription }`
  in `importSelection()` shadowed the `error` state; fixed with `self.error`.
- Signed Release build (`/tmp/juke-vibe-memories-build`, log
  `/tmp/juke-vibe-guided-release.log`) passes `codesign --verify --deep --strict`
  and is installed at `~/Applications/Juke Vibe.app`. The previous scrapbook build is
  backed up at `/tmp/Juke Vibe scrapbook backup.app`.
- The user said to skip automated tests while iterating quickly, so no unit or UI
  tests were run for this revision. The 900×640 visual pass and gallery checks for
  granted and denied Photos access are still pending.

### Journey UX pass — 2026-09-18 (ITERATIVE)
- User approved 12 UX changes plus choosing any song. All are implemented in the
  signed Release build installed at `~/Applications/Juke Vibe.app`. At the user's
  request no automated tests were run, and there was no visual pass by the agent.
- Journey: starts with the song when a track is playing ("Is this the one?"),
  otherwise with photos. Photo uploads continue in the background (review/save
  wait on them), and photos deselected mid-upload are discarded. Progress dots jump
  to any reached step. Esc goes back; Return advances, or ⌘Return on the song and
  story steps.
- Song step: catalog search (`CatalogClient.search`, kind `tracks`, Spotify-backed)
  adds any song. The snippet steppers are replaced by `SnippetRangeSlider` with
  "Hear it" and "Start here". Song length comes from the track/catalog duration and
  is kept in composer state only, with no backend schema change.
- Visuals: record labels show the album art and spin only while that song plays.
  The accent color (`journeyAccent` environment value) comes from the artwork or
  the first photo.
- Story: questions built from date/place/song/insights, with "Ask me something
  else". #tags typed in the story show up as chips as you type.
- Preview is the memory card itself; each chip opens its detail page.
- Completion: the card tucks into a stack, the Spotify snippet auto-plays only
  when Juke controls Spotify directly, and the memory opens by itself after ~2.6 s.
  The duplicate "Tucked into your soundtrack" banner was removed from the list.
- Photos: the year menu is replaced by a strip of only the years that have photos
  (`MemoryPhotoLibrary.loadYears`).
- List: month/year timeline sections and an "On this day" (±3 days, earlier
  years) row.
- UI tests referencing `memory.segmentStart/segmentEnd`, `memory.saved` or the
  old step order need updating before the next test run.
