---
id: juke-ios-polish-round1
title: Juke iOS polish round 1 (owner feedback from first on-device test)
status: ready
priority: p1
owner: unassigned
area: clients
label: CLIENTS
complexity: 4
updated_at: 2026-10-08
---

## Goal

Fix the nine items the owner found when running the merged iOS app (`com.juke.app`) on an iPhone 15 Pro, so the phone app matches the macOS app (`macos/juke`) and `docs/design/juke-app/Round3.reference.html`. Source of truth: the owner's polish brief (`juke-ios-polish-round1.md` in the agent-deck data directory).

## Scope

Nine items, each one small PR into `integration/juke-app`:

1. **T1+T2 Layout (one item):** Chat message pane is hidden behind the "Listening for Music" bar and the keyboard covers the tab bar; the Radio tuner text is clipped by the tab bar. Respect tab bar and now-playing bar insets; composer above the keyboard; keyboard dismissible; tab bar reachable.
2. **T3 New station wizard:** flicking the dial to "+ New" transitions into a wizard (feelings or artists/albums/songs seeds, name, description), matching the Mac flow; seeds reach `POST /api/v1/radio/stations/`.
3. **T4 New memory flow:** Mac interaction adapted for touch; saving still works.
4. **T5 Vinyl swipe-to-close:** tracks the finger, settles naturally, cancellable.
5. **T6 Artwork-derived background:** find why the shared theme (#187) is not applied on iOS and wire it with the animated transition.
6. **T7 Memory thumbnails/artwork:** photo/video thumbnails and song artwork instead of filenames.
7. **T8 Library browsing:** album -> tracks (tap plays; menu "Start a station from this song"); artist -> albums (Play from beginning, View album, Start a station from this album).
8. **T9 Podcasts:** when Spotify `currently_playing_type` is `episode`, show "Spotify is playing something else. Radio is paused." with a resume button; never show the episode as a station track. Backend PR first if the field is dropped.
9. **T10 Neptune FQDN:** extra stack only, add `neptune.tail647b75.ts.net` to `WEB_ALLOWED_HOSTS` (keep the IP) and point `VITE_API_BASE_URL` at the FQDN; restart only that web container.

## Out Of Scope

- PR #177, master, `/srv/juke-dev`, `/srv/juke-prod`, other Neptune stacks.
- Deploying backend changes to Neptune (send `NEED:` to the owner instead).
- Installing on the physical phone; entering owner credentials.

## Acceptance Criteria

- All nine items merged through the PR pipeline (reviewer verdict bound to head SHA), CI green on `integration/juke-app`.
- Every UI PR has side-by-side screenshots (macOS app and iOS simulator iPhone 18 Pro, iOS 27.0; T1+T2 also a small phone such as iPhone 17e with the keyboard up) and a "not verified on device" note. If a macOS screenshot is impossible, compare against the Round 3 reference and say so.
- Logic changes carry unit tests (layout calculations, state mapping, formatters).
- T10: `curl` shows the login page and API proxy answering under the FQDN; exact before/after of the two variables recorded (no secrets).

## Execution Notes

- Mode: ASYNC. The brief fully defines the work; proceed without waiting on clarification unless blocked.
- Split: juke-ios-port runs T1+T2, T5, T6, T3, T4; juke-implementor runs T10, T9, T7, T8. At most two implementors at once.
- Key files: `mobile/ios/jukeapp/`, `macos/juke/JukeMac/Views/`, `backend/` (playback state, T9 only).
- Commands: `scripts/build_and_run_ios.sh -p jukeapp -s "iPhone 18 Pro"`, `scripts/test_mobile.sh -p jukeapp --ios-only -s "iPhone 18 Pro" -o 27.0`.
- Risks: agents cannot judge feel or test on device; T9 may need a backend deploy; T10 must not exceed the two variables.

## Handoff

- Completed: task spec written. T10 applied on Neptune 2026-10-08 (extra stack only, `/srv/juke-extra/juke-app/docker-compose.juke-app.yml`, `juke-app-web` recreated with `up -d --no-deps`; backend untouched):
  - `WEB_ALLOWED_HOSTS`: `100.110.159.98,localhost` -> `neptune.tail647b75.ts.net,100.110.159.98,localhost`
  - `VITE_API_BASE_URL` (runtime env): `http://100.110.159.98:5373` -> `http://neptune.tail647b75.ts.net:5373`
  - Build args and `BACKEND_URL`/`PUBLIC_BACKEND_URL` left as the IP. Neptune compose file is untracked there; backup at `/tmp/juke-app-compose.before` on Neptune.
  - Verified: `http://neptune.tail647b75.ts.net:5373/` -> 200 and `/api/v1/radio/stations/` -> 401 (unauthenticated, proxy reaches backend); same results via the IP.
- Next: T10, T9, T7, T8 (juke-implementor); T1+T2, T5, T6, T3, T4 (juke-ios-port).
- Blockers: none.
