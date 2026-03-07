# Mobile Agent Guide

## Mobile Identifier Registry (Required)

The canonical source of truth for deployment identifiers is:
- `mobile/identifiers/registry.yaml`
- `mobile/identifiers/README.md`

All mobile app deployment identifiers must follow the canonical pattern:
- `com.juke.<project-name>`

Examples:
- `com.juke.juke`
- `com.juke.shotclock`
- `com.juke.tunetrivia`

Test and UI test bundles follow:
- `com.juke.<project-name>.tests`
- `com.juke.<project-name>.uitests`

When onboarding a new product project, update at least:
- `mobile/identifiers/registry.yaml` (add `projects.<name>` with `ios` + `android` keys and shared values)
- `scripts/build_and_run_ios.sh` and `scripts/build_and_run_android.sh` mappings (if the project is selectable by script)
- relevant app project files so they match registry values

Environment values should remain env-var-based where possible in the registry (`BACKEND_URL`, `FRONTEND_URL`, signing vars).

Useful check after edits:
```bash
rg -n "com.juke\\." mobile/ios mobile/android mobile/identifiers scripts
```

## What this task changed

- Introduced `mobile/identifiers/` and switched canonical IDs for Juke, ShotClock, and TuneTrivia to `com.juke.<project>`.
- Migrated Android package namespaces from `fm.<project>.mobile` to `com.juke.<project>`.
- Updated Android/iOS build scripts and docs to use canonical IDs.
- Updated Android Juke Spotify callback from web URL to app deep link (`juke://spotify-callback`) and added manifest handler.

## Subproject AGENTS

- `mobile/android/AGENTS.md`
- `mobile/ios/AGENTS.md`
