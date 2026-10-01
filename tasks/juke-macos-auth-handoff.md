---
id: juke-macos-auth-handoff
title: Restore Mac sign-in handoff against deployed Neptune
status: review
priority: p1
owner: codex
area: clients
label: CLIENTS
complexity: 3
updated_at: 2026-10-01
---

## Goal

Return browser sign-in to the new Juke Mac test build with a verified Juke session.

## Scope

- Keep `com.juke.mac`; use the deployed `juke-vibe-mac` PKCE protocol for compatibility.
- Capture authentication callbacks with ASWebAuthenticationSession so parallel
  installed copies do not steal them through Launch Services.
- Rebuild, verify signature and relaunch the isolated executable.
- Fix web authorization callback delivery under React StrictMode, prepare a
  focused deployment patch that preserves Neptune's Journal auth integration.

## Out Of Scope

- Neptune deployment without user approval, Spotify-first web login, Radio slices owned by other agents.

## Acceptance Criteria

- Browser URL and exchange agree on a deployed client/redirect pair.
- Callback still validates state, server, code and PKCE verifier.
- Browser cancellation does not display a misleading sign-in failure.
- Unit regression checks and signed build pass; user verifies real credential flow.

## Execution Notes

- ITERATIVE. Worktree is juke-radio-listening-room.
- Read-only Neptune Docker inspection confirms deployed allowlist contains only
  `juke-vibe-mac` and `juke-vibe-ios`; deployed web parser matches that list.
- Current app PID 43462 remained on initial authentication screen after web login.
- Risk: installed copies share URL schemes. Use OS authentication sessions rather
  than changing global scheme ownership or registering another legacy app scheme.

## Handoff

- Root cause verified; no remote server files or other worktrees changed.
- Implemented deployed sign-in protocol in ASWebAuthenticationSession; bundle ID
  remains com.juke.mac. State/server/PKCE checks remain intact. Duplicate starts
  are blocked; cancellation clears pending attempt and server changes cancel UI.
- 95 unit tests passed (unsigned CI); added deployed-contract, fresh state and
  mismatched-state regression checks. Signed universal Release build passed;
  strict code signature verification passed. Logs: build/auth-handoff-tests.log
  and build/auth-handoff-release.log.
- Relaunched isolated Release/Juke.app and verified native Sign in opens Chrome
  at Neptune's login page with deployed juke-vibe-mac contract. Credentials and
  completed account handoff require user retest; no credentials accessed.
- No remote deployment or installed app replacement. The renamed client contract
  can replace this compatibility protocol once Neptune's web/backend support it.
- Live test exposed a Swift 6 actor assertion on Apple's SafariLaunchAgent XPC
  callback queue (PID 66168, crash report Juke-2026-10-01-170621.ips). Moved
  completion creation to a nonisolated Sendable helper; added a regression invoking
  it on a background queue from MainActor. Rebuilt, verified signature and relaunched.
- User retest: app PID 67362 still waits; Neptune logs authorization HTTP 200
  without any code exchange. Running web uses React StrictMode; its replay cleanup
  discards the response while its started ref suppresses the replacement listener.
- Web fix reuses one authorization promise across effect replay and attaches a
  fresh active listener. Submit takes ownership before login updates the context.
- Seven focused web tests pass, including callback delivery under StrictMode and
  no redirect after real unmount. The same regression fails against original code.
  TypeScript build and targeted ESLint pass.
- Concrete deployment patch: build/neptune-sign-in.patch, generated against the
  exact running LoginRoute and preserving its Journal authorization path. Only
  LoginRoute and browserRedirect helper change; user approval required to apply.
