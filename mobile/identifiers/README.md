# Mobile Identifier Registry

This folder is the source of truth for deployment-critical identifiers used by iOS and Android apps.

## Structure

- Global keys: shared across all projects/platforms.
- Platform keys: iOS-only or Android-only keys.
- Project-local keys: values that vary for `juke`, `shotclock`, or `tunetrivia`.

## Environments

The registry tracks two environments:

- `development`
- `production`

Where possible, environment values reference env var names rather than literals.

## Canonical ID Convention

App deployment identifiers must follow:

- `com.juke.<project-name>`

Examples:

- `com.juke.juke`
- `com.juke.shotclock`
- `com.juke.tunetrivia`

## Notes

- Secrets are represented only as env var references.
- Internal code namespaces may temporarily differ from deployment identifiers and are tracked separately.
