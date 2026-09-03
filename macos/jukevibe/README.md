# Juke Vibe for macOS

Juke Vibe is a chat-first music companion for Juke. It observes Apple Music or
Spotify player metadata without audio-capture permission, can explicitly use
ShazamKit with the microphone or system audio for other sources, and adapts its
visual atmosphere to the current track.

## Local build

1. Install XcodeGen and run `xcodegen generate` in this directory after changing
   `project.yml`.
2. Open `JukeVibeMac.xcodeproj` in Xcode.
3. Select the `JukeVibeMac` scheme and the paid Juke development team.

## Testing

The default `JukeVibeMac` scheme runs the permission-free unit and integration
suite. It does not launch or control other applications:

```sh
xcodebuild -project JukeVibeMac.xcodeproj \
  -scheme JukeVibeMac \
  -destination 'platform=macOS' test
```

UI-driving tests are intentionally isolated in the
`JukeVibeMacUIAutomation` scheme. They are opt-in because macOS requires the
person running them to grant Xcode or the invoking terminal Automation and
Accessibility access. Juke Vibe does not attempt to bypass those protections.
4. Run the Debug build.

The app signs in through `https://neptune.tail647b75.ts.net` and returns through
the `juke-vibe://auth/callback` URL scheme.

## Signing capabilities

The `com.juke.vibe.mac` App ID and provisioning profile require ShazamKit and
Keychain Sharing. The shared keychain group is `com.juke.vibe.shared`.

Chat is encrypted before local persistence or Neptune sync. The current private
beta shares its encryption key across the user's Apple devices through iCloud
Keychain; both devices must use the same Apple ID with Keychain sync enabled.
Account-level device linking and key recovery are a future hardening step.

## Platform behavior

- Apple Music and Spotify metadata are the default, quiet detection path.
- Around Me asks for microphone access only when selected.
- This Mac's Audio asks for Screen & System Audio Recording only when selected.
- The visual palette follows artwork and local audio presence while preserving
  layout, contrast, Reduce Motion, and Reduce Transparency behavior.
