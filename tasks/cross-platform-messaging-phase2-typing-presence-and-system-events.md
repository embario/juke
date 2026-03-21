---
id: cross-platform-messaging-phase2-typing-presence
title: Messaging Phase 2 - typing indicators, presence, privacy, and event polish
status: ready
priority: p1
owner: unassigned
area: platform
label: ALL/GENERAL
labels:
  - juke-task
  - messaging
  - realtime
  - presence
  - web
  - ios
  - android
complexity: 4
updated_at: 2026-03-21
---

## Goal

Add richer realtime behavior to messaging with typing indicators, online/offline presence, a privacy toggle, and polished system-event rendering on all supported clients.

## Scope

- Typing indicators for accepted DM conversations only.
- Presence model with online/offline state.
- User privacy toggle controlling whether presence is exposed to other users.
- Realtime propagation of typing and presence updates across web, Android, and iOS.
- System-message/event rendering polish for DM lifecycle events already introduced or planned in phase 1.
- Client and backend handling for stale indicator expiration.

## Out Of Scope

- Group presence or typing behavior.
- Last-active timestamps, detailed presence states, or device-specific presence.
- Message-body search.
- New attachment types.
- Public activity feeds.

## Acceptance Criteria

- Typing indicators do not appear immediately; they begin only after roughly 1-2 seconds of active typing.
- Typing indicators expire after roughly 2-3 seconds of inactivity without requiring a hard refresh.
- Typing indicators are shown only in accepted conversations and are never exposed across a block boundary.
- Presence is limited to `online` or `offline`.
- Users can disable presence visibility via a privacy toggle, and other clients honor that preference consistently.
- Presence state is reflected across web, Android, and iOS without leaking hidden/block-restricted users.
- System messages for request/accept/block lifecycle events render consistently and do not crowd out user-authored messages.

## Execution Notes

- Keep typing state ephemeral and websocket-driven. Do not persist per-keystroke events as durable messages.
- Favor TTL-based typing and presence expiry on the backend or client cache rather than requiring explicit "stop typing" reliability.
- If phase 1 lands minimal system messages for request flow, this phase should normalize the payload and rendering contract across all three clients.
- Key files:
  - `/Users/embario/Documents/juke/backend/settings/asgi.py`
  - `/Users/embario/Documents/juke/web/src/features/messages/`
  - `/Users/embario/Documents/juke/mobile/android/juke/app/src/main/java/com/juke/juke/ui/`
  - `/Users/embario/Documents/juke/mobile/ios/juke/juke-iOS/`
- Commands:
  - `docker compose exec backend python manage.py test`
  - `docker compose exec web npm test`
  - `scripts/build_and_run_android.sh -p juke`
  - `scripts/build_and_run_ios.sh -p juke`
- Risks:
  - typing and presence can generate noisy fan-out traffic if not rate-limited and coalesced
  - privacy-toggle bugs can leak hidden presence state unless filtering is enforced server-side
  - event expiry behavior can diverge across clients if timers are not standardized

## Handoff

- Completed:
  - Phase definition established for richer realtime UX after the core DM release.
- Next:
  - Finalize canonical typing and presence event payloads before implementation.
  - Decide whether the privacy toggle belongs in profile settings, messaging settings, or both.
- Blockers:
  - Depends on phase 1 transport and conversation lifecycle landing first.
