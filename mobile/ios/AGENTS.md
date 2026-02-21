# iOS Agent Guide

## Location & Layout

```
mobile/ios/
├── juke/                        # Juke app target + tests
├── shotclock/                   # ShotClock app target + tests
├── tunetrivia/                  # TuneTrivia app target + tests
└── Packages/JukeKit/            # Shared Swift package used by all iOS apps
```

All iOS projects and shared packages live under `mobile/ios`.

## Naming Conventions (MANDATORY)

These naming rules apply to all iOS app targets (`juke`, `shotclock`, `tunetrivia`) and shared packages (`Packages/JukeKit`):

- Use `UpperCamelCase` for Swift types (`struct`, `class`, `enum`, `protocol`) and `lowerCamelCase` for properties, methods, and variables.
- Use `camelCase` model properties in Swift for API payloads (`inviteCode`, `tracksPerPlayer`) and rely on shared coding strategy for snake_case JSON from backend.
- Name files after the primary type (`HomeView.swift`, `SessionService.swift`, `JukeAPIClient.swift`). One primary type per file unless a small helper enum/extension is tightly coupled.
- Keep view models suffixed with `ViewModel`, services with `Service`, and stores/managers with `Store` or `Manager` consistently across all apps.
- Prefix cross-app shared types in `JukeKit` with `Juke` when ambiguity is possible (`JukeAPIClient`, `JukeSessionStore`, `JukeAuthService`).
- Keep app-specific namespaces clear:
  - `Juke*` for Juke app domain types.
  - `PowerHour*` / `ShotClock*` for ShotClock domain types.
  - `TuneTrivia*` for TuneTrivia domain types.
- Test files must mirror production type names with `Tests` suffix (`JukeDateParsingTests.swift`, `HomeViewModelTests.swift`); test methods follow `test<Behavior>_<ExpectedResult>()`.
- Avoid new hyphenated product/module names in code identifiers. Hyphens may remain in legacy Xcode target names, but Swift symbols and new modules should be alphanumeric `UpperCamelCase`.
- Use `UPPER_SNAKE_CASE` only for compile-time flags/env keys; use `lowerCamelCase` for Swift constants (`static let defaultTimeout`).

When introducing shared logic, prefer moving it into `Packages/JukeKit` with neutral, reusable naming instead of duplicating app-specific implementations.

## Toolchain

- Xcode 15+ recommended (script targets latest simulator OS).
- Swift Package Manager dependencies are embedded in the project; run `xcodebuild -resolvePackageDependencies` if needed.
- Bundle ID defaults to `embario.juke-iOS` (overridable via project settings).

## Build & Run

```bash
# Automated path (build + simulator boot + install + launch)
scripts/build_and_run_ios.sh -p <project>      # required: juke, shotclock, tunetrivia
scripts/build_and_run_ios.sh -p <project> -s "iPhone 17 Pro"   # optional simulator override

# Manual path
xed mobile/ios/juke/juke-iOS.xcodeproj          # opens Xcode
# Choose the `juke-iOS` scheme and any simulator/device, then ⌘R
```

The helper script:
1. Builds the selected project scheme (`juke-iOS`, `ShotClock`, or `TuneTrivia`) into `.derived-data` at repo root.
2. Resolves/boots the requested simulator via `xcrun simctl`.
3. Installs the Debug app bundle (`.app`).
4. Launches it using `xcrun simctl launch` and the bundle ID.

Per-run logs are written under `logs/` (for example `ios-build-<project>-<timestamp>.log` and `simulator-<project>-<device>-<timestamp>.log`).

## Troubleshooting Permissions (MANDATORY)

- When problems occur during testing or development, agents are authorized to inspect backend, web, and iOS/Android logs in their respective locations and Docker containers.
- No explicit virtualenv is required; agents must use Docker containers for troubleshooting and log inspection.

## Iterative Mobile Development Loop (MANDATORY)

- For each change, rebuild and rerun using the platform build script (`scripts/build_and_run_ios.sh -p <project>` or `scripts/build_and_run_android.sh -p <project>`).
- Capture the PIDs printed by the script (Android emulator PID + app PID; iOS app PID) and use them to scope log inspection.
- Review the per-run logs saved by the scripts before checking backend/web logs in Docker containers.

## Configuration Touchpoints

- API base URL: use an `xcconfig` file or `Info.plist` entry so it stays aligned with backend environments (set via `.env` for local Docker).
- OAuth redirects: coordinate with backend `SOCIAL_AUTH_SPOTIFY_*` + scheme/host in `Info.plist` (`URL Types`).
- Feature flags/settings: consolidate inside a shared Swift struct (e.g., `AppConfiguration.swift`) to keep parity with Android/web.

## Testing

- Unit tests: `juke-iOSTests` target (`⌘U` in Xcode or `xcodebuild test -scheme juke-iOS -destination "platform=iOS Simulator,name=iPhone 17 Pro"`).
- UI tests: `juke-iOSUITests` target; keep selectors resilient to design tweaks by referencing accessibility identifiers.
- Repo script: `scripts/test_mobile.sh -p <project> --ios-only` (required: `juke`, `shotclock`, or `tunetrivia`; defaults to iPhone 17 Pro / iOS 26.2; override with `-s <sim>` / `-o <os>`).

## Release Checklist for Agents

- Update app icons/splashes using assets generated by `scripts/export_brand_icons.sh` and commit inside `juke-iOS/Assets.xcassets`.
- Before shipping, archive via `xcodebuild -scheme juke-iOS -configuration Release -archivePath <path> archive` and export using the appropriate `.ipa` template.
- Sync version + build numbers across Info.plist, TestFlight, and the marketing site so analytics remain consistent.
