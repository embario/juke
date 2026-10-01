---
id: juke-app-implementation
title: Build the Juke App (formerly Juke Vibe) with Radio, Library, Memories and Chat
status: in_progress
priority: p1
owner: claude
area: clients
label: CLIENTS/BACKEND
complexity: 5
updated_at: 2026-10-01
---

## Goal

Replace the macOS Juke Vibe app with the **Juke** app designed in
`tasks/juke-app-radio-redesign.md` (canvas page "Round 3 · Converged",
https://claude.ai/artifact/9vZzRaNkXzpMxvN7bETvfZ; a static copy of the prototype
source is in `docs/design/juke-app/Round3.reference.html`). Rename the iOS
Juke Vibe app to Juke as well. Turning radio on must be frictionless: one tap the
first time, auto-resume afterwards, and the music never stops while you change
stations.

## Decisions (from the user, 2026-10-01)

- Only this effort builds the feature. Lead autonomously; open and merge PRs into
  `integration/juke-app` with a review on every PR. Final PR to `master` stays open.
- Rename both Apple apps to **Juke**, bundle IDs included:
  macOS `com.juke.vibe.mac` → `com.juke.mac`; iOS Juke Vibe → `com.juke.app`
  (`com.juke.juke` already belongs to `mobile/ios/juke`). The sandbox container
  and Keychain items change, so users sign in once more; memories and encrypted
  chat records live on the backend and come back after sign-in.
- Sections: **Radio**, **Library** (catalog browsing, the crate), **Memories**,
  **Chat**. Chat stays in v1, restyled in the same single-card language.
  Recognition (Shazam + player metadata) becomes a quiet background helper that
  feeds taste signals; it has no screen of its own.
- Spotify-only playback for radio in v1. Apple Music keeps today's local
  controls for whatever is already playing.
- Recommendations: Spotify's recommendations/related-artists/audio-features APIs
  are unavailable to new apps, so radio picks come from our stack: MLCore
  co-occurrence (populated on the neptune dev server) → Spotify aliases, then
  fallbacks (MLCore metadata ranker, artist top tracks, Spotify search with
  mood keywords).
- macOS 26 minimum. Crate flip direction lives on the crate switch and in
  Settings. Station frequencies are stored on the backend. Backend URL becomes a
  setting (default `https://neptune.tail647b75.ts.net`), no more hardcoding.
- Lyrics: "coming soon" sheet until a licensed provider is chosen. Ads: out of scope.

## Delivery

- Mode: `ASYNC`. Integration branch: `integration/juke-app` (from `master`).
- Each slice: branch `juke-app/<slice>` from the integration branch → PR into
  `integration/juke-app` → review (code-review pass, findings fixed) → merge.
- CI runs on PRs into `integration/**` (backend build/lint/tests, macOS unit tests).
- Neptune: the dev stack (`/srv/juke-dev`, containers `juke-dev-*`) holds the MLCore
  data. Its git checkout belongs to other work; never switch its branch or touch its
  uncommitted files. Validate against it read-only (`ssh neptune`, `docker exec
  juke-dev-backend-1 …`), and serve integration builds from an extra stack at
  `/srv/juke-extra/juke-app` (backend port 8200) that shares the dev Postgres,
  Redis and recommender engine and only ever runs `migrate radio`.

## Slices

1. **S0 spec + CI** (this file, CI triggers, design reference).
2. **S1 backend `radio` app**: models, API, recommendation pipeline, queue-based
   continuous playback, events, crate endpoint. Contract below.
3. **S2 macOS foundation**: rename (folder `macos/juke`, targets `JukeMac*`, bundle IDs,
   display name, README, scripts), XcodeGen regenerate, settings (appearance,
   crate flip, backend URL, recognition toggle), theme tokens + artwork-derived
   card color with animated transitions, app shell with the four sections and
   gentle navigation transitions, shared API client using the configurable URL.
4. **S3 macOS Radio card**: sleeve (flip to options), vinyl (spin edge to seek with
   fling, slide label into/out of sleeve to stop/resume, click to pause), reaction
   strip (+ click = emoji picker, + hold = words), progress, play/skip(hold menu)/save,
   FM dial (drag + momentum, flick to "+ New", hold a station to move its
   frequency, three seed thumbnails per station, play cue for the tuned station),
   station sheet (built from / feels like / keep out / keeps learning), put-away
   state with session summary and "Save as a memory", RadioController loop that
   queues the next track ~20 s before the current one ends.
5. **S4 macOS Library + New station**: crate (side-to-side and front-to-back, drag,
   wheel, click), Songs/Artists/Albums, search, "Start radio"; New station with
   Records or Feelings first, the other step optional, picks listed as text.
6. **S5 macOS Memories + Chat + recognition**: restyle both into the single-card
   language; recognition runs in the background and posts taste events.
7. **S6 iOS rename**: Juke Vibe iOS → Juke, `com.juke.app`.
8. **S7 integration**: deploy to neptune extra stack, end-to-end checks, UI tests,
   final PR to master.

## Radio API contract (S1, consumed by S3–S5)

All under `/api/v1/radio/`, token auth (`Authorization: Token …` or `Bearer …`),
JSON, camelCase keys (matches the Vibe memories API).

Types:
- `Track`: `{spotifyId, uri, title, artist, artistId, album, albumId, artworkUrl, durationMs}`
- `Seed`: `{kind: "track"|"artist"|"album", spotifyId, title, subtitle, artworkUrl}`
- `Exclusion`: `{id, scope: "station"|"everywhere", kind: "track"|"artist"|"genre"|"text", value, label}`
- `Station`: `{id, name, kind: "personal"|"custom", frequency (float, odd tenths 88.1–107.9),
  seeds: [Seed], thumbnails: [artworkUrl ×≤3], feelings: [string], learning: bool,
  exclusions: [Exclusion], createdAt}`

Endpoints:
- `GET stations/` → `{stations: [Station]}`. Creates the personal station
  ("My Station", 88.7) on first call.
- `POST stations/` `{name?, seeds: [Seed], feelings: [string]}` → `Station` (201).
  Needs ≥1 seed or feeling. Name defaults to `"<first seed> Radio"` or
  `"<feelings> Radio"`; frequency auto-assigned to the highest free slot.
- `PATCH stations/<id>/` `{name?, frequency?, seeds?, feelings?, learning?}` → `Station`.
  Frequency is snapped to odd tenths in range; if within 2.2 MHz of another station it
  is moved to the nearest free slot (response has the final value).
- `DELETE stations/<id>/` → 204 (not for the personal station).
- `POST stations/<id>/exclusions/` `{scope, kind, value, label}` → `Exclusion`;
  `DELETE exclusions/<id>/` → 204. `scope: "everywhere"` applies to all stations.
- `PUT reactions/` `{spotifyTrackId, stationId?, reactions: [string]}` →
  `{reactions, suggestion: {stationId, name, matched: [string]} | null}`.
  Reactions are emoji or short phrases (≤40 chars). A suggestion is returned when
  another station's feelings match better than the current one's.
- `POST stations/<id>/next` `{count?: 1-10 (default 3), recentTrackIds?: [id]}` →
  `{tracks: [Track], source: "mlcore"|"metadata"|"artist"|"search"|"seed"}`. Never returns
  excluded tracks/artists or recently played ones.
- `POST play` `{stationId, mode: "now"|"queue", deviceId?}` → `{track: Track, state}`:
  `now` starts the station's next track immediately; `queue` adds it to the Spotify
  queue (used ~20 s before the current track ends, and for "after this song").
- `POST events/` `{stationId?, spotifyTrackId, event, positionMs?, source?}` → 204.
  `event`: `play|complete|skip|less|not_on_station|never_artist|seek|save|recognized`.
  Positive events and reactions feed the personal station's seeds when `learning`.
- `GET crate/?kind=tracks|artists|albums&q=` → `{items: [{id, kind, spotifyId, title,
  subtitle, artworkUrl, track?: Track}]}`. With `q`: Spotify search. Without: a
  personal crate (station seeds, reacted/loved tracks, then MLCore picks).
- `GET session/summary` → `{startedAt, songCount, reactions: [string], tracks: [Track]}`
  for the put-away "Save as a memory" action.

## Acceptance Criteria

- Personal station plays continuously on Spotify with no user action after the
  first tap; switching stations never interrupts the current song unless the play
  cue is pressed.
- Every gesture in the design works with mouse and trackpad; every action also has a
  keyboard path (buttons, menus).
- Light, Dark and Match system all pass WCAG AA text contrast; default Match system.
- Backend tests cover the API contract with Spotify and MLCore mocked; ruff clean;
  migrations committed. macOS unit tests pass; UI tests cover the main flows.
- The app reaches the neptune extra stack through the configurable backend URL.

## Handoff

- Completed: S0.
- Next: S1, S2, S6 in parallel; then S3, S4, S5; then S7.
- Blockers: none.
