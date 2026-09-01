# Juke Vibe for iPhone

Juke Vibe is the mobile companion for conversational discovery, Juke catalog
browsing, and music-aware chat. It supports the current Apple Music player,
linked Spotify playback state through Juke, and explicit ShazamKit recognition
for music playing around the phone.

## Local build

1. Install XcodeGen and run `xcodegen generate` in this directory after changing
   `project.yml`.
2. Open `JukeVibe.xcodeproj` in Xcode.
3. Select the `JukeVibe` scheme, the paid Juke development team, and an iPhone.
4. Run the Debug build, or archive with the included TestFlight configuration.

The app signs in through `https://neptune.tail647b75.ts.net` and returns through
the `juke-vibe://auth/callback` URL scheme.

## Signing capabilities

The `com.juke.vibe` App ID and provisioning profile require ShazamKit and
Keychain Sharing. The shared keychain group is `com.juke.vibe.shared`.

Chat is encrypted before local persistence or Neptune sync. The current private
beta shares its encryption key across the user's Apple devices through iCloud
Keychain; both devices must use the same Apple ID with Keychain sync enabled.
Account-level device linking and key recovery are a future hardening step.

## iOS boundary

iOS does not expose a universal queue or raw audio stream from arbitrary third-
party apps. Juke Vibe therefore uses Apple Music's local player metadata,
permission-based Spotify state through Juke, and a user-initiated microphone
recognition mode for other sources. Its artwork-derived colors and intensity
change the app's atmosphere without moving controls or disrupting readability.
