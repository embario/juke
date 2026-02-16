---
id: social-graph-activity-foundation
title: Build social graph and follow/activity foundations
status: ready
priority: p2
owner: unassigned
area: platform
label: ALL/GENERAL
complexity: 5
updated_at: 2026-02-16
---

## Goal

Introduce a first-party social graph so users can follow other listeners and consume a basic activity feed.

## Scope

- Add backend follow relationship model and APIs (follow, unfollow, followers, following).
- Define activity event model and feed endpoint for user-visible events.
- Add basic privacy controls for profile visibility and feed inclusion.
- Add minimal web/mobile profile affordances for follow state and feed consumption.

## Out Of Scope

- Direct messaging.
- Group chat.
- Advanced recommendation ranking based on social graph signals.

## Acceptance Criteria

- Follow/unfollow APIs are implemented with auth and abuse protections.
- Feed endpoint returns paginated events with deterministic ordering.
- Web and mobile can display follow status and list followers/following.
- Backend tests cover relationship constraints, privacy filters, and feed pagination.

## Execution Notes

- Idea rank: `#10`
- Portfolio classification: `experimental`
- Key files:
- `/Users/embario/Documents/juke/backend/juke_auth/models.py`
- `/Users/embario/Documents/juke/backend/juke_auth/views.py`
- `/Users/embario/Documents/juke/backend/juke_auth/serializers.py`
- `/Users/embario/Documents/juke/web/src/features/profiles/**`
- `/Users/embario/Documents/juke/mobile/ios/juke/juke-iOS/**`
- `/Users/embario/Documents/juke/mobile/android/juke/app/src/main/java/fm/juke/mobile/**`
- Commands:
- `docker compose exec backend python manage.py test`
- `docker compose exec web npm test`
- `scripts/build_and_run_ios.sh -p juke`
- `scripts/build_and_run_android.sh -p juke`
- Risks:
- Social misuse/abuse controls will be needed early (block/report/rate limits).
- Feed query performance can degrade without indexing and denormalized read models.

## Handoff

- Completed:
- Task created to close the social-layer gap in current product architecture.
- Next:
- Design data model and API contract before implementing client UI.
- Blockers:

