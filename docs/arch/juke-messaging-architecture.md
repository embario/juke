# Juke Messaging Architecture

## Executive Summary

This document designs a first-party messaging feature for Juke across the Django backend, web app, Android app, and iOS app. The feature supports:

- 1:1 direct messages
- Private group conversations
- Realtime inbox and thread updates
- Juke-native sharing of tracks inside messages

The design is intentionally phased. Phase 1 ships direct messages and the shared transport/foundation. Phase 2 extends the same model to group messaging, membership management, and richer inbox behavior. This avoids blocking the first release on the hardest moderation and group-state problems while still landing on one coherent architecture.

## Product Goals

- Let any authenticated Juke user privately message another user from profile and world surfaces.
- Let users create small private group chats for music discovery and social coordination.
- Make message delivery feel live without forcing clients into aggressive polling loops.
- Make music sharing feel native by embedding Juke track references directly in message payloads.
- Keep the backend contract consistent enough that web, Android, and iOS can converge on one inbox model.

## Non-Goals

- End-to-end encryption
- Public channels or community servers
- File uploads, images, voice notes, or video
- Message edit history or hard delete in v1
- Rich moderation console UI
- CLI parity in the initial rollout

## User Experience

### Primary User Journeys

1. Start a DM from a music profile or Juke World user card.
2. Open the inbox, read recent threads, and continue a conversation.
3. Create a group chat, name it, add members, and share tracks.
4. Receive a new message while already in the app and see the thread update immediately.
5. Leave the app, return later, and still see unread counts and last-message previews.

### Shared UX Decisions

- Inbox-first navigation: every client gets a dedicated `Messages` entry point.
- Conversation list sorted by latest activity.
- Unread count is tracked per participant, not globally per conversation.
- Composer supports plain text plus one optional track attachment in v1.
- Group chats support title, optional emoji/avatar later, and participant list.
- Direct-message creation is idempotent for a given unordered user pair.

### Web

- Add `Messages` to the sidebar and route it at `/messages`.
- Desktop uses a split view: conversation rail on the left, thread pane on the right.
- Mobile web collapses into stacked navigation: inbox list -> thread detail.
- Entry points:
  - profile page CTA: `Message`
  - Juke World user modal CTA: `Message`
  - global sidebar badge for unread count

### Android

- Add a `Messages` tab to `HomeScreen` bottom navigation alongside Profile and Catalog.
- Use a master-detail layout on large widths and a list/detail stack on phones.
- Add `Message` CTA on profile surfaces and user discovery surfaces.
- Use a bottom sheet track picker for the attach-track flow.

### iOS

- Replace the single signed-in landing view with a tab shell, keeping existing browse/profile flows intact.
- Add a `Messages` tab with inbox list and thread detail.
- iPhone uses `NavigationStack`; iPad can render a split inbox/thread view.
- Add `Message` CTA to profile and world user surfaces.

## Architecture Overview

## Core Decision

Messaging should be a dedicated backend app, `backend/messaging/`, backed by a shared websocket transport in `backend/realtime/`. Clients use REST for history and mutations, and websocket events for live delivery and unread refresh.

## Phase Strategy

### Phase 1

- Shared transport foundation in `backend/realtime/`
- `backend/messaging/` models and APIs for direct messages
- Web inbox/thread vertical slice
- Android and iOS inbox/thread vertical slices
- Track attachments

### Phase 2

- Group conversations and membership management
- Group metadata updates
- Conversation mute/archive
- Push notification hooks

### Phase 3

- Message search
- Attachments beyond tracks
- Thread settings and moderation/report flows

## Backend Design

### Django Apps

- `backend/realtime/`
  - ASGI router
  - token auth middleware
  - websocket consumer base helpers
  - Redis channel-layer integration
- `backend/messaging/`
  - models
  - serializers
  - REST views
  - websocket publishing helpers
  - tests

### Data Model

Use one model shape for both direct and group conversations.

#### `Conversation`

- `id`
- `kind` enum: `direct`, `group`
- `created_by` FK to `JukeUser`
- `title` nullable; required for `group`, null for `direct`
- `slug` optional future-friendly field for deep links
- `last_message` FK nullable
- `last_message_at`
- `created_at`
- `updated_at`
- `is_active`

#### `ConversationParticipant`

- `id`
- `conversation` FK
- `user` FK
- `role` enum: `owner`, `member`
- `joined_at`
- `left_at` nullable
- `last_read_message` FK nullable
- `last_read_at` nullable
- `is_muted`
- `is_archived`

Constraints:

- unique active membership per `(conversation, user)`
- direct conversations must have exactly two active participants
- a `direct` conversation is unique for an unordered pair of active participants

For direct uniqueness, store a normalized participant pair on `Conversation`:

- `direct_user_low` FK nullable
- `direct_user_high` FK nullable

Only populated when `kind = direct`, with a uniqueness constraint on the ordered pair.

#### `Message`

- `id`
- `conversation` FK
- `sender` FK
- `client_message_id` UUID for optimistic reconciliation
- `body` text, max 2000 chars
- `message_type` enum: `text`, `track_share`, `system`
- `status` enum: `active`, `removed`
- `created_at`
- `edited_at` nullable, unused in v1

#### `MessageAttachment`

- `id`
- `message` OneToOne FK
- `kind` enum: `track`
- `track` FK to `catalog.Track`
- `metadata` JSON for future generic payloads

#### `ConversationEvent`

Small append-only audit/event table for membership and system messages:

- `conversation`
- `actor`
- `event_type` enum: `group_created`, `participant_added`, `participant_left`, `title_updated`
- `payload` JSON
- `created_at`

This feeds generated `system` messages without forcing all lifecycle state into the main `Message` table.

### REST API

Mount under `/api/v1/messaging/`.

#### Conversations

- `GET /api/v1/messaging/conversations/`
  - paginated inbox
  - returns unread count, last message preview, participant summaries, and group metadata
- `POST /api/v1/messaging/direct-conversations/`
  - body: `target_user_id`
  - idempotent
- `POST /api/v1/messaging/group-conversations/`
  - body: `title`, `participant_ids`
- `GET /api/v1/messaging/conversations/<id>/`
  - detail view for bootstrapping a thread shell
- `PATCH /api/v1/messaging/conversations/<id>/`
  - group title, mute, archive

#### Messages

- `GET /api/v1/messaging/conversations/<id>/messages/`
  - paginated, newest-first at the API layer, reversed in clients for thread rendering
- `POST /api/v1/messaging/conversations/<id>/messages/`
  - body: `body`, `client_message_id`, optional `track_id`
- `POST /api/v1/messaging/conversations/<id>/read/`
  - body: `last_read_message_id`

#### Participants

- `POST /api/v1/messaging/conversations/<id>/participants/`
  - group only
  - owner/member can add depending on policy
- `DELETE /api/v1/messaging/conversations/<id>/participants/<user_id>/`
  - remove participant or self-leave

### Response Shape

All clients should share one canonical payload shape.

#### Conversation summary

- `id`
- `kind`
- `title`
- `participants`
- `unread_count`
- `last_message`
- `last_message_at`
- `is_muted`
- `is_archived`

#### Message payload

- `id`
- `client_message_id`
- `conversation_id`
- `sender`
- `body`
- `message_type`
- `attachment`
- `created_at`
- `status`

`attachment` for v1 expands track details inline:

- `kind`
- `track.id`
- `track.juke_id`
- `track.name`
- `track.artist_name`
- `track.album_name`
- `track.image_url`
- `track.preview_url`

### Realtime Transport

The current repo does not yet have Channels routing beyond plain Django ASGI, so messaging must ride on the same transport foundation already anticipated by:

- `tasks/cli-phase2-backend-websocket-transport.md`
- `tasks/realtime-world-and-session-events-platform.md`
- `tasks/backend-direct-messaging-foundation.md`

Messaging should consume that foundation rather than inventing a second realtime stack.

#### Websocket endpoint

- `/ws/v1/messaging/`

#### Subscription model

On connect, authenticate the user and join:

- `user_{user_id}` for inbox-wide events
- `conversation_{conversation_id}` for each active conversation

This supports both:

- low-cost inbox badge refresh events
- immediate thread append events for open conversations

#### Event types

- `conversation.upsert`
- `conversation.read`
- `message.created`
- `message.removed`
- `participant.joined`
- `participant.left`
- `conversation.archived`

#### Delivery rules

- Publish only after DB commit using `transaction.on_commit`.
- Use websocket events as incremental state, not the source of truth.
- Clients that miss events recover by re-fetching inbox/thread via REST.

### Unread State

Unread is derived from `ConversationParticipant.last_read_message`.

Rules:

- when a user sends a message, their own `last_read_message` advances to that message
- recipients do not advance until they explicitly mark read or open the thread and the client acknowledges the latest visible message
- unread count for a participant is messages after `last_read_message`, excluding their own sends

This gives one consistent model across web, Android, and iOS.

### Security, Abuse, and Policy

- Require authenticated membership for all conversation and message reads.
- Return `404` for non-member access to avoid leaking conversation existence.
- Rate limit message sends per user and per conversation.
- Cap group size at `32` participants in v1.
- Sanitize text and strip unsupported markup.
- Reserve hooks for block/report integration with future social controls.
- Keep server-side audit events for membership changes.

## Client Design

## Web App

### New module

- `web/src/features/messages/`
  - `api/messagingApi.ts`
  - `hooks/useInbox.ts`
  - `hooks/useConversationThread.ts`
  - `hooks/useMessagingSocket.ts`
  - `routes/MessagesRoute.tsx`
  - `components/ConversationList.tsx`
  - `components/ConversationThread.tsx`
  - `components/Composer.tsx`
  - `components/TrackAttachmentPill.tsx`

### Integration points

- Add `/messages` in `web/src/router.tsx`
- Add sidebar nav item and unread badge in `web/src/features/app/components/Sidebar.tsx`
- Add CTA buttons in:
  - `web/src/features/profiles/routes/MusicProfileRoute.tsx`
  - `web/src/features/world/components/UserDetailModal.tsx`

### State strategy

- REST fetch on route load
- websocket hook merges incremental updates into cached inbox/thread state
- optimistic send keyed by `client_message_id`
- reconnect falls back to full refetch of current thread and inbox

## Android

### Shared Android core

Add a new shared package in `mobile/Packages/JukeCore/src/main/java/fm/juke/core/messaging/`:

- DTOs
- domain models
- repository
- websocket client wrapper
- unread counter model

This avoids duplicating transport and payload parsing in future Android apps.

### Juke Android app

Add app-specific UI under `mobile/android/juke/app/src/main/java/com/juke/juke/ui/messages/`:

- `MessagesViewModel`
- `MessagesScreen`
- `ConversationListPane`
- `ConversationThreadPane`
- `ComposerBar`
- `CreateGroupSheet`

### Integration points

- register repository in `ServiceLocator`
- add `MESSAGES` tab to `HomeScreen`
- add `Message` actions in profile/world surfaces

### State strategy

- `StateFlow` for inbox and active thread
- optimistic sends with `client_message_id`
- websocket event collector updates local state on the main view model
- thread screen sends read acknowledgements when latest visible message changes

## iOS

### Shared JukeKit module

Add `mobile/ios/Packages/JukeKit/Sources/JukeKit/Messaging/`:

- `JukeMessagingModels.swift`
- `JukeMessagingService.swift`
- `JukeRealtimeClient.swift`
- `JukeInboxStore.swift`

This keeps networking and event parsing reusable across Juke, ShotClock, and TuneTrivia if messaging later expands there.

### Juke iOS app

Add app-specific views under `mobile/ios/juke/juke-iOS/Messages/`:

- `MessagesRootView.swift`
- `InboxListView.swift`
- `ConversationView.swift`
- `MessageComposerView.swift`
- `CreateGroupView.swift`

### Integration points

- replace the direct `SearchDashboardView` signed-in landing with a tab shell
- preserve onboarding and Juke World entry flow
- wire `Message` CTAs into profile/world surfaces

### State strategy

- `ObservableObject` inbox store from JukeKit
- async REST bootstrapping with websocket incremental updates
- optimistic send and reconcile via `client_message_id`

## Notifications and Deep Linking

Realtime in-app delivery is phase 1. Background delivery should integrate with the existing notifications backlog in phase 2.

### Deep links

- web: `/messages/<conversation_id>`
- iOS: `juke://messages/<conversation_id>`
- Android: app link / deep link to conversation detail

### Push hooks

On new message, emit a notification-domain event when:

- recipient is not actively viewing that conversation
- recipient has not muted the conversation
- notification preferences allow message alerts

Actual APNs/FCM delivery should stay aligned with `tasks/cross-platform-notifications-and-re-engagement.md`.

## Rollout Plan

### Slice 1: Backend + Web DM

- ship transport foundation
- ship direct conversations and track-share messages
- ship web inbox/thread experience

### Slice 2: Android + iOS DM

- add messages tab on both native apps
- support deep links, unread badges, and track shares

### Slice 3: Group Messaging

- group creation
- membership management
- system messages
- mute/archive

### Slice 4: Notification and Trust Hardening

- push notifications
- abuse controls
- moderation/report endpoints
- delivery metrics and operational dashboards

## Testing Strategy

### Backend

- model tests for direct uniqueness and group membership constraints
- API tests for access control, pagination, read state, and group membership updates
- websocket tests using `WebsocketCommunicator`
- transaction tests proving publish-on-commit behavior

### Web

- route tests for inbox and thread rendering
- reducer/hook tests for optimistic send and websocket merge
- component tests for unread badge and track attachment rendering

### Android

- repository tests with mocked API/socket sources
- view model tests for unread count and optimistic send reconciliation
- Compose tests for tab navigation, thread rendering, and read acknowledgements

### iOS

- JukeKit service/store tests
- view model/store tests for inbox and thread updates
- SwiftUI tests for tab shell and conversation rendering

## Operational Concerns

- Index `ConversationParticipant(conversation_id, user_id, left_at)`
- Index `Message(conversation_id, created_at)`
- Keep inbox queries denormalized around `last_message_at`
- Add structured logs for connect, disconnect, publish, and send failures
- Track metrics:
  - websocket connection count
  - message send latency
  - unread counter mismatches
  - reconnect frequency

## Open Questions

- Should group membership be owner-managed only in v1, or can any member invite?
- Should archived conversations still receive unread badges, or only a subtle inbox count?
- Should track attachments stay limited to one per message, or do we want multi-share batches later?

## Recommended Decision

Ship direct messages first, but implement them on the final shared conversation model described above. That keeps the first release tractable while avoiding a schema rewrite when group messaging lands.
