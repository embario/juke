---
id: juke-vibe-apple-clients
title: Build Juke Vibe for macOS and iOS
status: done
priority: p1
owner: codex
area: clients
label: CLIENTS
complexity: 5
updated_at: 2026-09-01
---

## Goal

Deliver a chat-first Juke Vibe app for macOS and iOS that listens alongside
the user, identifies music through platform-permitted integrations, supports
catalog browsing and discovery, and accumulates an encrypted private history of
musical conversations.

## Scope

- Add a separate SwiftUI iOS app under `mobile/ios/jukevibe` and a macOS app
  under `macos/jukevibe`.
- Center both clients on conversational music discovery, Now Playing context,
  catalog browsing, recommendations, and detailed track/album/artist views.
- Derive an adaptive visual atmosphere from current artwork, playback state,
  and locally available audio intensity, with smooth cross-track transitions.
- Support Apple Music Now Playing, permission-based Spotify playback state, and
  explicit short-lived ShazamKit microphone recognition for other sources.
- Encrypt chat history locally and sync only ciphertext between a user's
  devices; treat decrypted chat as sensitive PII.
- Use chat history locally to generate thoughtful questions and identify musical
  influences, connections, likes, and dislikes.
- Preserve an explicit consent boundary before decrypted chat is submitted for
  cloud AI processing.
- Add Juke Vibe backend routes for authentication handoff,
  ciphertext sync, permission-gated chat, questions, discovery, and track
  context.
- Register identifiers and provide private TestFlight build/export assets.

## Out Of Scope

- Timelines, listening journals, journal entries, reflection records, or diary
  metaphors in this product.
- Circumventing iOS sandboxing to capture arbitrary app audio or metadata.
- Public Tailscale Funnel exposure, Android, spoken chat, or public App Store
  distribution.
- Deleting or modifying Neptune's existing Journal backend, which remains
  available for separate future Juke journaling features.

## Acceptance Criteria

- Neither client exposes journal, entry, reflection, or timeline interfaces.
- Chat, discovery, catalog, and Now Playing experiences remain readable at
  Dynamic Type sizes and compact iPhone widths.
- Dynamic color and intensity preserve accessible contrast, avoid flashing,
  and respect Reduce Motion and Reduce Transparency.
- Chat history is encrypted before persistence or sync; raw personal text is
  not included in background telemetry or automatic cloud prompts.
- Apple Music and microphone adapters are implemented behind clear privacy
  controls; Spotify integration degrades gracefully until connected.
- Juke login reaches the private Neptune HTTPS endpoint using PKCE.
- Focused backend, web, macOS, and iOS tests pass.
- No secrets, generated build products, or user-specific Xcode state are
  committed.
- The feature branch is pushed and a pull request is opened.

## Execution Notes

- Execution mode: ITERATIVE.
- Key paths: `backend/vibe`, `mobile/ios/jukevibe`, `macos/jukevibe`,
  `mobile/identifiers/registry.yaml`, and mobile scripts.
- Risks: iOS background execution limits, provider SDK policy/credentials,
  ShazamKit provisioning, E2EE key transfer, and cloud-AI consent semantics.

## Handoff

- Completed: Juke Vibe backend, web authentication bridge, macOS client, iPhone
  client, private encrypted chat sync, music-aware visual atmosphere, platform
  music detection adapters, identifier registration, and build assets.
- Verified: 12 backend API tests; migration drift check; backend lint; focused
  web tests, lint, and production build; two macOS unit tests; iPhone simulator
  build/launch and one iOS unit test.
- Privacy boundary: local chat is encrypted before persistence or sync; cloud AI
  receives only the message the user submits and current track context, never an
  automatic transcript of prior chat.
- Platform boundary: iOS uses Apple Music state, linked Spotify state, and
  explicit ShazamKit microphone recognition because the OS does not expose a
  universal third-party Now Playing queue or raw cross-app audio.
- Provisioning note: both App IDs require ShazamKit and Keychain Sharing. The
  private beta's cross-device key transfer requires the same Apple ID with
  iCloud Keychain enabled; account-level key recovery is future hardening.
- Blockers: none for review. Device signing still depends on the Apple Developer
  portal capabilities and private TestFlight profiles.
