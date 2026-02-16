---
id: onboarding-contract-profile-unification
title: Unify onboarding contract and profile data sources across clients
status: ready
priority: p1
owner: unassigned
area: platform
label: ALL/GENERAL
complexity: 4
updated_at: 2026-02-16
---

## Goal

Define and enforce one canonical onboarding/profile contract so backend, web, iOS, and Android use identical field semantics and lifecycle behavior.

## Scope

- Define canonical payload schema for onboarding fields (`favorite_*`, `location`, `city_lat`, `city_lng`, `custom_data`).
- Normalize read/write behavior for `POST/PATCH /api/v1/music-profiles/me/` and related onboarding endpoints.
- Align web and mobile onboarding forms with the canonical schema and validation rules.
- Add contract tests to prevent key drift and accidental schema divergence.

## Out Of Scope

- Net-new onboarding questions that are not already in product scope.
- Full redesign of onboarding visuals.
- Non-profile account lifecycle changes (billing, teams, enterprise controls).

## Acceptance Criteria

- One documented onboarding/profile contract exists and is referenced by backend and client teams.
- Web, iOS, and Android send the same keys and value types for onboarding submission.
- Existing users with partial onboarding data are migrated or handled without data loss.
- Contract tests fail when schema changes are introduced without explicit versioning.

## Execution Notes

- Idea rank: `#6`
- Portfolio classification: `essential`
- Key files:
- `/Users/embario/Documents/juke/backend/juke_auth/models.py`
- `/Users/embario/Documents/juke/backend/juke_auth/serializers.py`
- `/Users/embario/Documents/juke/backend/juke_auth/views.py`
- `/Users/embario/Documents/juke/web/src/features/auth/components/onboarding/**`
- `/Users/embario/Documents/juke/mobile/ios/juke/juke-iOS/Onboarding/**`
- `/Users/embario/Documents/juke/mobile/android/juke/app/src/main/java/fm/juke/mobile/ui/onboarding/**`
- Commands:
- `docker compose exec backend python manage.py test`
- `docker compose exec web npm test`
- `scripts/build_and_run_ios.sh -p juke`
- `scripts/build_and_run_android.sh -p juke`
- Risks:
- Backward compatibility issues for users with legacy `custom_data` shape.
- Race conditions between onboarding completion and Spotify connect state transitions.

## Handoff

- Completed:
- Task defined from cross-codebase onboarding audit and schema drift risk.
- Next:
- Draft canonical contract doc and implement backend serializers/validation as source of truth.
- Blockers:

