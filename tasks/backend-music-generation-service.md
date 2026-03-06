---
id: backend-music-generation
title: Music generation service - prompt to audio via external gen API
status: ready
priority: p3
owner: unassigned
area: backend
label: BACKEND
labels:
  - juke-task
  - backend
  - experimental
  - ml
complexity: 4
updated_at: 2026-03-06
---

## Goal

An experimental backend surface for text-prompt → generated audio. Wraps an
external music-generation API (provider TBD) behind a job queue: submit prompt,
get job ID, poll status, fetch audio URL when done. Consumed by cli-phase6 and
potentially a web experiment later.

## Scope

- Provider selection spike first: evaluate 2–3 external gen APIs on latency,
  output quality, licensing, and cost. Pick one. Document the choice + runners-up
  in an Execution Note here before building.
- Models: `GenerationJob` (user FK, prompt text, status enum
  `queued`/`running`/`completed`/`failed`/`cancelled`, `result_url` nullable,
  `error` nullable, `created_at`, `completed_at`). Lives in a new
  `backend/generation/` app.
- Celery task: `run_generation_job(job_id)`. Calls the external API, polls it
  (or waits on its webhook), updates `GenerationJob.status` as it goes, stores
  the final audio URL.
- REST endpoints under `/api/v1/generation/`:
  - `POST jobs/` — submit prompt, returns `{"job_id": ..., "status": "queued"}`.
    Enqueues the Celery task.
  - `GET jobs/` — list the user's jobs.
  - `GET jobs/<pk>/` — job detail with current status + `result_url` when done.
  - `DELETE jobs/<pk>/` — cancel if queued/running, delete if terminal.
- Optional (if cli-phase2 has landed): `GenerationConsumer` on
  `ws/v1/generation/` pushing `{"type": "job.updated", "job": {...}}` on status
  change. If not, clients poll `GET jobs/<pk>/`.
- Rate limiting: per-user daily generation cap (setting
  `JUKE_GENERATION_DAILY_LIMIT`). Return 429 with a `retry_after` hint.

## Out Of Scope

- Hosting our own generation model. External API only.
- Saving generated audio into the catalog as `Track` rows. Results are
  ephemeral (provider-hosted URLs, expire per provider TTL).
- Generation parameters beyond prompt text (duration, genre seeds, BPM). Add
  only if the chosen provider supports them trivially.
- Audio post-processing / mastering.
- Copyright / content-policy filtering on prompts. Deferred to a follow-up
  once we see what people actually submit.

## Acceptance Criteria

- Provider-selection note exists in this file's Execution Notes with the chosen
  API and reasoning.
- `POST .../jobs/` with a prompt returns a job ID and `status: queued`.
  A Celery worker picks it up and the job reaches `completed` with a valid
  `result_url`, or `failed` with a populated `error` field.
- `GET .../jobs/<pk>/` polled during a run shows status transitions.
- Rate limit: submitting past `JUKE_GENERATION_DAILY_LIMIT` returns 429.
- Cancelling a queued job prevents it from running. Cancelling a running job
  best-effort stops it (or at least marks it cancelled so clients stop polling).
- Tests mock the external API. No real generation calls from the test suite.

## Execution Notes

- Portfolio classification: `experimental`. This is the most speculative of the
  three CLI backend dependencies. If provider costs or quality don't justify it,
  closing this task and unblocking cli-phase6 as "won't do" is a valid outcome.
- The Celery task pattern exists already — mirror whatever `mlcore` or other
  apps do for long-running jobs. Don't invent new job-state machinery.
- Result URLs from external providers usually expire. Document the TTL in the
  API response so clients know to fetch promptly. Don't proxy/re-host audio in
  v1.
- Key files:
  - `backend/generation/{__init__,apps,models,views,urls,tasks}.py` (new)
  - `backend/generation/migrations/0001_initial.py`
  - `backend/generation/providers/<chosen>.py` (API wrapper)
  - `backend/settings/base.py` (add `generation` to `INSTALLED_APPS`,
    `JUKE_GENERATION_DAILY_LIMIT`, provider API key setting)
  - `backend/settings/urls.py` (include `generation.urls`)
  - `backend/tests/unit/test_generation_*.py`
  - Optionally `backend/realtime/routing.py` (if adding WS push)
- Commands:
  - `docker compose exec backend python manage.py makemigrations generation`
  - `docker compose exec backend python manage.py migrate`
  - `docker compose exec backend python manage.py test`
  - `docker compose exec celery_worker celery -A settings inspect active`
    (watch jobs run)
- Risks:
  - **Provider lock-in.** Put the provider behind a `GenerationProvider` ABC
    (same pattern as `catalog/services/playback.py`'s `PlaybackProvider`) so
    swapping is a one-file change.
  - External gen APIs are flaky and slow (multi-minute). The Celery task needs
    a generous timeout, retries with backoff, and must handle the provider
    going away mid-job without leaving the `GenerationJob` in `running` forever.
    Add a janitor task that marks stale `running` jobs as `failed` after N
    minutes with no update.
  - Cost. Even with rate limiting, a few users hammering this is real money.
    The daily cap is the first line; a global monthly budget-kill-switch
    setting is the second.
  - The result-URL model means generated audio is **not playable through
    Spotify**. cli-phase6 needs a local-playback path. This should be surfaced
    in that task (it is), but the decision about whether the backend re-hosts
    audio vs. clients play provider URLs directly belongs here.

## Handoff

- Completed:
- Next:
  - cli-phase6 consumes this.
- Blockers:
  - None hard. Soft: if the WS push path is wanted, cli-phase2 should be done.
    But polling `GET jobs/<pk>/` works without it.
