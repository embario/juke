---
id: provider-neutral-catalog-read-through
title: Add provider-neutral catalog search and read-through cache foundations
status: done
priority: p1
owner: codex-provider-neutral-catalog
area: backend
label: BACKEND
complexity: 4
updated_at: 2026-09-03
---

## Goal

Make external catalog search and cached identity provider-neutral while preserving existing Spotify-default API behavior and data.

## Scope

- Add a validated catalog provider selector with Spotify as the compatibility default.
- Route external catalog requests through a provider adapter registry rather than constructing Spotify directly.
- Represent provider identifiers, provenance, and cache freshness without fabricating Spotify IDs.
- Preserve legacy `spotify_id` and `spotify_data` reads/writes for current clients.
- Define a deterministic, disabled-by-default Apple Music adapter contract if credentials are absent.
- Add focused API, unit, and migration tests plus backend documentation.

## Out Of Scope

- Bulk mirroring either provider catalog.
- Production Apple developer tokens or secrets.
- Replacing the canonical ML identity graph.
- Client-side UX changes or deployment.

## Acceptance Criteria

- Existing `external=true&q=...` requests still default to Spotify.
- An explicit supported provider routes to the matching registered adapter.
- Unknown or unconfigured providers fail with a stable validation/service error.
- Cached resources retain provider ID, payload provenance, retrieval time, and freshness policy without cross-provider collisions.
- Non-Spotify results can be represented without a fake `spotify_id`.
- Tests make no live provider calls and cover routing, compatibility, identity isolation, and cache metadata.

## Execution Notes

- Mode: ASYNC.
- Key files: `backend/catalog/views.py`, `backend/catalog/api_clients.py`, `backend/catalog/controllers.py`, `backend/catalog/models.py`, `backend/catalog/serializers.py`, `backend/tests/`.
- Commands: focused Django tests and `ruff check`, preferably through Docker Compose.
- Risks: existing models and serializers assume non-null unique Spotify IDs; migrations must remain additive and backward-compatible.

## Handoff

- Completed: Added provider validation/registry routing with Spotify as the default; made legacy Spotify IDs nullable; enriched all external-identifier bridges with provider payload, URL, market, refresh, and expiry metadata; backfilled legacy Spotify identities; added a neutral resource upsert contract; made Spotify search populate provenance; exposed provider identifiers to clients; documented the Apple Music adapter prerequisites.
- Validation: 44 focused API/unit/migration and legacy Spotify tests passed against temporary PostgreSQL 14 with provider calls stubbed; `makemigrations --check --dry-run catalog`, Python compile checks, Ruff lint, and `git diff --check` passed.
- Next: Implement and register `AppleMusicAPIClient` only after developer-token signing/storage, storefront behavior, payload normalization, and provider-policy cache/artwork rules are approved.
- Blockers: Docker Desktop was unavailable, so the repository Compose test path was not run locally; full CI remains required.
