---
id: spotify-oauth-hydrator-quota-isolation
title: Protect Spotify account linking from bulk hydration quota exhaustion
status: in_progress
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

- Completed: Verified the live incident was caused by the bulk hydrator exhausting Spotify quota before OAuth `/v1/me` completed.
- Next: Preserve Neptune's unpublished service delta, implement/tests, deploy, restart, and verify.
- Blockers: None.
