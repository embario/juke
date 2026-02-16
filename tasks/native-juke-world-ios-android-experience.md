---
id: native-juke-world-mobile
title: Deliver native Juke World experience for iOS and Android
status: ready
priority: p2
owner: unassigned
area: clients
label: CLIENTS
complexity: 4
updated_at: 2026-02-16
---

## Goal

Replace mobile webview-style world access with native iOS and Android Juke World experiences that use the same backend globe/profile data APIs.

## Scope

- Implement native world map/globe surfaces for Juke iOS and Juke Android.
- Hook onboarding completion and explicit navigation into native world entry points.
- Support user pin selection, profile preview, and deep-link to full profile.
- Align visual semantics with web world signals (`clout`, top genre color) while staying native.

## Out Of Scope

- Exact 3D parity with web rendering internals.
- ShotClock and TuneTrivia world experiences.
- Social feed or messaging overlays.

## Acceptance Criteria

- Juke iOS renders a native world view backed by `/api/v1/music-profiles/globe/`.
- Juke Android renders a native world view backed by `/api/v1/music-profiles/globe/`.
- Both clients support focus-on-self from onboarding completion state.
- Build/run scripts pass for both platforms after integration.

## Execution Notes

- Idea rank: `#11`
- Portfolio classification: `experimental`
- Key files:
- `/Users/embario/Documents/juke/mobile/ios/juke/juke-iOS/Views/JukeWorldView.swift`
- `/Users/embario/Documents/juke/mobile/ios/juke/juke-iOS/ContentView.swift`
- `/Users/embario/Documents/juke/mobile/android/juke/app/src/main/java/fm/juke/mobile/ui/world/JukeWorldScreen.kt`
- `/Users/embario/Documents/juke/mobile/android/juke/app/src/main/java/fm/juke/mobile/ui/navigation/JukeApp.kt`
- `/Users/embario/Documents/juke/backend/juke_auth/views.py`
- Commands:
- `scripts/build_and_run_ios.sh -p juke`
- `scripts/build_and_run_android.sh -p juke`
- `docker compose exec backend python manage.py test`
- Risks:
- Mobile GPU/performance constraints for large point sets.
- Divergent interaction patterns versus the established web globe experience.

## Handoff

- Completed:
- Task established to convert current mobile world entry into native-first implementations.
- Next:
- Finalize platform-specific rendering approach and ship one-client prototype first.
- Blockers:

