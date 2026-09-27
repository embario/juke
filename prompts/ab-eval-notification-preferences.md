# Notification Preferences and Device Tokens

Ecosystem goal: Give Juke a consent-aware notification foundation for session invites, messaging, onboarding nudges, and re-engagement.

Evaluation focus: Tests consent modeling, idempotency, provider-agnostic design, and whether the model resists integrating real push services.

Review the repository handbook, task board, backend guidance, and existing auth/profile implementation patterns. Promote this idea into an `ITERATIVE` task for a backend-only notification foundation: user preferences, device-token registration, idempotent token updates, and delivery-status records with mocked sends. Keep live push providers, client integration, and marketing journeys out of the first slice.
