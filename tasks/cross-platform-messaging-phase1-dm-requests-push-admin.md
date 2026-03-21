---
id: cross-platform-messaging-phase1-dm-requests
title: Messaging Phase 1 - DM requests, inbox/thread, push, and admin visibility
status: ready
priority: p1
owner: unassigned
area: platform
label: ALL/GENERAL
labels:
  - juke-task
  - messaging
  - realtime
  - notifications
  - web
  - ios
  - android
complexity: 5
updated_at: 2026-03-21
---

## Goal

Ship the first usable cross-platform Juke messaging release: direct messages only, with a message-request intake flow, inbox/thread UI across web/iOS/Android, track shares, unread state, push notifications, and minimum admin visibility.

## Scope

- Backend `messaging/` app and shared websocket transport for DM conversations only.
- Request-card conversation lifecycle:
  - sender starts a new conversation by sending the first message
  - receiver sees a request card after the first message
  - receiver can accept, ignore, or block
  - sender cannot send additional messages until the request is accepted
- Entry points on all supported clients:
  - profile
  - Juke World
  - search results
  - friend list
- Inbox/thread UI on web, Android, and iOS.
- Latest-visible-message read semantics and unread badges.
- One optional track attachment per message.
- Message body limit of 2000 characters.
- Rate limiting at no more than 10 messages per minute per conversation.
- Deep links to a specific conversation on web, Android, and iOS.
- Push notifications in v1 for new incoming requests and new messages in accepted conversations.
- Minimum admin visibility for conversation/message inspection.

## Out Of Scope

- Group conversations.
- File/image/audio/video attachments.
- End-to-end encryption.
- Full moderation console UX.
- Full-text message-body search.
- Rich presence and typing indicators beyond the minimum needed to support the initial thread UX.

## Acceptance Criteria

- A user can start a new DM from profile, Juke World, search results, and friend-list surfaces on web, Android, and iOS.
- A new conversation is represented to the recipient as a request card only after the first message is sent.
- Before acceptance, the sender cannot send more than the initial message into that conversation.
- The receiver can accept, ignore, or block the request; ignored requests do not reveal state back to the sender.
- Messages support plain text plus at most one track share attachment.
- The API rejects messages over 2000 characters and enforces a per-conversation limit of 10 messages per minute.
- Read state advances from the latest visible message, and unread badges disappear when a conversation is archived.
- Push notifications fire for eligible new requests and new messages, with deep links opening the target conversation on each client.
- Conversation access is restricted to participants, and blocked or non-member access returns `404`.
- Admins can inspect conversations and messages without relying on raw database access.

## Execution Notes

- This phase is the release-defining slice. The later phases should not block it.
- The existing architecture draft in [docs/arch/juke-messaging-architecture.md](/Users/embario/Documents/juke/docs/arch/juke-messaging-architecture.md) needs follow-up alignment because it still assumes group messaging and older phase boundaries.
- Recommended backend additions:
  - `Conversation`/`ConversationParticipant`/`Message` model set
  - explicit request status for conversations or memberships
  - request accept/ignore/block mutation endpoints
  - `transaction.on_commit` publish hooks for websocket and push fan-out
  - admin registrations or a minimal staff-only inspection API
- Recommended block behavior assumption unless superseded later:
  - if user `A` blocks user `B`, then `B` disappears from `A`'s search, profile, friend-list, world, messaging, presence, and deep-link surfaces
  - existing conversations become inaccessible through normal product flows
  - non-admin reads return `404`
- Key files:
  - `/Users/embario/Documents/juke/backend/settings/asgi.py`
  - `/Users/embario/Documents/juke/backend/settings/urls.py`
  - `/Users/embario/Documents/juke/backend/juke_auth/models.py`
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
  - request-state, read-state, and push-state divergence if the backend publishes before transaction commit or clients over-optimistically reconcile
  - block/hide behavior spans more than messaging and may require a shared social-control primitive rather than one-off filters
  - push-notification delivery may depend on incomplete cross-platform notification plumbing already tracked elsewhere

## Handoff

- Completed:
  - Product decisions confirmed for DM-only v1, request-card intake, message limits, rate limits, one-track attachments, latest-visible-message read semantics, and push notifications.
- Next:
  - Break this phase into backend, web, Android, and iOS implementation slices if parallel execution is needed.
  - Update the architecture doc to match the request-flow and block-model assumptions before implementation begins.
- Blockers:
  - `backend/realtime/` transport foundation is not fully present in the current tree.
  - Push delivery may require dependencies from `tasks/cross-platform-notifications-and-re-engagement.md`.
