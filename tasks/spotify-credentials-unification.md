---
id: spotify-credentials-unification
title: Unify Spotify credentials across backend, web, and all apps
status: in_progress
priority: p1
owner: codex
area: platform
label: ALL/GENERAL
complexity: 5
updated_at: 2026-02-16
---

## Goal

Implement a single Spotify account-linking and token model so users connect once through Juke and all clients reuse backend-managed Spotify credentials.

## Scope

- Add backend Spotify credential broker capabilities for authenticated Juke users.
- Reuse backend-owned Spotify refresh tokens to issue short-lived Spotify access tokens to clients that need direct Spotify SDK/API auth.
- Standardize Spotify connect flows across web, Juke mobile, and ShotClock mobile.
- Remove/replace per-client Spotify OAuth patterns that duplicate credential ownership.
- Add tests for new backend auth/token endpoints and updated client flows.

## Out Of Scope

- Adding non-Spotify streaming providers.
- Full redesign of onboarding/auth UX beyond flow wiring required for unified credentials.
- Broad auth-system migration away from existing DRF token auth.

## Acceptance Criteria

- Backend exposes authenticated Spotify provider endpoints for connection status.
- Backend exposes an authenticated endpoint that issues short-lived Spotify access tokens without exposing refresh tokens.
- Backend exposes an authenticated disconnect/revoke endpoint for Spotify linkage.
- Existing backend Spotify playback path continues to function with unified token management.
- Web Spotify connect actions consistently route through backend user-link flow (no split between direct social login and account-connect links for authenticated users).
- Juke iOS and Juke Android include working Spotify connect entry points tied to backend connect flow.
- ShotClock iOS no longer depends on standalone in-app Spotify OAuth ownership; it uses backend-issued short-lived Spotify access tokens for Spotify SDK auth.
- Client regression checks pass for login, connect, playback gating, and reconnect/error paths.
- Security controls are documented and implemented for token issue endpoint (rate limiting + no refresh token exposure).

## Execution Notes

- Idea rank: `#3`
- Portfolio classification: `essential`
- Linked dependencies: `shotclock-android-data-layer-recovery`, `onboarding-contract-profile-unification`.
- Key files:
- `/Users/embario/Documents/juke/backend/juke_auth/views.py`
- `/Users/embario/Documents/juke/backend/juke_auth/urls.py`
- `/Users/embario/Documents/juke/backend/juke_auth/spotify_credentials.py`
- `/Users/embario/Documents/juke/backend/catalog/services/playback.py`
- `/Users/embario/Documents/juke/backend/settings/base.py`
- `/Users/embario/Documents/juke/web/src/features/app/components/Header.tsx`
- `/Users/embario/Documents/juke/web/src/features/auth/components/onboarding/api/onboardingApi.ts`
- `/Users/embario/Documents/juke/web/src/features/auth/components/onboarding/steps/ConnectStep.tsx`
- `/Users/embario/Documents/juke/mobile/ios/juke/juke-iOS/Onboarding/OnboardingWizardView.swift`
- `/Users/embario/Documents/juke/mobile/android/juke/app/src/main/java/fm/juke/mobile/ui/onboarding/OnboardingScreen.kt`
- `/Users/embario/Documents/juke/backend/tests/api/test_spotify_credentials.py`
- `/Users/embario/Documents/juke/backend/tests/api/test_spotify_connect.py`
- `/Users/embario/Documents/juke/backend/tests/api/test_playback.py`
- Commands:
- `docker compose exec backend python manage.py test tests.api.test_spotify_credentials tests.api.test_spotify_connect tests.api.test_powerhour_sessions tests.api.test_playback`
- `docker compose exec web npm test`
- `scripts/build_and_run_ios.sh -p juke`
- `scripts/build_and_run_ios.sh -p shotclock`
- `scripts/build_and_run_android.sh -p juke`
- Risks:
- ShotClock Android appears to reference missing repository/network source files in current tree and may need codebase repair before full parity changes.
- Spotify scopes may need expansion (for example SDK/App Remote requirements), requiring coordinated env + provider app config updates.

## Handoff

- Completed:
- Added backend credential broker service with token status, access-token issue, refresh behavior, and disconnect support.
- Added authenticated backend endpoints: `/api/v1/auth/spotify/status/`, `/api/v1/auth/spotify/token/`, `/api/v1/auth/spotify/disconnect/`.
- Added token issue throttle (`spotify_token_issue`) and mobile deep-link return-scheme support for connect callback routing.
- Migrated backend playback token refresh path to use shared broker service instead of inline provider token logic.
- Updated web Spotify connect flows (header + onboarding) to use backend connect entry path.
- Updated Juke iOS and Juke Android onboarding connect flows to route through backend connect endpoint.
- Added backend regression tests for connect flow, broker endpoints, powerhour Spotify gate, and playback refresh retry path.
- Verified targeted backend tests pass in Docker.
- Remaining work:
- Decide and implement policy for legacy direct social-auth token login path (`SocialAuth`) so clients cannot bypass backend-managed flow unintentionally.
- Decide whether disconnect semantics require provider-side revoke or if local unlink is sufficient; implement/document final behavior.
- Add explicit throttle-limit regression test for `/api/v1/auth/spotify/token/` (`429` behavior).
- Confirm and document final required Spotify scopes for all target clients and playback paths.
- Update task/PR documentation with final backend contract and rollout notes once merged.
- Blockers:
- No technical blockers; remaining items are mostly policy/contract decisions and hardening.
