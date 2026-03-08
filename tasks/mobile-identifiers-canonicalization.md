---
id: mobile-identifiers-canonicalization
title: Codify mobile identifiers and canonical app IDs across iOS and Android
status: done
priority: p1
owner: codex
area: platform
label: ALL/GENERAL
complexity: 3
updated_at: 2026-02-21
---

## Goal

Create a single mobile identifier registry under `mobile/` that separates global vs platform/project-local identifiers, and align app deployment identifiers to the canonical format `com.juke.<project-name>` for `juke`, `shotclock`, and `tunetrivia`.

## Scope

- Define a structured identifier manifest under `mobile/` covering:
- Shared global keys (dev/prod environment references, auth/deep-link contracts, signing env var references).
- iOS-specific keys (bundle IDs, scheme, URL schemes, universal link hosts, signing reference keys).
- Android-specific keys (application IDs, namespace, launcher activity, deep-link contract, signing reference keys).
- Project-local values for `juke`, `shotclock`, and `tunetrivia`.
- Update iOS and Android project/app identifiers that are in-scope for canonicalization to `com.juke.<project-name>`.
- Update mobile build/run scripts to use canonical identifiers.
- Move Android Juke Spotify connect callback return target from web URL to app deep link.

## Out Of Scope

- Changing backend auth endpoint contracts beyond callback target parameters already consumed by mobile clients.
- Provisioning actual signing credentials/secrets (only env var references are documented).
- Large package/namespace refactors unrelated to deployment identifiers.

## Acceptance Criteria

- `mobile/identifiers/` exists with a documented registry format and values for all three projects.
- Registry clearly distinguishes global/shared keys from iOS-local, Android-local, and project-local keys.
- Registry includes development and production environment sections.
- iOS/Android deployment identifiers for each project follow `com.juke.<project-name>` where edited in this task.
- `scripts/build_and_run_ios.sh` and `scripts/build_and_run_android.sh` remain compatible with canonical identifiers.
- Android Juke Spotify connect uses an app deep-link callback target and corresponding manifest handler exists.
- Task index and handoff notes are updated.

## Execution Notes

- Key files:
- `/Users/embario/Documents/juke/mobile/identifiers/README.md`
- `/Users/embario/Documents/juke/mobile/identifiers/registry.yaml`
- `/Users/embario/Documents/juke/mobile/ios/juke/juke-iOS.xcodeproj/project.pbxproj`
- `/Users/embario/Documents/juke/mobile/ios/tunetrivia/TuneTrivia.xcodeproj/project.pbxproj`
- `/Users/embario/Documents/juke/mobile/android/juke/app/build.gradle.kts`
- `/Users/embario/Documents/juke/mobile/android/shotclock/app/build.gradle.kts`
- `/Users/embario/Documents/juke/mobile/android/tunetrivia/app/build.gradle.kts`
- `/Users/embario/Documents/juke/scripts/build_and_run_ios.sh`
- `/Users/embario/Documents/juke/mobile/android/juke/app/src/main/java/com/juke/juke/ui/onboarding/OnboardingScreen.kt`
- `/Users/embario/Documents/juke/mobile/android/juke/app/src/main/AndroidManifest.xml`
- `/Users/embario/Documents/juke/tasks/_index.md`
- Commands:
- `bash -n scripts/build_and_run_ios.sh scripts/build_and_run_android.sh scripts/test_mobile.sh`
- `rg -n "com.juke\." mobile/ios mobile/android scripts`
- Risks:
- Concurrent agents are actively editing backend and ShotClock files; avoid reverting or broad-touch edits.
- Existing local modifications in ShotClock iOS project files must remain untouched unless explicitly requested.

## Handoff

- Completed:
- Added task entry and index registration.
- Added `/Users/embario/Documents/juke/mobile/identifiers/README.md` and `/Users/embario/Documents/juke/mobile/identifiers/registry.yaml` with global/platform/project-local structure for `development` and `production`.
- Updated Android `applicationId` values to canonical IDs:
- `com.juke.juke`
- `com.juke.shotclock`
- `com.juke.tunetrivia`
- Updated iOS bundle IDs for Juke and TuneTrivia targets/tests/UI tests to canonical IDs.
- Updated `/Users/embario/Documents/juke/scripts/build_and_run_ios.sh` bundle ID mapping to canonical IDs.
- Moved Android Juke Spotify connect callback target to app deep link (`juke://spotify-callback`) and added Android manifest deep-link intent filter.
- Updated mobile docs (`AGENTS.md` + architecture docs) to reflect canonical IDs.
- Ran lightweight validation:
- `bash -n scripts/build_and_run_ios.sh scripts/build_and_run_android.sh scripts/test_mobile.sh`
- Identifier grep checks across modified files.
- Migrated Android source namespaces across all app modules from `fm.*.mobile` to `com.juke.*` (build `namespace`, Kotlin packages/imports, manifests, and Android docs/registry).
- Completed physical package-directory migration:
  - `mobile/android/juke/app/src/main/java/com/juke/juke` and `src/test/java/com/juke/juke`.
  - `mobile/android/shotclock/app/src/main/java/com/juke/shotclock`.
  - `mobile/android/tunetrivia/app/src/main/java/com/juke/tunetrivia` and `src/test/java/com/juke/tunetrivia`.
- Next:
- [x] 2026-03-07: Reconcile ShotClock iOS test/UI-test bundle IDs in `mobile/ios/shotclock/ShotClock.xcodeproj/project.pbxproj` to canonical values (`com.juke.shotclock.tests`, `com.juke.shotclock.uitests`).
- [x] 2026-03-07: Add ShotClock test and UI-test bundle IDs to `mobile/identifiers/registry.yaml` for source-of-truth parity with runtime project values.
- [x] 2026-03-07: Confirm scope decision to include Android package-namespace migration (`fm.*` → `com.juke.*`) as part of this task.

## Validation

- Ran compile validation after Android namespace migration using:
  - `BACKEND_URL=http://localhost ./gradlew --no-daemon :app:compileDebugKotlin`
- Result:
  - `mobile/android/juke/app`: success
  - `mobile/android/shotclock/app`: success (single deprecation warning in `HomeScreen.kt`)
  - `mobile/android/tunetrivia/app`: success

## Proposed next actions

1. Scope decision outcome:
   - Option A (not chosen): limit scope to deployment identifiers + registry/docs/test IDs only.
   - Option B (chosen): include Android package namespace migration in this task.

2. If Option B is approved:
   - Update `namespace` in all Android app modules:
     - [x] `mobile/android/juke/app/build.gradle.kts`
     - [x] `mobile/android/shotclock/app/build.gradle.kts`
     - [x] `mobile/android/tunetrivia/app/build.gradle.kts`
   - [x] Run a Kotlin package rename across sources and tests.
   - [x] Verify manifest/entry points and script hooks still resolve correctly.
   - [x] Update affected docs and `mobile/identifiers/registry.yaml` values.
   - [x] Update any references in CI/build scripts if needed.

3. After scope lock-in:
   - Sync task handoff and status with final action set.
- Blockers:
- None currently.
