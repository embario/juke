---
id: backend-track-facts-llm
title: Track fun-facts LLM endpoint
status: ready
priority: p2
owner: unassigned
area: backend
label: BACKEND
labels:
  - juke-task
  - backend
  - llm
complexity: 2
updated_at: 2026-03-06
---

## Goal

An authenticated endpoint that takes a track and returns 2–3 short, interesting
facts about it (artist trivia, recording context, chart history, notable
samples/covers). Consumed by cli-phase4's sidebar and later by web/mobile
now-playing screens.

## Scope

- Endpoint: `GET /api/v1/catalog/tracks/<pk>/facts/` (action on the existing
  `TrackViewSet`) or a standalone `/api/v1/facts/track/` — pick whichever fits
  the router better at implementation time.
- Service: new `catalog/services/facts.py` with a `TrackFactsService` following
  the `TriviaGenerationService` pattern from `backend/tunetrivia/services.py:258-344`
  (OpenAI client, system prompt, structured output).
- Prompt builds context from the track's catalog metadata (name, artist(s),
  album, year, genre tags). No external knowledge-base calls — the LLM's
  training data is the source.
- Response shape: `{"track_id": ..., "facts": ["...", "...", "..."]}`. Facts
  are plain strings, no markdown, target 1–2 sentences each.
- Cache layer: facts for a given track are stable-ish. Cache in Redis keyed on
  `(track_id, model_version)` with a long TTL (days). Cache miss hits the LLM.
- Settings: reuse `OPENAI_API_KEY` from env; new `JUKE_FACTS_MODEL` setting
  defaulting to the same value as `TUNETRIVIA_TRIVIA_MODEL` (`gpt-4o-mini` per
  `template.env`).

## Out Of Scope

- Fact verification / citation. These are "fun facts," not encyclopedia entries.
  The prompt should discourage fabrication but we don't verify.
- Facts for artists/albums/genres. Track-only for v1.
- Streaming responses. Return the full list or nothing.
- User-specific personalization of facts.

## Acceptance Criteria

- `GET .../facts/` with a valid token returns 2–3 facts for a known track
  within the LLM round-trip time on cache miss, <50ms on cache hit.
- Cache hit rate verified by calling twice and asserting the second call
  doesn't hit the OpenAI client (mock it, count calls).
- Unknown track returns 404. Unauthenticated returns 401.
- LLM failure (timeout, quota, malformed output) returns 503 with a generic
  body, not a stack trace. Caller (cli-phase4 sidebar) renders "—" on 503.
- Tests mock the OpenAI client; no real API calls from the test suite.

## Execution Notes

- Portfolio classification: `moderate-bet` — low complexity, reuses existing
  OpenAI wiring, multiple clients want it.
- The `tunetrivia/services.py` pattern is almost directly reusable: same client
  initialization, same structured-output request style. Main difference is the
  system prompt and the response schema.
- Key files:
  - `backend/catalog/services/facts.py` (new)
  - `backend/catalog/views.py` (add `@action(detail=True)` to `TrackViewSet`,
    or add a standalone view)
  - `backend/catalog/urls.py` (if standalone)
  - `backend/settings/base.py` (add `JUKE_FACTS_MODEL`)
  - `backend/tunetrivia/services.py:258-344` (pattern reference, do not modify)
  - `backend/tests/unit/test_track_facts.py` (new)
- Commands:
  - `docker compose exec backend python manage.py test tests.unit.test_track_facts`
  - `docker compose exec backend python manage.py test`
- Risks:
  - LLM hallucination. "Fun facts" framing tolerates some squish, but the
    prompt needs explicit "if you don't know, say less" guidance. Returning
    1 fact is better than 3 wrong ones.
  - Cache key must include the model identifier. A model swap should bust the
    cache, not serve stale outputs from the previous model.
  - Don't make the cache TTL infinite — model behavior drifts, and occasionally
    regenerating is cheaper than a "clear facts cache" admin action.

## Handoff

- Completed:
- Next:
  - cli-phase4 consumes this. Web/mobile now-playing screens could follow.
- Blockers:
  - None. The OpenAI client is already configured (`OPENAI_API_KEY` in env,
    `openai` package in `requirements.txt` per tunetrivia usage).
