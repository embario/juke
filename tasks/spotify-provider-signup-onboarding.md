---
id: spotify-provider-signup-onboarding
title: Support onboarding-complete registration flow for Spotify-first signup
status: ready
priority: p1
owner: unassigned
area: platform
label: ALL/GENERAL
complexity: 4
updated_at: 2026-02-21
---

## Goal

Ensure users who create a Juke account via Spotify (`social-login`) complete the same registration/onboarding flow required for full profile setup.

## Scope

- Define backend contract for Spotify-first auth outcomes (newly created user vs existing user).
- Ensure newly created Spotify users are routed into the onboarding/profile completion flow before treated as fully onboarded.
- Wire web and mobile clients to honor the new contract and continue into onboarding when required.
- Preserve existing login behavior for returning users who already completed onboarding.
- Add regression tests for backend auth responses and client routing decisions.

## Out Of Scope

- Adding non-Spotify provider signup paths.
- Redesigning onboarding UX or introducing new onboarding steps.
- Changing the unified Spotify credential broker endpoints.

## Acceptance Criteria

- `POST /api/v1/auth/social-login/` returns a deterministic signal indicating onboarding is required for first-time Spotify signups.
- First-time Spotify signups are redirected/routed to onboarding on web and supported mobile clients.
- Existing Spotify-linked users can still sign in without forced onboarding replay.
- Login + onboarding transition tests cover first-time and returning Spotify users.
- Task explicitly documents any required data-migration or backfill behavior (if needed).

## Execution Notes

- Related tasks:
- `tasks/spotify-credentials-unification.md`
- `tasks/onboarding-contract-and-profile-source-unification.md`
- Key files:
- `/Users/embario/Documents/juke/backend/juke_auth/views.py`
- `/Users/embario/Documents/juke/backend/juke_auth/serializers.py`
- `/Users/embario/Documents/juke/backend/tests/api/test_login.py`
- `/Users/embario/Documents/juke/web/src/features/auth/routes/LoginRoute.tsx`
- `/Users/embario/Documents/juke/web/src/features/auth/hooks/useAuth.ts`
- `/Users/embario/Documents/juke/mobile/ios/Packages/JukeKit/Sources/JukeKit/Auth/JukeAuthService.swift`
- `/Users/embario/Documents/juke/mobile/android/juke/app/src/main/java/fm/juke/mobile/ui/auth/AuthViewModel.kt`
- Commands:
- `docker compose exec backend python manage.py test tests.api.test_login`
- `docker compose exec web npm test`
- `scripts/build_and_run_ios.sh -p juke`
- `scripts/build_and_run_android.sh -p juke`
- Risks:
- Existing users missing profile completion timestamps may require careful fallback logic.
- Mobile auth contracts must remain backward compatible during staged rollout.

## Handoff

- Completed:
- Task created from Spotify-credentials-unification split: social-login onboarding completion is now tracked separately.
- Next:
- Define backend response contract for first-time Spotify signup and update clients to route accordingly.
- Blockers:
- None.
