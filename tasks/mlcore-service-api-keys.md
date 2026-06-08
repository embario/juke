---
id: mlcore-service-api-keys
title: Add service API keys for shared MLCore endpoints
status: ready
priority: p2
owner: unassigned
area: platform
label: BACKEND/ML
labels:
  - juke-task
  - mlcore
  - backend
  - security
complexity: 3
updated_at: 2026-06-07
---

## Goal

Add a lightweight service-auth layer for shared MLCore endpoints once the
private-tailnet-only isolation boundary is working.

The first isolation release may be unauthenticated on the private tailnet, but
the API design should be ready to require per-backend service keys before
public HTTPS exposure or broader multi-stack use.

## Scope

- Define service-client records for Juke backend stacks that call Neptune MLCore.
- Require an API key or bearer token on MLCore identity-resolution and
  recommendation endpoints.
- Attribute requests by service client in logs and metrics.
- Support key rotation and revocation.
- Add simple per-client rate-limit hooks or placeholders.
- Document deployment/env var setup for local backend clients and Neptune.

## Out Of Scope

- End-user authentication.
- OAuth/OIDC service mesh integration.
- Public internet exposure by itself; this task only adds auth primitives.

## Acceptance Criteria

- MLCore endpoints reject missing/invalid service credentials when auth is enabled.
- Known backend service clients can call identity resolution and recommendation endpoints.
- Logs/metrics include a low-cardinality service client label.
- Keys can be rotated without schema or code changes.
- Private-tailnet deployments can keep auth disabled through explicit config.
- Tests cover success, missing key, invalid key, disabled-auth mode, and key rotation.

## Execution Notes

- Key files:
  - `backend/recommender_engine/app/main.py`
  - `backend/recommender/services/client.py`
  - `template.env`
  - deployment docs / runbook
- Prefer hashed stored keys, not plaintext secrets.
- Keep the auth check small and framework-native for FastAPI.
- Avoid tying service keys to local Juke database IDs.

## Handoff

- Completed: task created from MLCore isolation-boundary planning.
- Next: implement after private-tailnet identity/recommendation contracts settle.
- Blockers: final endpoint shapes for shared MLCore APIs.
