---
id: backend-direct-messaging
title: Direct messaging foundation - messaging/ app + MessageConsumer
status: blocked
priority: p2
owner: unassigned
area: backend
label: BACKEND
labels:
  - juke-task
  - backend
  - realtime
  - social
complexity: 4
updated_at: 2026-03-06
---

## Goal

A new `backend/messaging/` Django app delivering 1:1 direct messages between
Juke users, with REST CRUD + a `MessageConsumer` riding on cli-phase2's
`realtime/` WebSocket transport for push delivery. First consumer is
cli-phase5; web/mobile follow.

## Scope

- Models: `Conversation` (two participant FKs to user, `unique_together` on the
  unordered pair — same lex-ordering trick as `mlcore`'s `ItemCoOccurrence`),
  `Message` (FK to conversation, sender FK, `body` text, `sent_at`, optional
  `track` FK to `catalog.Track` for shared-track attachments).
- Migration creating both tables.
- REST endpoints under `/api/v1/messages/`:
  - `GET conversations/` — list for `request.user`, with last-message preview
    + unread count.
  - `GET conversations/<pk>/messages/` — paginated thread, newest-last.
  - `POST conversations/<pk>/messages/` — send. Body + optional `track_id`.
  - `POST conversations/` — start a conversation with a target user (idempotent:
    returns existing conversation if the pair already exists).
  - `POST conversations/<pk>/read/` — mark read up to a message ID.
- Serializers with the track attachment expanded inline (track name, artist,
  `juke_id`, whatever a client needs to render a play button).
- `MessageConsumer(AsyncJsonWebsocketConsumer)` in `backend/realtime/consumers.py`
  (or `backend/messaging/consumers.py` importing from `realtime.middleware`).
  Group `messages_{user.id}`. On message create, publish
  `{"type": "message.received", "conversation_id": ..., "message": {...}}` to
  the recipient's group. Reuses cli-phase2's `TokenAuthMiddleware` verbatim.
- Route: `ws/v1/messages/` added to `realtime/routing.py`.
- Publisher hook in the message-create path, same `async_to_sync` pattern as
  `PlaybackService._publish`.

## Out Of Scope

- Group conversations (>2 participants). 1:1 only.
- Message edit/delete. Send-only.
- Read receipts visible to the sender. Unread counts are for the reader only.
- Typing indicators.
- Attachment types beyond track references. No images/files.
- Blocking/muting. Rides on `social-graph-and-follow-activity-foundation` later.
- End-to-end encryption.

## Acceptance Criteria

- Starting a conversation with the same target twice returns the same
  `Conversation` row (unordered-pair uniqueness).
- Sending a message via REST causes a WS frame to arrive on a
  `WebsocketCommunicator` connected as the recipient, with the serialized
  message body including the expanded track attachment.
- Thread pagination works: a conversation with 200 messages returns pages in
  chronological order with standard DRF pagination links.
- Unread count on `GET conversations/` increments when the other party sends,
  resets to 0 after `POST .../read/`.
- A user can only see conversations they participate in. `GET` on another
  user's conversation returns 404 (not 403 — don't leak existence).
- `docker compose exec backend python manage.py test` passes, including new
  `test_messaging_*.py` and existing `test_realtime_consumers.py`.

## Execution Notes

- Portfolio classification: `moderate-bet`. DMs are explicitly out-of-scope in
  `tasks/social-graph-and-follow-activity-foundation.md:26` — this is the
  sibling task that fills the gap.
- **Depends on cli-phase2** for `TokenAuthMiddleware` and the
  `ProtocolTypeRouter` wiring. This task only adds a consumer + a route, no
  transport work.
- The unordered-pair uniqueness: store `(user_a, user_b)` with `user_a.id <
  user_b.id` always. Enforce in `save()` or a manager method. `unique_together`
  on the ordered pair then gives unordered uniqueness.
- Key files:
  - `backend/messaging/{__init__,apps,models,serializers,views,urls}.py` (new)
  - `backend/messaging/migrations/0001_initial.py`
  - `backend/realtime/consumers.py` (add `MessageConsumer`) or
    `backend/messaging/consumers.py` (new — cleaner separation)
  - `backend/realtime/routing.py` (add `ws/v1/messages/` route)
  - `backend/settings/urls.py` (include `messaging.urls`)
  - `backend/settings/base.py` (add `messaging` to `INSTALLED_APPS`)
  - `backend/tests/unit/test_messaging_models.py`
  - `backend/tests/unit/test_messaging_views.py`
  - `backend/tests/unit/test_messaging_consumer.py`
- Commands:
  - `docker compose exec backend python manage.py makemigrations messaging`
  - `docker compose exec backend python manage.py migrate`
  - `docker compose exec backend python manage.py test`
- Risks:
  - The unordered-pair model makes "who is the other person in this
    conversation" a conditional (`user_b if request.user == user_a else user_a`).
    Put that in a model property, not repeated in every serializer/view.
  - Unread-count queries can get expensive at scale (N+1 on `GET conversations/`
    if each row counts messages). Annotate with `Count` + `Q(read=False)` in
    the queryset.
  - The publish-on-create hook can fire inside a transaction that later rolls
    back. Either publish post-commit (`transaction.on_commit`) or accept
    rare phantom pushes. Post-commit is correct.

## Handoff

- Completed:
- Next:
  - cli-phase5 consumes this. Web/mobile DM screens follow.
- Blockers:
  - `cli-phase2-backend-ws-transport` must be `done` (for `TokenAuthMiddleware`
    and the `ProtocolTypeRouter` setup this consumer plugs into).
