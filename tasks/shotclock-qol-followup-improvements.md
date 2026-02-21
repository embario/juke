---
id: shotclock-qol-followup-improvements
title: Follow-up ShotClock QoL improvements and polish pass
status: ready
priority: p1
owner: unassigned
area: ios
label: IOS
complexity: 3
updated_at: 2026-02-21
---

## Goal

Close out remaining ShotClock QoL work from iterative improvements with a focused follow-up pass on QA, Spotify-link enforcement timing, and UX polish.

## Scope

- Run additional manual QA loops on session lifecycle flows (create, edit, delete, start, stop/end, lobby refresh).
- Decide whether Spotify linkage is enforced at session creation time or only at session start time, then implement the chosen behavior.
- Polish copy, loading/empty states, and edge-case error states in key ShotClock views.
- Add targeted regression tests for any newly fixed issues discovered in this pass.

## Out Of Scope

- Broad visual redesign.
- Non-ShotClock feature work outside dependencies needed for this task.
- New provider integrations beyond current Spotify-backed behavior.

## Acceptance Criteria

- Manual QA pass is completed and any discovered issues are fixed or captured with clear follow-up notes.
- Spotify-link enforcement decision is documented in handoff and reflected in implementation.
- Session lifecycle flows behave consistently in normal authenticated use.
- Loading, empty, and error states are clear and consistent in the touched flows.
- All ShotClock iOS tests pass via `scripts/test_mobile.sh -p shotclock --ios-only` after changes.

## Execution Notes

- Key files:
- `/Users/embario/Documents/juke/mobile/ios/shotclock/ShotClock/Views/Home/HomeView.swift`
- `/Users/embario/Documents/juke/mobile/ios/shotclock/ShotClock/Views/Session/SessionLobbyView.swift`
- `/Users/embario/Documents/juke/mobile/ios/shotclock/ShotClock/Views/Session/PlaybackView.swift`
- `/Users/embario/Documents/juke/mobile/ios/shotclock/ShotClock/Views/Session/CreateSessionView.swift`
- `/Users/embario/Documents/juke/mobile/ios/shotclock/ShotClock/ViewModels/HomeViewModel.swift`
- `/Users/embario/Documents/juke/mobile/ios/shotclock/ShotClock/ViewModels/SessionLobbyViewModel.swift`
- `/Users/embario/Documents/juke/mobile/ios/shotclock/ShotClock/ViewModels/PlaybackViewModel.swift`
- `/Users/embario/Documents/juke/mobile/ios/shotclock/ShotClockTests/ShotClockTests.swift`
- `/Users/embario/Documents/juke/backend/powerhour/views.py`
- `/Users/embario/Documents/juke/backend/tests/api/test_powerhour_sessions.py`
- Commands:
- `scripts/build_and_run_ios.sh -p shotclock`
- `scripts/test_mobile.sh -p shotclock --ios-only`
- `docker compose exec backend python manage.py test tests.api.test_powerhour_sessions`
- Risks:
- Behavior changes around Spotify enforcement timing may affect onboarding friction and session-start reliability.
- Manual QA findings may span backend + iOS in the same loop and should be landed incrementally to reduce regression risk.

## Handoff

- Completed:
- Seeded from the remaining work in `tasks/shotclock-qol-iterative-improvements.md` after integration-style tests and iOS 26.0 deployment-target alignment were completed.
- Next:
- Execute manual QA loop, apply fixes, then re-run iOS/backend tests.
- Finalize and document Spotify-link enforcement timing decision.
- Blockers:
- None currently.
