# Android Agent Guide

## Location & Layout

```
mobile/android/juke
├── app/                 # Main Android application module (Kotlin, Compose/Views)
├── brand_assets/        # Shared iconography exported by scripts/render_icons.cjs
├── build.gradle.kts     # Root Gradle config (Kotlin DSL)
├── settings.gradle.kts  # Declares modules (currently just `:app`)
├── gradle/              # Wrapper + version catalogs
├── .gradle/, .kotlin/   # Build cache dirs (ignore)
└── gradlew(.bat)        # Wrapper entrypoints
```

Set `ANDROID_PROJECT_NAME` if you ever rename the folder (defaults to `juke`). App ID defaults to `fm.juke.mobile` (see `scripts/build_and_run_android.sh`).

## Toolchain

- Android Gradle Plugin via the wrapper (`./gradlew`).
- Minimum tooling per `scripts/build_and_run_android.sh`: `sdkmanager`, `avdmanager`, `emulator`, `adb`.
- Target emulator: API 36 Google APIs arm64 Pixel 7 profile by default.

## Build & Run

```bash
# From repo root
scripts/build_and_run_android.sh        # installs SDK components, creates/boots emulator, installs app

# Manual commands
cd mobile/android/juke
./gradlew :app:assembleDebug            # builds APK
./gradlew :app:installDebug             # installs onto attached emulator/device
adb shell monkey -p fm.juke.mobile 1    # launches the app
```

The helper script creates the AVD (`jukeApi36`), waits for boot, installs the debug build, then launches via `adb shell monkey`. Logs stream under `.android-emulator/` at the repo root.

## Troubleshooting Permissions (MANDATORY)

- When problems occur during testing or development, agents are authorized to inspect backend, web, and iOS/Android logs in their respective locations and Docker containers.
- No explicit virtualenv is required; agents must use Docker containers for troubleshooting and log inspection.
- All permissions for `adb` operations (including `logcat`) are granted when building and running Android apps.

## Iterative Mobile Development Loop (MANDATORY)

- For each change, rebuild and rerun using the platform build script (`scripts/build_and_run_ios.sh -p <project>` or `scripts/build_and_run_android.sh -p <project>`).
- Capture the PIDs printed by the script (Android emulator PID + app PID; iOS app PID) and use them to scope log inspection.
- Review the per-run logs saved by the scripts before checking backend/web logs in Docker containers.

## Networking & Config

- Android clients talk to the Django API; point them at your backend via build-time config (e.g., `local.properties` or buildConfig fields). Keep the value aligned with `BACKEND_URL` in `.env`.
- Authentication mirrors the backend: Spotify OAuth and token-based endpoints; keep redirect URIs consistent with the app id.

## Testing & QA

- Instrumented tests live under `app/src/androidTest`. Launch with `./gradlew :app:connectedDebugAndroidTest` while the emulator is running.
- Unit tests under `app/src/test` via `./gradlew testDebugUnitTest`.
- Repo script: `scripts/test_mobile.sh -p <project> --android-only` (required: `juke` or `shotclock`)

## Release Notes for Agents

- Build flavors are defined in the `app` module’s `build.gradle.kts` (check for `dev`, `staging`, `prod` if present).
- Assets are generated via `scripts/export_brand_icons.sh`; keep `brand_assets/` in sync before committing UI tweaks.
- Any new feature flags should integrate with shared Kotlin singletons inside `app/src/main/java/.../config` so they can map to backend toggles quickly.
