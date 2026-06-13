---
id: mlcore-spotify-output-resolution-from-isrc
title: MLCore platform URI resolution from ISRC aliases
status: ready
priority: p1
owner: unassigned
area: platform
label: BACKEND/ML
labels:
  - juke-task
  - mlcore
  - backend
  - recommender
  - identity
complexity: 4
updated_at: 2026-06-09
---

## Goal

Resolve MLCore recommendation candidates into external music-platform IDs and URIs, starting with Spotify track IDs for the downstream recommendation API contract.

## Scope

- Use ISRC aliases as the preferred bridge from canonical items to platform track IDs.
- Query Spotify Search with `isrc:<code>` for prioritized canonical items as the first provider implementation.
- Store resolved platform aliases in `mlcore_canonical_item_alias`, including Spotify track IDs and URIs.
- Add confidence/evidence metadata for each platform match.
- Ensure MLCore serving can return Spotify IDs only, with graceful omission of unresolved recommendations.
- Keep the resolver/provider interface generic enough to add Apple Music, YouTube Music, Deezer, Tidal, or other provider URIs without changing canonical identity semantics.

## Out Of Scope

- Training ML models from Spotify content.
- Resolving all 123M canonical items eagerly.
- Public HTTPS/auth changes.

## Acceptance Criteria

- Resolver prioritizes items likely to be served, such as high-score recommendation candidates and popular corpus items.
- Resolver respects provider rate limits and retries/backoff.
- Platform aliases are idempotent and conflict-aware.
- Spotify aliases store both normalized track IDs and URI forms, for example `spotify:track:<id>`.
- Serving endpoint can return:
  - seed Spotify IDs accepted
  - recommendation Spotify IDs returned
  - unresolved candidates filtered or reported according to API contract
- Tests cover match scoring, no-result handling, conflict behavior, and serving response shape.

## Execution Notes

- Spotify and other provider metadata are for serving output resolution, not model training input unless provider policy explicitly permits training use.
- Avoid full-corpus eager resolution unless a capacity plan proves it is affordable and compliant.
- This task should grow the shared identity graph over time: ISRC in, provider URI aliases out.
- Risks:
  - Spotify search can return territory-specific or remastered variants.
  - Multiple provider tracks may share an ISRC.
  - Rate limits make naive full-corpus resolution impractical.

## Handoff

- Completed: task created.
- Next: implement after ISRC alias enrichment.
- Blockers: `mlcore-isrc-alias-enrichment`.
