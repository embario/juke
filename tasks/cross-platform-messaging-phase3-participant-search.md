---
id: cross-platform-messaging-phase3-participant-search
title: Messaging Phase 3 - participant search across inbox and composer surfaces
status: ready
priority: p2
owner: unassigned
area: platform
label: ALL/GENERAL
labels:
  - juke-task
  - messaging
  - search
  - web
  - ios
  - android
complexity: 3
updated_at: 2026-03-21
---

## Goal

Add participant-only search to help users find existing conversations and start new DMs without introducing full message-body search.

## Scope

- Search by participant identity only, not message body.
- Search/filter existing inbox conversations by participant display name or username.
- Search for users when starting a new DM from composer/search entry surfaces.
- Respect block/hide rules and privacy constraints in all search results.
- Support the same search behavior on web, Android, and iOS.

## Out Of Scope

- Full-text message search.
- Group-chat search.
- Search ranking driven by message content or semantic retrieval.
- Rich discovery recommendations beyond direct participant lookup.

## Acceptance Criteria

- Users can filter their inbox by participant identity on web, Android, and iOS.
- Users can search for a participant when creating a new DM.
- Blocked/hidden users never appear in participant search results.
- Search results are limited to participant fields such as username and display name; no message-body matches are returned.
- Existing deep-link and DM-creation flows continue to use the same conversation identity rules from phase 1.

## Execution Notes

- Prefer reusing existing people-search/profile-search infrastructure where it exists rather than creating a parallel messaging-only directory of users.
- Scope should stay narrow: quick participant lookup and inbox filtering, not a search platform project.
- Key files:
  - `/Users/embario/Documents/juke/backend/juke_auth/views.py`
  - `/Users/embario/Documents/juke/backend/settings/urls.py`
  - `/Users/embario/Documents/juke/web/src/features/messages/`
  - `/Users/embario/Documents/juke/mobile/android/juke/app/src/main/java/com/juke/juke/ui/`
  - `/Users/embario/Documents/juke/mobile/ios/juke/juke-iOS/`
- Commands:
  - `docker compose exec backend python manage.py test`
  - `docker compose exec web npm test`
  - `scripts/build_and_run_android.sh -p juke`
  - `scripts/build_and_run_ios.sh -p juke`
- Risks:
  - user-search duplication if messaging search ignores existing discovery/profile search APIs
  - privacy regressions if block filters are applied in UI only instead of at the backend query layer

## Handoff

- Completed:
  - Phase definition established for participant-only search.
- Next:
  - Confirm whether inbox filtering and new-message user lookup should share one backend endpoint or separate contracts.
- Blockers:
  - Depends on phase 1 conversation identity and block/hide rules being established first.
