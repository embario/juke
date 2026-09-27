---
id: spotify-oauth-hydrator-quota-isolation
title: Protect Spotify account linking from bulk hydration quota exhaustion
status: done
priority: p0
owner: codex
area: backend
label: BACKEND
complexity: 3
updated_at: 2026-09-04
---

## Goal

Make Juke's Spotify account-linking flow reliable while the canonical identity hydrator is running, and make failures explicit and recoverable.

## Scope

- Prevent a browser session for another Juke user from overriding the app-selected account.
- Replace durable API tokens in browser query strings with short-lived, single-use connection tickets.
- Surface Spotify quota exhaustion distinctly during OAuth completion.
- Add a persistent, configurable request budget/cooldown for bulk Spotify hydration so interactive authentication and playback retain capacity.
- Make the systemd unit own a named Compose hydration service so stopping it cannot orphan a one-off worker.
- Deploy to Juke Dev and restart the existing systemd hydration unit.

## Out Of Scope

- Circumventing Spotify development-mode quota policy.
- Changing Spotify developer accounts or purchasing/requesting extended quota.
- Reworking catalog identity matching semantics.

## Acceptance Criteria

- A valid connection ticket always links the ticket's Juke user, regardless of an existing browser login, and cannot be replayed.
- Spotify `QUOTA_EXCEEDED` callbacks return a specific user-visible error instead of appearing successful.
- Bulk hydration honors a persistent rolling budget and Spotify-provided retry delay across process restarts.
- Backend and Juke Vibe tests cover the new handoff and quota behavior.
- Juke Dev is deployed without losing Neptune-only hydrator plumbing, and the systemd unit is active after restart.

## Execution Notes

- ITERATIVE: production-impacting OAuth/hydrator reliability fix requested after a live failure.
- Key files: `backend/juke_auth/`, `backend/mlcore/services/provider_hydration.py`, `backend/mlcore/management/commands/hydrate_spotify_from_isrc.py`, `macos/jukevibe/`.
- Risks: OAuth account confusion, token leakage, repeated systemd restarts, and quota starvation.

## Handoff

- Completed: Added single-use connection tickets, explicit quota errors, persistent/smoothed bulk hydration budgeting, and a named Compose worker managed by the user systemd unit. Deployed as Neptune revision `475e55a9c74ec6dcc3cd5e57b27dd5e132478f42`; live ticket/replay, HTTPS health, migration, seeding, pacing, and restart lifecycle checks passed.
- Next: Have the user retry Spotify linking from a freshly built Juke Vibe client.
- Blockers: None.
