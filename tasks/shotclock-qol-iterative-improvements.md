---
id: shotclock-qol-iterative-improvements
title: Iterate on ShotClock QoL, session reliability, and UX polish
status: in_progress
priority: p1
owner: codex
area: ios
label: IOS
complexity: 4
updated_at: 2026-02-21
---

## Goal

Ship a stable, test-backed ShotClock experience by iteratively fixing user-facing issues discovered during manual testing.

## Scope

- Improve ShotClock session lifecycle reliability (create, fetch, edit, stop, delete).
- Add and standardize QoL UI behaviors requested during iterative testing.
- Keep Spotify auth ownership backend-mediated (no app-owned Spotify OAuth flow).
- Add regression tests for each fix where practical.
- Keep AGENTS conventions aligned with iterative mobile workflow.

## Out Of Scope

- Broad redesign of ShotClock visual identity.
- Non-ShotClock feature work in unrelated clients unless required dependency.
- New streaming-provider integrations beyond current Spotify-backed playback path.

## Acceptance Criteria

- Session creation and session list refresh work reliably under normal auth state.
- Session owner can edit session parameters from session detail/lobby flow.
- Stopping/canceling active sessions requires explicit confirmation.
- Session removal from list supports swipe action with confirmation.
- Track search triggers quickly with debounce and shows an explicit loading state.
- Ephemeral in-app notifications are visible for key user actions and auto-dismiss.
- Session start/playback path enforces backend-managed Spotify linkage before runtime failure.
- New or updated tests cover each fixed behavior and pass in CI-representative runs.

## Execution Notes

- Key files:
- `/Users/embario/Documents/juke/mobile/ios/shotclock/ShotClock/ViewModels/HomeViewModel.swift`
- `/Users/embario/Documents/juke/mobile/ios/shotclock/ShotClock/Views/Home/HomeView.swift`
- `/Users/embario/Documents/juke/mobile/ios/shotclock/ShotClock/Views/Session/CreateSessionView.swift`
- `/Users/embario/Documents/juke/mobile/ios/shotclock/ShotClock/Views/Session/AddTracksView.swift`
- `/Users/embario/Documents/juke/mobile/ios/shotclock/ShotClock/ViewModels/SessionLobbyViewModel.swift`
- `/Users/embario/Documents/juke/mobile/ios/shotclock/ShotClockTests/ShotClockTests.swift`
- `/Users/embario/Documents/juke/backend/powerhour/views.py`
- `/Users/embario/Documents/juke/backend/tests/api/test_powerhour_sessions.py`
- Commands:
- `scripts/build_and_run_ios.sh -p shotclock`
- `scripts/test_mobile.sh -p shotclock --ios-only`
- `docker compose exec backend python manage.py test tests.api.test_powerhour_sessions`
- Risks:
- Iterative fixes may span app, backend, and test fixtures in the same cycle; keep each issue isolated and verified before proceeding.
- Existing local workspace includes parallel Spotify-unification edits; avoid accidental regressions while landing QoL changes.

## Handoff

- Completed:
- Added owner-only session edit flow from lobby (`Edit` action + prefilled session config + update endpoint wiring).
- Added end-session confirmation dialog in active playback.
- Added swipe-to-remove session action on home list with destructive confirmation dialog.
- Added transient flash notifications via JukeKit flash center/overlay for create/join/update/delete flows.
- Added reusable JukeKit track search UI components and adopted them in ShotClock (`JukeKitTrackSearchField`, `JukeKitTrackSearchLoadingView`).
- Updated track search behavior to debounce at 0.5s with explicit loading state.
- Filtered ended sessions from list display and local session upsert handling.
- Added regression tests for key view-model behavior (session upsert/filter, create-session prefill, debounce constant).
- Added JukeKit flash-center tests.
- Added integration-style ShotClock tests with request stubbing for edit/save (`CreateSessionViewModel.updateSession`), delete confirmation action path (`HomeViewModel.deleteSession`), and end-session confirmation action path (`PlaybackViewModel.endSession`).
- Standardized ShotClock iOS deployment target to `26.0` across project + app/test/UI-test build settings in the Xcode project.
- Hardened integration tests to support request-path normalization and streamed request bodies in URLProtocol stubs.
- Verified iOS + JukeKit test runs via `scripts/test_mobile.sh -p shotclock --ios-only --include-jukekit-tests`.
- Verified ShotClock iOS tests via `scripts/test_mobile.sh -p shotclock --ios-only` and app run via `scripts/build_and_run_ios.sh -p shotclock`.
- Remaining work:
- Continue iterative manual QA passes and log-driven fixes for any additional reliability/UX issues discovered.
- Decide and implement whether Spotify linkage should be required at session creation time (currently enforced at session start time).
- Do final polish sweep for copy consistency, edge-case error states, and loading/empty states.
- Keep bundling these QoL updates with Spotify unification PR scope as requested.
- Blockers:
- None currently; active task remains open for continued iterative testing.
