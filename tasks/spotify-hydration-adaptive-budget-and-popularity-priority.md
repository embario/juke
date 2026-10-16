---
id: spotify-hydration-adaptive-budget-and-popularity-priority
title: Adaptive Spotify hydration budget with popularity-first, graph-expanding priority
status: ready
priority: p2
owner: unassigned
area: backend
label: BACKEND/ML
complexity: 4
updated_at: 2026-10-16
---

## Goal

Hydrate the Spotify ISRC backlog faster and more usefully, in two independent parts:

1. **Adaptive budget.** Replace the hand-set fixed request budget with a controller that finds a safe sustained request rate on its own, backs off on provider limiting, and never starves OAuth linking or playback.
2. **Popularity-first ordering.** Spend the available requests on the items that matter most: start with the most-listened tracks, then branch outward to related tracks, artists, and albums, instead of working through the queue in insertion order.

## Background (observed 2026-10-16 on Neptune)

- The worker runs as the user systemd unit `juke-spotify-hydration` with `--rps 1`, on a dedicated Spotify app (`SPOTIFY_HYDRATION_CLIENT_ID/SECRET`).
- `SpotifyHydrationQuotaGuard.effective_rps` is `min(requested_rps, budget / window)`. With the default `SPOTIFY_HYDRATION_REQUEST_BUDGET=5000` per 86400 s this pins the pacer at ~0.058 rps, so `--rps 1` is ignored. The pacer's recovery (`+0.1` rps per 300 successes) can never exceed that cap, so nothing probes for headroom.
- Throughput is ~4,100 items per 24 h. Backlog is ~6.4M pending, 316k matched, 143k ambiguous, 109k no_match, 5k dead. At the current rate that is years.
- Retries count against the budget: `record_request` runs before every attempt, including Spotify HTTP 5xx. The latest run had ~11.9k retries.
- Queue order is `ORDER BY priority, id` (`claim_hydration_item`). `ProviderHydrationItem.priority` defaults to 100 and the seeder never sets it, so order is effectively insertion order and carries no signal about which tracks users care about.

## Scope

### Part 1: Adaptive budget

- Add a controller (alongside `RequestPacer` / `SpotifyHydrationQuotaGuard` in `backend/mlcore/services/provider_hydration.py`) that adjusts the sustained rate/budget:
  - Additive increase while requests succeed with no 429 for a configurable period.
  - Multiplicative decrease on 429, honoring `Retry-After` and the existing persisted `cooldown_until`.
  - Persist the learned ceiling in run metadata so restarts resume from it instead of from the static default.
  - Configurable floor and hard ceiling (`SPOTIFY_HYDRATION_MIN_RPS`, `SPOTIFY_HYDRATION_MAX_RPS`, or equivalent) so an operator can bound it. The static budget remains as the hard ceiling.
- Do not charge provider 5xx responses (or charge them at a reduced weight) against the rolling budget. Back off on a streak of 5xx instead.
- Keep the dedicated-app isolation: the controller governs only the hydration client's traffic and must not read or reduce the login/playback app's capacity.
- Emit rate, budget used, learned ceiling, 429 count, and 5xx count in the existing `--metrics-path` output so progress and limiting are observable.

### Part 2: Popularity-first, graph-expanding priority

- Define an item score from signals MLCore already has and write it into `ProviderHydrationItem.priority` (lower claims first). Candidate signals, to be validated against real data before choosing weights:
  - Listen counts per canonical item from `ListenBrainzEventLedger` / session data.
  - Number of distinct users or sessions listening, to damp single-user binges.
  - Items already referenced by Juke users' libraries, playback history, or Juke Vibe memories (highest priority: these are what clients will actually ask for).
- **Wave expansion.** After the top-N popular items are hydrated, expand outward by relatedness instead of re-sorting the entire corpus:
  - Co-listening neighbors via `ItemCoOccurrence` (PMI/`co_count`) of already-hydrated popular items.
  - Same-artist and same-album siblings of hydrated items, once artist/release identity is resolved from the MusicBrainz ISRC bridge.
  - Each wave raises the priority of its newly discovered neighbors, bounded per wave so one hub item cannot flood the queue.
- Make priority recomputation incremental and cheap (seed-time scoring plus a periodic re-score pass), and do not require a full-table rewrite of ~6.4M rows each cycle.
- Provide an operator-visible way to see what is being hydrated next (for example a management command that prints the top-K pending items and their scores).

## Out Of Scope

- Circumventing Spotify quota policy: no additional or disguised Spotify apps, rotating credentials, or hiding the nature of the traffic. Requesting extended quota from Spotify through the developer dashboard is the legitimate route and is a separate, manual step.
- Changing identity-matching semantics (how `matched` / `ambiguous` / `no_match` are decided).
- Replacing Spotify search with another provider. Reducing Spotify calls by resolving through MusicBrainz/ListenBrainz data is tracked in the existing `mlcore-*` tasks.
- Multi-worker hydration; the global provider lease stays single-worker.

## Acceptance Criteria

- With a mocked provider that returns 200s, the controller raises the effective rate step by step up to the configured ceiling; on a mocked 429 it cuts the rate, waits the `Retry-After`, and resumes lower. Covered by unit tests with injected clock and sleep.
- The learned ceiling and cooldown survive a worker restart (verified by test, not just by inspection).
- 5xx responses no longer drain the rolling budget one-for-one, with a test showing a burst of 502s leaves the budget substantially intact.
- Pending items are claimed in popularity order: given a seeded fixture with known listen counts, the highest-count items are claimed first, and items referenced by Juke users' libraries or playback come before purely corpus-popular ones.
- Wave expansion: given a fixture with co-occurrence rows and sibling relationships, hydrating a popular item raises the priority of its neighbors, capped per wave, and the claim order reflects it.
- Priority recomputation does not take a lock on the whole table or block the worker's `claim_hydration_item` path (check query plan / batch size).
- On Juke Dev, after deployment: the learned rate and 24 h hydration count are visibly above the pre-change ~4,100/day baseline without any sustained 429s, and OAuth linking still succeeds while the worker runs.
- Backend tests pass: `docker compose exec backend python manage.py test`.

## Execution Notes

- ITERATIVE: the user expects to refine scope as work proceeds. Ship Part 1 first as a narrow slice (controller plus 5xx accounting plus metrics), report the measured rate, then take Part 2 in stages: score from listen counts, then library/playback boosts, then wave expansion.
- Key files: `backend/mlcore/services/provider_hydration.py` (`RequestPacer`, `SpotifyHydrationQuotaGuard`, `claim_hydration_item`, `seed_spotify_hydration_queue`), `backend/mlcore/management/commands/hydrate_spotify_from_isrc.py`, `backend/mlcore/models.py` (`ProviderHydrationItem.priority`, `ItemCoOccurrence`, `ListenBrainzEventLedger`, `CanonicalItem`), `backend/settings/base.py` (`SPOTIFY_HYDRATION_*`), `deploy/systemd/juke-spotify-hydration.service`, `docker-compose.yml` (`spotify-hydrator`).
- Related tasks: `tasks/spotify-oauth-hydrator-quota-isolation.md` (done; origin of the fixed budget), `tasks/mlcore-platform-uri-hydration-from-isrc.md`, `tasks/mlcore-shared-identity-alias-resolver.md`, `tasks/mlcore-musicbrainz-isrc-bridge-ingestion.md`.
- Resource note: avoid MLCore-heavy jobs on the local stack. Mock Spotify; test the controller and priority logic against small fixtures. Validate scoring on Neptune with read-only queries before writing priorities.
- Rollout: the worker is a live systemd service on Neptune. Deploy via the normal Juke Dev path and restart `juke-spotify-hydration`; confirm `systemctl --user is-active` and recent HTTP 200s afterward.
- Risks:
  - Raising the rate too aggressively could exhaust quota even on the dedicated app. Keep a conservative ceiling and ramp slowly.
  - Popularity bias skews the early hydrated corpus toward mainstream tracks; wave expansion and a low-priority sweep of the long tail must still run so the tail is not starved forever.
  - Rewriting `priority` for millions of rows can bloat or lock the table. Update in bounded batches and prefer scoring at seed time.
  - Hub items (very popular tracks) can dominate co-occurrence expansion; cap per-wave fan-out.
  - Spotify's actual limits for the dedicated app are unpublished, so the controller must learn them empirically and degrade safely.

## Handoff

- Completed: Task written from a live read-only inspection of the Neptune hydrator (2026-10-16). The worker was moved to a dedicated Spotify app's credentials and restarted the same day; the budget is still the static 5,000 per 24 h.
- Next: Start with Part 1. First confirm with a read-only query that the dedicated app is sustaining HTTP 200s, then implement the controller with unit tests. Separately, run read-only scoring queries on Neptune to pick the popularity signal and weights for Part 2.
- Blockers: None.
