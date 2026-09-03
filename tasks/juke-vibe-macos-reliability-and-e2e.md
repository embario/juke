---
id: juke-vibe-macos-reliability-and-e2e
title: Harden Juke Vibe macOS interactions and add UI tests
status: done
priority: p1
owner: codex
area: clients
label: CLIENTS
complexity: 3
updated_at: 2026-09-03
---

## Goal

Make the Juke Vibe Mac client reliable and responsive across catalog search,
private chat, and Settings, with durable end-to-end coverage of its principal
user flows.

## Scope

- Correct the catalog authentication contract used by Neptune search.
- Lock encrypted-sync timestamp encoding to Neptune's numeric reference-date
  contract and replace repeated modal sync warnings with a quiet status treatment.
- Present the encryption explanation once after the first Juke login.
- Render an asynchronous Juke typing bubble while a reply is pending without
  blocking editing or the rest of the interface.
- Repair native Settings presentation.
- Add deterministic macOS UI-test seams and an XCUITest target covering signed
  out, chat, search, navigation, Now Playing, and Settings surfaces.
- Eliminate the chat composer's focus-driven SwiftUI layout loop and move
  Spotify/Apple Music polling off the main actor with background-aware cadence.
- Replace legacy per-binary Keychain ACL access with the signed app's stable,
  entitlement-scoped Data Protection Keychain access group.
- Make chat scrolling, reply feedback, and composer focus geometry feel native.
- Use Neptune's connected-provider playback contract for responsive Spotify
  state, transport controls, scrubbing, and double-click playback from search.
- Present richer catalog result metadata and artwork without conversation-only
  actions.
- Treat Juke authentication and provider playback authorization as separate
  capabilities, with a read-only spectator experience when Spotify playback is
  unavailable.
- Give transport controls a distinct, responsive row that never compresses song
  metadata, and visually separate the conversation from its composer.

## Out of Scope

- Changing Neptune's catalog or Vibe API contracts.
- Sending previous decrypted conversation to cloud AI.
- Redesigning the overall Vibe information architecture.
- Modifying the iPhone client in this pass.

## Acceptance Criteria

- Search authenticates successfully using the catalog endpoint's supported
  token scheme and reports actionable HTTP errors.
- Encrypted envelopes use the server's numeric Swift-reference timestamp contract.
- A sync outage does not produce a modal alert for every message.
- Chat immediately shows the submitted message and an animated typing bubble;
  the reply arrives asynchronously without blocking navigation or typing.
- The sidebar Settings control opens the native Settings scene.
- macOS unit and UI tests exercise every primary interactive surface and pass.
- The Debug application builds successfully.
- Repeated application focus changes remain responsive without runaway CPU or
  memory growth, and playback polling publishes only meaningful state changes.
- Spotify controls and search playback remain unavailable until Neptune verifies
  working provider credentials; catalog browsing and local observation continue.

## Execution Notes

- Execution mode: ITERATIVE.
- Primary paths: `macos/jukevibe/JukeVibeMac`, `JukeVibeMacTests`,
  `JukeVibeMacUITests`, and `macos/jukevibe/project.yml`.
- UI tests use explicit launch arguments and deterministic local fixtures; they
  must not depend on Neptune availability or mutate a real account.
- Preserve unrelated staged prompt/handbook work and the local Compose edit.

## Handoff

- Corrected catalog search from `Bearer` to DRF's required `Token` scheme and
  added differentiated authentication, service, and decode failures.
- Preserved the Vibe API's verified numeric Swift-reference timestamp contract
  and added unit coverage for both client/server network contracts.
- Replaced per-message modal encrypted-sync warnings with a quiet composer
  status, while presenting encryption education once per account after login.
- Chat now submits immediately, renders an animated typing bubble, and completes
  the reply on a retained cancellable task. Settings uses the native
  `SettingsLink` route.
- Added six deterministic XCUITest journeys covering signed-out account flows,
  asynchronous chat, search/navigation/Now Playing/Settings, and one-time privacy
  education.
- Neptune's public health endpoint returned HTTP 200 over the configured
  Tailscale TLS hostname.
- A live hang sample on 2026-09-02 captured the main thread continuously inside
  SwiftUI/AttributeGraph field-editor layout. The process reached 99% CPU and
  grew from 3.5 GB to 4.4 GB while the focus-sensitive expanding composer was
  active.
- Replaced the expanding `TextField` with a fixed-height `TextEditor`, clears
  focus as the scene becomes inactive, and restores it only after the scene is
  active. The app-lock timer now ignores duplicate inactive/background events.
- Moved Spotify and Apple Music Apple Events out of the app process onto a
  serialized utility worker, with a three-second process deadline and no
  overlapping reads. Player notifications now trigger immediate local reads;
  the fallback safety refresh backs off from 20 seconds during foreground
  playback to 120 seconds when inactive and idle. Position-only changes are
  deduplicated before they reach SwiftUI.
- Added unit coverage for publication identity and adaptive polling plus an
  XCUITest that cycles focus through Finder five times and then edits the chat
  composer. A manual 30-cycle stress run settled to 0% CPU at approximately
  120 MB RSS; the previous failure reached 99% CPU and more than 4 GB RSS.
- The Juke session and synced chat key now use the Data Protection Keychain and
  the shared signed-app access group. The chat vault caches its key for the
  active account and releases it on logout, avoiding one Keychain query per
  message. The prior legacy session item is intentionally not queried, so the
  user must sign in once after this migration.
- Added Neptune-backed Spotify state polling, artwork, device context, previous,
  play/pause, next, and seeking. Apple Music exposes the same controls through
  local Apple Events. Search cards now show richer metadata and album artwork,
  omit the former conversation action, and start Spotify playback on double-click.
- Chat pins itself to the newest response, uses only an animated three-dot reply
  indicator while a response is pending, and keeps placeholder and insertion
  geometry separate so focus does not displace the caret.
- The developer-signed Debug build, all 13 unit tests (including a signed Data
  Protection Keychain round trip and playback API contract coverage), and all
  six XCUITest journeys pass on an active Mac desktop.
- Follow-up interaction polish separates the transport row from song metadata,
  enlarges controls with hover/press feedback, strengthens the transcript-to-
  composer boundary, and replaces unavailable Spotify actions with an explicit
  spectator state across Now Playing and catalog search.
