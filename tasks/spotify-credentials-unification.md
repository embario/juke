---
id: spotify-credentials-unification
title: Unify Spotify credentials across backend, web, and all apps
status: review
priority: p1
owner: codex
area: platform
label: ALL/GENERAL
complexity: 5
updated_at: 2026-02-21
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
- Backend exposes an authenticated disconnect/unlink endpoint for Spotify linkage.
- Existing backend Spotify playback path continues to function with unified token management.
- Web Spotify connect actions consistently route through backend user-link flow (no split between direct social login and account-connect links for authenticated users).
- Juke iOS and Juke Android include working Spotify connect entry points tied to backend connect flow.
- ShotClock iOS no longer depends on standalone in-app Spotify OAuth ownership or Spotify SDK dependencies.
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
- Any future return to client-owned Spotify SDK flows would require scope expansion and provider app configuration updates (out of scope here).

### Final Spotify Scope Set (2026-02-21)

- `user-read-playback-state`
- `user-read-currently-playing`
- `user-modify-playback-state`
- No additional Spotify SDK/App Remote scopes are required for this task because clients use backend-managed playback and link state.

### Final Backend Contract (2026-02-21)

- `GET /api/v1/auth/spotify/status/`
- Auth required: Juke token/session
- Returns connection metadata (`connected`, `spotify_user_id`, `scopes`, `expires_at`, `expires_in`, `has_refresh_token`)
- `POST /api/v1/auth/spotify/token/`
- Auth required: Juke token/session
- Returns short-lived Spotify access token payload (`provider`, `token_type`, `access_token`, `expires_at`, `expires_in`)
- Refresh token is never returned to clients
- Rate limited by `spotify_token_issue` (`SPOTIFY_TOKEN_ISSUE_RATE`)
- `POST /api/v1/auth/spotify/disconnect/`
- Auth required: Juke token/session
- Semantics: local unlink only (delete `UserSocialAuth` link); no provider-side revoke in this task
- `POST /api/v1/auth/social-login/`
- Intended for Spotify-backed bootstrap login/signup flow
- Guardrail: already-authenticated callers are rejected (`409`) and directed to `/api/v1/auth/connect/spotify/`

### Rollout Notes (2026-02-21)

- Keep existing Spotify app credentials and redirect URI configuration.
- Ensure env includes:
- `SOCIAL_AUTH_SPOTIFY_SCOPE`
- `SPOTIFY_CONNECT_ALLOWED_RETURN_SCHEMES`
- `SPOTIFY_TOKEN_ISSUE_RATE`
- Deploy backend first (new broker endpoints + `social-login` guard), then clients.
- Follow-up onboarding behavior for first-time Spotify signup is tracked separately in `tasks/spotify-provider-signup-onboarding.md`.

## Handoff

- Completed:
- Added backend credential broker service with token status, access-token issue, refresh behavior, and disconnect support.
- Added authenticated backend endpoints: `/api/v1/auth/spotify/status/`, `/api/v1/auth/spotify/token/`, `/api/v1/auth/spotify/disconnect/`.
- Added token issue throttle (`spotify_token_issue`) and mobile deep-link return-scheme support for connect callback routing.
- Migrated backend playback token refresh path to use shared broker service instead of inline provider token logic.
- Updated web Spotify connect flows (header + onboarding) to use backend connect entry path.
- Updated Juke iOS and Juke Android onboarding connect flows to route through backend connect endpoint.
- Added backend regression tests for connect flow, broker endpoints, powerhour Spotify gate, and playback refresh retry path.
- Added backend regression test for Spotify token issue throttling (`429`) on `/api/v1/auth/spotify/token/`.
- `SocialAuth` now rejects already-authenticated callers and points them to `/api/v1/auth/connect/spotify/`.
- Confirmed disconnect semantics for this task are local unlink (`UserSocialAuth` removal), not provider-side revoke.
- Confirmed ShotClock iOS no longer contains Spotify SDK dependencies (`SpotifyiOS`/`SPT*`).
- Verified backend tests pass in Docker:
- `docker compose exec backend python manage.py test tests.api.test_spotify_credentials tests.api.test_spotify_connect tests.api.test_powerhour_sessions tests.api.test_playback tests.api.test_login`
- Verified web tests pass in Docker:
- `docker compose exec web npm test`
- Verified mobile build/run scripts complete:
- `scripts/build_and_run_ios.sh -p juke`
- `scripts/build_and_run_ios.sh -p shotclock`
- `scripts/build_and_run_android.sh -p juke` (Emulator PID `47358`, App PID `3477`)
- Remaining work:
- None inside this task scope.
- Follow-up tracked separately: `tasks/spotify-provider-signup-onboarding.md`.
- Blockers:
- None.
