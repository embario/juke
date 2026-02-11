---
id: spotify-credentials-unification
title: Unify Spotify credentials across backend, web, and all apps
status: ready
priority: p1
owner: unassigned
area: platform
label: ALL/GENERAL
complexity: 5
updated_at: 2026-02-11
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

- Key files:
- `/Users/embario/Documents/juke/backend/juke_auth/views.py`
- `/Users/embario/Documents/juke/backend/juke_auth/urls.py`
- `/Users/embario/Documents/juke/backend/catalog/services/playback.py`
- `/Users/embario/Documents/juke/backend/settings/base.py`
- `/Users/embario/Documents/juke/web/src/features/auth/constants.ts`
- `/Users/embario/Documents/juke/web/src/features/app/components/Header.tsx`
- `/Users/embario/Documents/juke/mobile/ios/shotclock/ShotClock/Services/SpotifyManager.swift`
- `/Users/embario/Documents/juke/mobile/ios/shotclock/ShotClock/ShotClockApp.swift`
- `/Users/embario/Documents/juke/mobile/ios/juke/juke-iOS/Onboarding/OnboardingWizardView.swift`
- `/Users/embario/Documents/juke/mobile/android/juke/app/src/main/java/fm/juke/mobile/ui/onboarding/OnboardingScreen.kt`
- Commands:
- `docker compose exec backend python manage.py test`
- `docker compose exec web npm test`
- `scripts/build_and_run_ios.sh -p juke`
- `scripts/build_and_run_ios.sh -p shotclock`
- `scripts/build_and_run_android.sh -p juke`
- Risks:
- ShotClock Android appears to reference missing repository/network source files in current tree and may need codebase repair before full parity changes.
- Spotify scopes may need expansion (for example SDK/App Remote requirements), requiring coordinated env + provider app config updates.

## Handoff

- Completed:
- Task defined from cross-codebase audit of current Spotify auth/token flow.
- Next:
- Implement backend token-broker endpoints and shared Spotify token service.
- Migrate clients incrementally: web connect links, Juke mobile connect entry points, ShotClock iOS SDK auth integration.
- Add/adjust tests per service.
- Blockers:
- Confirm required Spotify scopes and callback constraints for ShotClock SDK usage.
- Resolve missing ShotClock Android data-layer files if Android parity is required in this phase.
