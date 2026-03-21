---
id: cross-platform-messaging
title: Cross-platform messaging roadmap for direct messages
status: ready
priority: p1
owner: unassigned
area: platform
label: ALL/GENERAL
labels:
  - juke-task
  - messaging
  - realtime
  - web
  - ios
  - android
complexity: 5
updated_at: 2026-03-21
---

## Goal

Deliver a phased first-party direct-messaging system across Juke web, Android, and iOS with message requests, unread state, realtime thread updates, push notifications, and follow-on presence/search work.

## Scope

- Break messaging delivery into explicit execution phases with clear dependencies.
- Phase 1 covers DMs only: request-card intake after the first message, unread state, track-share attachments, deep links, push notifications, rate limiting, block-aware access, and admin visibility.
- Phase 2 adds typing indicators, online/offline presence with a privacy toggle, and broader system-event polish.
- Phase 3 adds participant-only search for inbox and composer surfaces.
- Keep one shared backend/API contract across web, Android, and iOS.

## Out Of Scope

- End-to-end encryption.
- File, image, voice, or video attachments.
- Group conversations for the current rollout.
- Full moderation console implementation beyond the minimum admin visibility required to inspect conversations/messages.
- CLI client support in the first rollout.
- Full-text message-body search.

## Acceptance Criteria

- Delivery is decomposed into phase tasks with no ambiguity about what ships in each slice.
- Phase 1, 2, and 3 tasks all preserve one shared conversation/message contract across web, Android, and iOS.
- The phased roadmap reflects the current product decisions: DMs only, 2000-char messages, one track per message, 10 messages per minute per conversation, latest-visible-message read semantics, push in v1, typing/presence later, participant search only.
- Architecture and implementation tasks call out that [docs/arch/juke-messaging-architecture.md](/Users/embario/Documents/juke/docs/arch/juke-messaging-architecture.md) still needs follow-up alignment because it currently includes group chat and older phase boundaries.

## Execution Notes

- Architecture doc: [docs/arch/juke-messaging-architecture.md](/Users/embario/Documents/juke/docs/arch/juke-messaging-architecture.md)
- Existing related tasks:
  - `tasks/backend-direct-messaging-foundation.md`
  - `tasks/realtime-world-and-session-events-platform.md`
  - `tasks/cross-platform-notifications-and-re-engagement.md`
- Phase tasks created from the confirmed product decisions:
  - `tasks/cross-platform-messaging-phase1-dm-requests-push-admin.md`
  - `tasks/cross-platform-messaging-phase2-typing-presence-and-system-events.md`
  - `tasks/cross-platform-messaging-phase3-participant-search.md`
- Recommended delivery order:
  - shared websocket transport and DM request foundation
  - web vertical slice
  - Android and iOS vertical slices
  - typing/presence and richer realtime polish
  - participant search
- Key files:
  - `/Users/embario/Documents/juke/backend/settings/asgi.py`
  - `/Users/embario/Documents/juke/backend/settings/urls.py`
  - `/Users/embario/Documents/juke/web/src/router.tsx`
  - `/Users/embario/Documents/juke/web/src/features/app/components/Sidebar.tsx`
  - `/Users/embario/Documents/juke/mobile/android/juke/app/src/main/java/com/juke/juke/ui/navigation/HomeScreen.kt`
  - `/Users/embario/Documents/juke/mobile/ios/juke/juke-iOS/ContentView.swift`
- Commands:
  - `docker compose exec backend python manage.py test`
  - `docker compose exec web npm test`
  - `scripts/build_and_run_android.sh -p juke`
  - `scripts/build_and_run_ios.sh -p juke`
- Risks:
  - websocket transport is not fully present in the repo yet and must be landed first or in parallel
  - unread count drift if optimistic state and read acknowledgements diverge
  - request-state, block-state, and push-state can drift if they are modeled in separate layers without a single canonical source of truth

## Handoff

- Completed:
  - Cross-platform messaging architecture draft exists.
  - Messaging execution is now split into three phase tasks aligned to the current product decisions.
- Next:
  - Update the architecture doc to remove group-chat assumptions and match the new DM-request flow.
  - Execute phase 1 first, then phase 2, then phase 3.
- Blockers:
  - Realtime transport foundation under `backend/realtime/` is not yet implemented in the current tree.
  - Minimal block/admin visibility model may need to land in parallel if no reusable social-control primitives exist yet.
