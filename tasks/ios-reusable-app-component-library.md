---
id: ios-reusable-app-component-library
title: Reusable App component library
status: in-progress
priority: p2
owner: claude
area: ios
label: IOS
complexity: 5
updated_at: 2026-02-11
---

## Goal

Establish a reusable iOS app component library (JukeCore) that encapsulates common functionality across Juke, ShotClock, and TuneTrivia apps.

## Scope

- Create `JukeCore` Swift Package under `mobile/ios/Packages/JukeCore/`
- Extract networking layer (APIClient, APIConfiguration, APIError)
- Extract authentication system (AuthService, auth models, AppConfiguration)
- Extract session state management (SessionStore with delegate protocol)
- Extract user/profile models and services
- Extract themeable design system components
- Extract deep-link handling with registration fallback to web
- Extract AuthViewModel
- Remove SpotifyiOS SDK from ShotClock and migrate to backend playback
- Include unit tests for extracted components
- Document component usage and conventions

## Out Of Scope

- Full visual redesign unrelated to component reuse
- Android/web component library implementation (tracked separately)
- New feature development beyond shared component extraction

## Acceptance Criteria

- [x] Architecture document exists at `docs/arch/ios-jukecore-architecture.md`
- [x] JukeCore Swift Package created with proper structure
- [ ] All three apps consume JukeCore for shared functionality
- [ ] Duplicate UI/logic implementations removed from each app
- [ ] SpotifyiOS SDK removed from ShotClock (uses backend playback)
- [x] Registration in satellite apps falls back to web URL when Juke app not installed (JukeDeepLinkHandler.openJukeAppForRegistration + webRegistrationURL)
- [x] Unit tests exist for JukeCore components (120 tests)
- [ ] iOS tests/builds pass for all three apps after refactor

## Execution Notes

- Key files:
  - Architecture doc: `docs/arch/ios-jukecore-architecture.md`
  - Package location: `mobile/ios/Packages/JukeCore/`
  - Juke app: `mobile/ios/juke/`
  - ShotClock app: `mobile/ios/shotclock/`
  - TuneTrivia app: `mobile/ios/tunetrivia/`
- Commands:
  - Build iOS: `scripts/build_and_run_ios.sh -p <project>`
  - Test iOS: `scripts/test_mobile.sh -p <project> --ios-only`
- Risks: Large refactor surface; iterative rollout required
- Minimum iOS target: iOS 16.0 (ShotClock constraint)

## SpotifyiOS SDK Investigation

**Finding:** ShotClock uses SpotifyiOS SDK (`SPTAppRemote`) for direct playback control:
- `SpotifyManager.swift` (209 lines) uses `SPTAppRemote` to authorize and control Spotify playback
- Falls back to `AVPlayer` with preview URLs when Spotify app not installed
- Used in `PlaybackViewModel.swift` for Power Hour track playback

**Recommendation:** Remove SpotifyiOS SDK and migrate to backend playback approach:
- Juke app already uses `PlaybackService.swift` which calls `/api/v1/playback/` endpoints
- Backend controls Spotify via server-side credentials (no client SDK needed)
- Benefits: Simpler client code, no SDK dependency, consistent with Juke approach
- Migration: Replace `SpotifyManager` calls with `PlaybackService` API calls

## Progress Log

| Date | Phase | Work Done |
|------|-------|-----------|
| 2026-02-11 | Audit | Analyzed all 3 iOS apps, identified ~1,600 lines of duplicate code |
| 2026-02-11 | Design | Created architecture document at `docs/arch/ios-jukecore-architecture.md` |
| 2026-02-11 | Investigation | Audited SpotifyiOS SDK usage in ShotClock - can be replaced with backend playback |
| 2026-02-11 | Phase 1 | Created JukeCore Swift Package structure at `mobile/ios/Packages/JukeCore/` |
| 2026-02-11 | Phase 2 | Extracted Networking Layer: JukeAPIClient, JukeAPIConfiguration, JukeAPIError, JukeHTTPMethod, JukeDateParsing (27 tests passing) |
| 2026-02-11 | Phase 3 | Extracted Auth Layer: JukeAuthService, JukeAuthModels, JukeAppConfiguration (60 tests passing) |
| 2026-02-11 | Phase 4 | Extracted Session Management: JukeSessionStore, JukeMusicProfile, JukeProfileService, JukePaginatedResponse (79 tests passing) |
| 2026-02-11 | Phase 5 | Skipped - No additional shared models needed (JukeUser not used in apps) |
| 2026-02-11 | Phase 6 | Extracted Design System: JukeTheme protocol, built-in themes (JukeDefaultTheme, ShotClockTheme, TuneTriviaTheme), themeable components (JukeCoreBackground, JukeCoreCard, JukeCoreButtonStyle, JukeCoreInputField, JukeCoreStatusBanner, JukeCoreSpinner, JukeCoreChip), Color(hex:) extension (92 tests passing) |
| 2026-02-11 | Phase 7 | Extracted Deep Links & ViewModels: JukeDeepLink, JukeDeepLinkParser, JukeDeepLinkHandler, JukeAuthViewModel, URLComponents.queryParameters extension (120 tests passing) |

## Handoff

- Completed:
  - Full audit of Juke, ShotClock, TuneTrivia iOS apps
  - Architecture document with 7-phase implementation plan
  - SpotifyiOS SDK investigation - confirmed removal feasible
  - Phase 1: JukeCore Swift Package created at `mobile/ios/Packages/JukeCore/`
  - Phase 2: Networking Layer extracted (JukeAPIClient, JukeAPIConfiguration, JukeAPIError, JukeHTTPMethod, JukeDateParsing)
  - Phase 3: Auth Layer extracted (JukeAuthService, JukeAuthModels, JukeAppConfiguration)
  - Phase 4: Session Management extracted (JukeSessionStore, JukeMusicProfile, JukeProfileService, JukePaginatedResponse)
  - Phase 6: Design System extracted (JukeTheme, built-in themes, themeable components)
  - Phase 7: Deep Links & ViewModels extracted (JukeDeepLink, JukeDeepLinkParser, JukeDeepLinkHandler, JukeAuthViewModel)
  - **120 unit tests passing**
- Next:
  - Migrate Juke app to use JukeCore
  - Migrate ShotClock app to use JukeCore
  - Migrate TuneTrivia app to use JukeCore
  - Remove duplicate code from each app
  - Remove SpotifyiOS SDK from ShotClock
- Blockers:
  - None currently
