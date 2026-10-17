# Juke for iPhone

Juke (formerly Juke Vibe) is the mobile companion for conversational discovery,
Juke catalog browsing, and music-aware chat. It supports the current Apple Music
player, linked Spotify playback state through Juke, and explicit ShazamKit
recognition for music playing around the phone.

Not to be confused with `mobile/ios/juke` (`juke-iOS`, bundle `com.juke.juke`),
the older Juke client.

## Local build

1. Install XcodeGen and run `xcodegen generate` in this directory after changing
   `project.yml`.
2. Build and launch on a simulator with `scripts/build_and_run_ios.sh -p jukeapp`,
   or open `JukeApp.xcodeproj` in Xcode.
3. In Xcode, select the `JukeApp` scheme, the paid Juke development team, and an iPhone.
4. Run the Debug build, or archive with the included TestFlight configuration.
5. Unit tests: `scripts/test_mobile.sh -p jukeapp --ios-only`.

## Backend URL

The backend is resolved at launch from, in order: the `BACKEND_URL` launch
environment variable, the `BACKEND_URL` Info.plist key (filled from the
`BACKEND_URL` build setting; the build script loads it from `.env`), and finally
`https://neptune.tail647b75.ts.net`. The web sign-in page uses `FRONTEND_URL`
the same way and falls back to the backend URL.

Sign-in opens `<frontend>/accounts/login?client=juke-app-ios` and returns through
the `juke-app://auth/callback` URL scheme.

## Signing capabilities

The `com.juke.app` App ID and provisioning profile require ShazamKit and
Keychain Sharing. The shared keychain group is still `com.juke.vibe.shared`:
it holds the chat encryption key that syncs with the macOS app, so it keeps its
original name.

Chat is encrypted before local persistence or Neptune sync. The current private
beta shares its encryption key across the user's Apple devices through iCloud
Keychain; both devices must use the same Apple ID with Keychain sync enabled.
Account-level device linking and key recovery are a future hardening step.

## Migrating from Juke Vibe

The bundle ID changed from `com.juke.vibe` to `com.juke.app`, so Juke installs
as a new app. Sign in once more; chat history comes back from the backend.

## iOS boundary

iOS does not expose a universal queue or raw audio stream from arbitrary third-
party apps. Juke therefore uses Apple Music's local player metadata,
permission-based Spotify state through Juke, and a user-initiated microphone
recognition mode for other sources. Its artwork-derived colors and intensity
change the app's atmosphere without moving controls or disrupting readability.
