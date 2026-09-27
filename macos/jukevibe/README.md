# Juke Vibe for macOS

Juke Vibe is an authenticated music-memory companion for Juke. Save songs,
photos, videos, and stories, then explore your personal soundtrack over time.
It observes Apple Music or Spotify player metadata, can explicitly use ShazamKit
for other sources, and preserves the existing private chat experience.

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

## Music memories (macOS first)

After Juke sign-in, Memories is the starting screen. “New memory” opens an
inline scrapbook in the main window. There is no memory-name field: the story is
the only free-text input. Add the currently playing song, reuse songs from earlier
memories, keep an optional snippet, choose feeling/reusable tag chips, or put a
custom #tag in the story. People already attached to earlier memories can be
selected; the app does not invent new identities from photos.

Choose photos/videos in the embedded Apple Photos picker, drop files, or browse
files (50 MiB each; 12 per memory). Selected media uploads privately to Juke and
renders as small photo prints. Image EXIF and video capture metadata supply the
first known capture date; file creation/modification dates are never substituted.
Missing metadata defaults transparently to today. “Time travel” offers Today,
Yesterday and an inline day calendar without requiring a time. Explicit choices
survive subsequent imports. Removing media recalculates inferred date/place.

“Use Photos dates & places” optionally requests PhotoKit read access to enrich
only the selected assets. Denial leaves file/picker import and manual dates
available. Photo GPS is reverse-geocoded by Apple MapKit to a city/region, shown
as a removable chip, and included when the user reviews/saves. Missing location
stays blank. Apple's public PhotoKit asset API exposes creationDate and location,
but does not expose named People identities; no private APIs or Photos database
inspection are used. See [PHAsset metadata](https://developer.apple.com/documentation/photos/phasset)
and [PhotosPicker inline style](https://developer.apple.com/documentation/photosui/photospickerstyle/inline).

The chronological catalog supports search and connection filters. Photos and
videos are fetched with the Juke token and downloaded privately for rendering;
temporary media is removed on sign-out. User-selected file access is read-only.

Memories deliberately submitted to Juke are stored against the music profile;
they are separate from encrypted private chat. The Jev adapter is unconfigured
by default: creation works with an explicit unavailable status and user tags.
Configure the backend boundary described in `backend/vibe/MEMORIES.md` later.
Apply all Vibe migrations (through `0003_widen_normalized_memory_tag`) before using the new client in a shared
environment. The client continues to target the existing private Neptune URL.

Saved Spotify tracks support start/end segments through authorized Juke playback.
Music library tracks support local Apple Music controls with Automation access.
Apple catalog links open Music; precise segments require a library persistent ID.
Spotify end timing is best effort, with active song/device checks before pausing.
Playback errors and provider handoffs remain visible in the memory detail.

### Reproducible integration verification

Use a disposable account on an isolated backend. Store private credentials in a
mode-600 JSON file containing `baseURL`, `username`, and `password`, then run:

```sh
VIBE_TEST_CREDENTIALS=/path/to/private-test-credentials.json scripts/test_vibe_memories_live.sh
```

This compiles the production Swift client and verifies real login, Jev boundary,
photo/video upload, multi-song segments, persistence, chronological retrieval,
image/video decoding, tag edits/reuse, and profile connections. It deletes the
memory it creates; reusable test tags remain on the disposable account. Requires
Xcode command-line tools and ffmpeg. It does not control actual provider playback.

The UI scheme also includes fixture journeys and
`testLiveBackendAuthenticatedMemoryPersistsAndReusesTags`. Live UI testing is
opt-in via `/tmp/juke-vibe-live-ui-enabled` plus the private credentials file
`/tmp/juke-vibe-test-credentials.json` (also containing `accountID`). The DEBUG-only
launch seam accepts only a loopback backend and never stores its test token in the
Keychain. The Mac must be unlocked and UI automation authorized.

### Guided creation (September 17 revision)

Creation now progresses through Photo → Song → Story → Preview → Saved, with
one focused screen at a time. The main player is hidden during the journey.
Photo selection uses a custom PhotoKit thumbnail grid, not an embedded system
picker or file browser. Users explicitly request Photos access once; selected
assets persist while browsing years and moving backward. Only selected originals
are downloaded/uploaded, with a 50 MB streaming limit. Permission denial keeps
song/story-only creation and file drag-and-drop available. No permission is
automatically granted by the app or test workflow.

Date/place, tag and people adjustments are optional focused subpages of Preview.
Illustrations use native shapes and restrained looping motion; Reduce Motion
suppresses movement. Existing metadata precedence and backend payloads remain.
