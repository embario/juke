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

## Out Of Scope

- Neptune deployment, Spotify-first web login, Radio slices owned by other agents.

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
- 94 unit tests passed (unsigned CI); added deployed-contract, fresh state and
  mismatched-state regression checks. Signed universal Release build passed;
  strict code signature verification passed. Logs: build/auth-handoff-tests.log
  and build/auth-handoff-release.log.
- Relaunched isolated Release/Juke.app and verified native Sign in opens Chrome
  at Neptune's login page with deployed juke-vibe-mac contract. Credentials and
  completed account handoff require user retest; no credentials accessed.
- No remote deployment or installed app replacement. The renamed client contract
  can replace this compatibility protocol once Neptune's web/backend support it.
