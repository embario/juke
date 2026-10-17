# Radio: why stations run out, and why songs feel unrelated to the seeds and feelings

Round 3, PR S (investigation only). Refs #230. This PR changes no radio behavior: it adds this document and
a DB-free characterization test (`backend/tests/unit/test_radio_investigation.py`) that pins today's behavior
so each finding below can be reproduced. Fixes are listed at the end as proposals; each becomes a task only
after the owner approves it.

Code read: `integration/juke-app` at `c34b901` (`backend/radio/services/{recommend,spotify,signals,feelings}.py`,
`backend/radio/views.py`, `backend/mlcore/**`, `backend/recommender_engine/app/main.py`).
Deployed revision inspected read-only: Neptune extra stack `/srv/juke-extra/juke-app`, checkout `ac7dc10`
(`integration/juke-app`, includes #233/#234). Nothing was deployed, restarted or written there.

## 1. Short answers

**Why a station "runs out of songs".** On the deployed stack, every `409 radio_no_tracks` in the available
logs was not an exhausted station. All 14 of them fall inside the 60-second window after a single Spotify
connection reset opened the radio circuit breaker, which makes every Spotify call return nothing for 60 s.
The server then reported "nothing new to play". #234 (merged, running on the extra stack) now answers `503
radio_picks_unavailable` for that case and #233 shows it as "try again". A genuinely small candidate pool is the
second cause: with MLCore contributing nothing, a seeded station draws from about 50 songs, so it replays or
runs dry in a long session.

**Why songs feel unrelated to tags, feelings and seeds.** Three causes stack:

1. MLCore never contributes. None of the 43 Spotify tracks tried (39 the owner played, 4 very popular songs)
   resolve to a canonical item, so the co-occurrence and metadata rankers return nothing for every seed. The
   only "similar to the seed" signal left is the seed artist's top tracks.
2. Feelings barely steer. A seeded station asks the feelings for songs only when the seed artist's top tracks
   are used up, and when it does the search ignores the seed's genres. Before that, feelings can only re-order a
   pool of two tracks, and a single-artist pool is never re-ordered at all.
3. When there are no feelings and Spotify gives no genres for the seed artist, the fallback is the default
   "chill" profile (chillhop, lo-fi, chillwave, downtempo, indie pop), whatever the seed sounds like.

## 2. Verified and unverified

| # | Statement | Status | How it was checked |
|---|---|---|---|
| V1 | All 14 `409` responses in the logs follow a "Spotify unavailable for radio" warning within 60 s | Verified (deployed logs) | `docker logs --timestamps` on the extra-stack backend, 4 incidents (2026-10-08 13:40:28, 2026-10-08 18:20:43, 2026-10-09 19:43:33, 2026-10-10 13:21:31 UTC); same window had 28 successful plays |
| V2 | The 2026-10-10 13:21:31 incident is the owner's "Next does nothing" burst | Consistent, not proven | ten 409s between 13:21:31 and 13:22:24 on one station (skips of that station recorded at the same seconds), first success 13:22:34, three seconds after the breaker window ended |
| V3 | Seeds do not resolve in MLCore on the extra stack | Verified (deployed engine) | `/engine/recommend/{cooccurrence,metadata}/identity` returned `resolved_seed_count: 0` for every seed of the two track-seeded stations probed (a third, artist-seeded station was not probed), for 39 of 39 played tracks, and for 4 of 4 popular tracks |
| V4 | Spotify aliases are a small part of the identity graph and fill slowly | Verified (deployed DB, estimates) | Hydration queue: 6,657,142 items; matched 301,273; no_match 104,209; ambiguous 136,854; dead 5,211; pending 6,432,332. The running hydration run (started 2026-09-04) has attempted 153,433 items in 36 days (about 4,300 a day) and matched 73,052 |
| V5 | The extra stack has no user exclusions, and every station has one seed | Verified (deployed DB) | read-only counts: 0 exclusion rows; 5 custom stations with exactly one seed each (4 track seeds, 1 artist seed), 3 of them with feelings |
| V6 | Feelings do not choose songs while seed-artist tracks remain; the seed's genres are not used when feelings exist; the "chill" fallback; the 2-track re-rank pool; about 50 distinct songs then replays | Verified (code and mocked tests) | `backend/tests/unit/test_radio_investigation.py` (6 tests, run locally, DB-free) |
| U1 | Why Spotify connections were reset | Unverified | the failing call differed between incidents (search twice, tracks batch, artist top tracks): general connectivity or stale keep-alive connections are likely, not proven |
| U2 | Real size of the candidate pool per station | Unverified | the test pool is an optimistic fake (genre searches overlap in real life); the extra stack's Spotify cache is per process (`LocMemCache`), so it could not be read from outside the server process |
| U3 | Whether Spotify still returns artist genres and top tracks to this app | Unverified | no Spotify call was made; the `radio/*` code logs this only at INFO, which the stack does not print |
| U4 | Time spent per pick against the 4 s budget | Unverified | the logs carry no durations; `MLCORE_TIMEOUT` and reserve behavior is read from code only |
| U5 | ISRC alias coverage for the owner's seeds | Unverified | see F3: this is the first thing to measure |

## 3. Likely causes, ranked

### Exhaustion ("nothing left")

**E1. A single Spotify reset is reported as an empty station (verified, fixed by #234).**
`spotify._trip_breaker` opens a 60 s breaker for any transport error, 5xx or 429, and
`spotify._call` then returns `None` for every call, so MLCore-less stations have no source at all.
`PlayView` used to answer `409 radio_no_tracks`. Evidence: V1, V2. Since #234, the
same event is a `503 radio_picks_unavailable`. The breaker itself is unchanged: for up to 60 s every Next
still fails (now with the right message), and the client has no retry.

**E2. The candidate pool is small, fixed and ordered (verified in code and tests).**
With MLCore empty (E3), a seeded station draws from: up to 10 top tracks of the seed artist(s)
(at most 4 artists), then genre searches (at most 8 queries, 10 results per page; page 2 is fetched only when
page 1 is entirely in the history), then the seed itself as the last resort. All of those are cached and
returned in the same order (top tracks 24 h, searches 1 h). The history excludes the last 50 distinct songs
across all of the user's stations (`signals.recent_track_ids`, skips and queued songs included). Result in the
fake world of the test: 51 distinct songs, then the same songs again in the same order; with a smaller pool
(3 top tracks plus one 10-result search) the station plays 14 songs, the last one being its own seed, then
returns nothing. A station seeded with an artist whose Spotify results overlap, or that has no genres, runs
dry earlier.

**E3. MLCore, the broad source, contributes nothing (verified).**
See V3 and V4. The co-occurrence tables are large (the estimated rows of the current tables are in the
billions), but the lookup key is a Spotify id, and Spotify aliases exist for only a small part of the graph
(they are created by the slow Spotify hydration run). So the broad "people who played X also played Y"
pool never opens for these seeds, which is the main reason E2 is small.

**E4. The time budget and the MLCore reserve (code only, unverified).**
`NEXT_BUDGET_SECONDS` is 4 s for the whole pick; MLCore calls may use only what is left after a 1.5 s
reserve, and a second hop needs 1.8 s free. When MLCore is slow, later sources are skipped by `out_of_time()`.
This was a risk before E3 was known: with unresolved seeds MLCore answers in under half a second, so it is
not the cause on the extra stack.

**E5. Exclusions (not a factor here, latent in code).** Artist exclusions without a label make
`ExclusionFilter.blocks_track` drop every track that carries no artist ids (MLCore evidence tracks), so one
unlabelled exclusion can silence the whole MLCore source once MLCore works.

### Relevance

**R1. No co-occurrence signal (verified).** Same as E3: "songs people play with this one" never applies, so
relatedness to the seed is only "same artist" and then "same broad genre".

**R2. Feelings come after the seed artist's tracks, and re-rank at most two songs (verified, tests).**
Sound search ("honour the feeling") runs only when fewer than `count` seed-related tracks were found
(`recommend._next_tracks`). `/radio/play` asks for one song, so a feelings re-rank gets a pool of two
(`POOL_FACTOR = 2`), and the one-artist-per-pool rule puts every extra top track of the same artist into the
overflow, so one artist's top tracks leave a pool of one and no re-rank happens at all. For a station seeded
with a song, an owner who picked a mood sees ten songs by the seed artist, in order, before the mood does
anything.

**R3. Seed and feelings never combine in the search (verified, tests).** With feelings, `_sound_search` uses
only the feelings' genre filters (for example 🔥 means "hype": hip hop, trap, edm, electro house). The
seed's own genres are used only when the station has no feelings. A rock seed with a 🔥 feeling therefore
gets hip hop and EDM once the artist's top tracks are used up.

**R4. Default "chill" for a seed with no genres (verified, tests).** Without feelings, the search uses the
seed artists' Spotify genres; when Spotify returns none, it falls back to memory tags (personal station) or the
default `chill` profile (lo-fi, chillhop, chillwave, downtempo, indie pop).

**R5. Coarse, fixed feeling profiles (code).** A feeling is an emoji or phrase mapped by hand to a short
genre list (`feelings.PROFILES`, about 50 phrases). An unknown phrase becomes a literal `genre:"…"` filter
(which matches nothing unless it is a real genre) plus a title text search whose literal-title matches are then
dropped unless the artist's genres fit, so it often contributes little. Tags a user types are not understood
beyond that list.

**R6. Learned seeds mostly feed the artist list (code).** A learning station adds up to 15 completed, saved or
reacted songs as seeds, but MLCore receives only 3 of them (and finds none, E3), and the rest only add artists to
the first four expanded. Positive feedback therefore changes little today.

**R7. Memory tags are a fallback only (code).** Personal-station memory tags become feelings only when the
station has neither feelings nor seeds; with seeds they appear only as the fallback in R4.

## 4. What could not be checked

- Why Spotify connections reset (U1), and whether artist genres and top tracks are still served to this app
  (U3): needs a deliberate Spotify probe, which an investigation-only PR should not spend quota on.
- Real candidate pool sizes (U2) and time per pick (U4): the server logs at INFO are not printed, and the
  extra stack's cache is `LocMemCache` inside the server process.
- Whether the production stack differs. Only the extra stack was inspected; `/srv/juke-dev` and `/srv/juke-prod`
  were not touched. The cache and breaker are per process, so a multi-worker production server has one breaker
  per worker.
- A real phone and the iOS client: not part of this investigation.

## 5. Fix proposals (each needs the owner's approval; sizes S/M/L)

| # | Proposal | Fixes | Size | Risk and notes |
|---|---|---|---|---|
| F1 | Retry a Spotify call once on a connection error before the breaker opens, and shorten the breaker for transport errors (for example 10 s; keep 60 s and `Retry-After` for 429) | E1 | S | backend only, no migration; add a mocked test with a reset on the first attempt |
| F2 | Log a radio pick that returns nothing at WARNING with station id, sources tried and the trouble reasons; log breaker trips with the station id | observability for E1, E4, U2, U4 | S | backend only |
| F3 | Resolve a seed through its ISRC when its Spotify alias is missing: carry `external_ids.isrc` in the track payload, look the ISRC up in `CanonicalItemAlias` (`source='isrc'`, `resource_type='recording'`), cache the result per seed, and call the existing canonical `/engine/recommend/cooccurrence` with the canonical ids. Only station seeds and learned seeds are resolved, not the 6.4M backlog | E3, R1 | M | no migration; first step is a read-only probe of ISRC alias coverage for the owner's seeds (U5); needs Spotify to keep returning ISRCs (U3) |
| F4 | Make feelings influence the first pick: run a bounded sound search up front for a station that has feelings, combine seed genres with feeling genres, and re-rank a pool of at least 20 even when one song is asked | R2, R3 | M | behavior change for every seeded station with feelings; needs the owner's call on the balance between seed and feeling |
| F5 | Use the seed's own genres (or its artist's name search) before the default `chill` profile; drop the default for seeded stations | R4 | S | small behavior change |
| F6 | Vary the order: shuffle within a source with a per-station seed, keep a per-station history longer than 50, widen the pool (page 2 up front, top tracks of related artists via MLCore once F3 lands) | E2 | M | behavior change; pairs with F3 |
| F7 | Give the client one automatic retry after a 503 `radio_picks_unavailable` (about 2 s later) before it shows "try again" | E1 | S | iOS and Mac; builds on #233 |
| F8 | Treat labelled and unlabelled artist exclusions the same way for evidence tracks (hydrate or drop by id) | E5 | S | latent today |

Suggested order: F2 and F1 first (small, make incidents visible and rarer), then F3's read-only probe, then F3,
F5, F4, F6. F7 and F8 can wait.

## 6. Reproduce

- Characterization tests: `docker compose exec backend python manage.py test tests.unit.test_radio_investigation`
  (they use no database or network; they also ran locally with a plain virtualenv).
- Deployed-stack checks: read-only `docker logs --timestamps` on the extra-stack backend (filter on
  `Spotify unavailable for radio` and `radio/play` 409), plus read-only `manage.py shell` queries (station
  and exclusion counts, hydration queue counts) and calls to the MLCore identity endpoints with a station's
  seed ids and no exclusions. No rows were written and no Spotify request was made by these checks.
