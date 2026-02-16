---
id: cross-platform-notifications-reengagement
title: Build cross-platform notifications and re-engagement journeys
status: ready
priority: p2
owner: unassigned
area: platform
label: ALL/GENERAL
complexity: 4
updated_at: 2026-02-16
---

## Goal

Deliver a unified notification system (push, email, and optional in-app) to support retention and session re-engagement across Juke products.

## Scope

- Implement backend notification preference model and channel opt-in/opt-out APIs.
- Register and store APNs/FCM device tokens with user/session binding.
- Add event-triggered notifications for core journeys (session invites, onboarding completion nudges, weekly recap).
- Add retry, idempotency, and delivery status tracking for operational visibility.

## Out Of Scope

- Full marketing campaign UI.
- SMS channel rollout.
- Complex recommendation-personalized messaging copy engine.

## Acceptance Criteria

- Users can manage notification preferences through API-backed settings.
- iOS and Android clients can register tokens and receive test push notifications.
- Backend can send at least one production-relevant notification from an event trigger and one scheduled notification.
- Delivery outcomes are queryable for troubleshooting.

## Execution Notes

- Idea rank: `#8`
- Portfolio classification: `essential`
- Key files:
- `/Users/embario/Documents/juke/backend/juke_auth/models.py`
- `/Users/embario/Documents/juke/backend/juke_auth/views.py`
- `/Users/embario/Documents/juke/backend/catalog/tasks.py`
- `/Users/embario/Documents/juke/mobile/ios/juke/juke-iOS/**`
- `/Users/embario/Documents/juke/mobile/android/juke/app/src/main/java/fm/juke/mobile/**`
- Commands:
- `docker compose exec backend python manage.py test`
- `scripts/build_and_run_ios.sh -p juke`
- `scripts/build_and_run_android.sh -p juke`
- Risks:
- Token invalidation and stale device records can increase failed send volume.
- Regulatory/compliance requirements for notification consent vary by region.

## Handoff

- Completed:
- Task created from retention gap analysis across backend, web, and mobile.
- Next:
- Ship API/device registration first, then one event trigger per channel.
- Blockers:

