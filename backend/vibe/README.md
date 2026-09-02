# Juke Vibe server boundary

This Django app provides the server contracts for Juke Vibe. Conversation text
is not a server-side plaintext model. Encrypted sync accepts only the client
envelope's opaque base64 ciphertext and metadata needed for reconciliation.

## Routes

- `POST /api/v1/auth/vibe/authorize`: authenticated web handoff for the
  allowlisted `juke-vibe-mac` client. Accepts S256 PKCE parameters and returns
  the custom-scheme callback URL.
- `POST /api/v1/auth/vibe/exchange`: exchanges a one-time, two-minute code for
  the existing Juke API token and the Vibe account/capability response.
- `POST /api/v1/vibe/opening-question`: accepts only recent track strings and
  current-track metadata. Unknown fields are rejected.
- `PUT /api/v1/vibe/encrypted-chat-records/<uuid>`: idempotent ciphertext upload,
  isolated to the authenticated account. Stale and same-time conflicting writes
  return `409`.
- `GET /api/v1/vibe/encrypted-chat-records?cursor=<sequence>`: bounded incremental
  change feed in the Swift `EncryptedVibeChangeSet` shape.
- `POST /api/v1/vibe/chat`: non-persistent chat, disabled unless the account's
  `VibeAccountCapability.cloud_ai_enabled` flag is explicitly set.
- `GET /api/v1/health`: public lightweight API reachability check.

Vibe routes accept both the existing Juke `Token` authorization scheme and the
Mac client's `Bearer` spelling. The underlying credential remains Juke's current
DRF per-user token.

## Operations

Apply `vibe.0001_initial` before enabling browser handoff. Cloud AI remains
off by default and can be changed by an administrator. Production also needs the
Tailscale FQDN on the HTTPS reverse proxy and in Django's allowed-host settings.
