# Juke for macOS

Juke is the Mac app for Juke radio, your Library crate, music Memories and
private Chat (formerly Juke Vibe). It plays radio through Spotify, follows
Apple Music or Spotify metadata, can use ShazamKit in the background, and keeps
chat encrypted.

## Local build

1. Install XcodeGen and run `xcodegen generate` in this directory after changing
   `project.yml` (or adding/removing files). Commit the regenerated project;
   never commit `xcuserdata`.
2. Open `JukeMac.xcodeproj`, select the `JukeMac` scheme and the paid Juke
   development team.

## Testing

```sh
bash scripts/test_macos.sh          # unit + integration suite (permission-free)
CI=1 bash scripts/test_macos.sh     # unsigned, like CI (skips the Keychain tests)
bash scripts/test_macos.sh --ui     # JukeMacUIAutomation scheme
```

UI-driving tests are isolated in `JukeMacUIAutomation`. They are opt-in because
macOS requires the person running them to grant the test runner Automation and
Accessibility access; Juke does not bypass those protections.

## Identity

| | |
| --- | --- |
| App / tests / UI tests | `com.juke.mac`, `com.juke.mac.tests`, `com.juke.mac.uitests` |
| Sign-in client | `juke-app-mac`, callback `juke-app://auth/callback` |
| Session token (Keychain) | service `com.juke.mac.authentication` |
| Keychain group | `com.juke.vibe.shared` (shared with Juke for iPhone) |
| Chat key (iCloud Keychain) | service `com.juke.vibe.shared.chat-vault`, AAD `juke-vibe-chat:v1:<id>` |

The Keychain group, chat-vault service and AAD label keep their Juke Vibe names
on purpose: the chat key syncs between the Mac and iPhone apps, and renaming any
of them would make encrypted chat stored on Juke unreadable. The App ID needs
ShazamKit and Keychain Sharing.

Upgrading from Juke Vibe: the new bundle ID gets a fresh sandbox container, so
people sign in once more and local state starts over (preferences, the local
SwiftData chat store, cached memory media). Memories and encrypted chat come
back from the backend after sign-in.

## Settings

Settings (Command-,) are stored in `UserDefaults` by `JukeSettings`:
appearance (Match system, Light, Dark), crate flip direction, album-art tint,
background recognition, and the backend URL (default
`https://neptune.tail647b75.ts.net`). Every client resolves the server through
`JukeServer`; changing it signs out, because a token belongs to its server.

## Code map

- `JukeMac/App`: `JukeApp` (scenes, menu commands: Command-1 to 4 switch
  sections), `AppModel` (session, `api`, `settings`, `artwork`, `section`),
  `JukeSection`.
- `JukeMac/Settings/JukeSettings.swift`: persisted preferences.
- `JukeMac/Design`: `JukeTheme` (prototype `palette(dark, base)` tokens with a
  WCAG AA guard), `RGB` (`mix`, contrast), `JukeMotion`, `JukeRadius`,
  `JukeMetrics`, `JukeFont`, and shared components (`JukeCard`, button styles,
  `VinylDisc`). Bricolage Grotesque is not bundled yet; the system rounded
  design stands in.
- `JukeMac/Services/ArtworkPalette.swift`: dominant album-art colour feeding the theme.
  A section can point it at its own artwork with `AppModel.artworkOverride`
  (Memories follows the current memory's song).
- `JukeMac/Services/BackgroundRecognition.swift`: background recognition. While
  Settings > Listening is on and Juke radio is not playing, a song that stays on
  for 30 s becomes `POST radio/events/ {event: "recognized", source:
  "metadata"|"shazam"}` (same track at most once per 30 min, 40 per hour).
  Spotify metadata carries the track ID; Apple Music and Shazam songs are
  resolved through catalog search and skipped unless title and artist match.
  It only reads `MusicDetectionController` and never starts audio capture;
  Radio sets `backgroundRecognition.isRadioPlaying`.
- `JukeMac/Services/API`: `JukeServer`, `JukeAPI` (typed requests, token auth,
  error mapping), `RadioModels.swift` (`Radio.Track`, `Radio.Station`, ...),
  `JukeAPI+Radio.swift` (every `/api/v1/radio/` endpoint).
- `JukeMac/Views/Shell`: root window, header, `SectionStage` transitions, mini player.
- `JukeMac/Views/Radio`, `Library`, `Memories`, `Chat`: one folder per section.
  Memories is one card per memory (`MemoryBrowser` holds the ‹ n of N ›
  state); Chat is one card with the song on top and the composer as a well.
- `JukeMac/Views/Settings`, `Views/Shared`.

## Music memories (macOS first)

After Juke sign-in, Memories is the starting screen. “New memory” opens an
inline scrapbook in the main window. There is no memory-name field: the story is
the only free-text input. Add the currently playing song, reuse songs from earlier
memories, keep an optional snippet, choose feeling/reusable tag chips, or put a
custom #tag in the story. People already attached to earlier memories can be
selected; the app does not invent new identities from photos.

Choose photos/videos from the in-app PhotoKit thumbnail grid or drag files onto
the composer (50 MiB each; 12 per memory; see Guided creation below). Selected
media uploads privately to Juke and
renders as small photo prints. Image EXIF and video capture metadata supply the
first known capture date; file creation/modification dates are never substituted.
Missing metadata defaults transparently to today. “Time travel” offers Today,
Yesterday and an inline day calendar without requiring a time. Explicit choices
survive subsequent imports. Removing media recalculates inferred date/place.

“Use Photos dates & places” optionally requests PhotoKit read access to enrich
only the selected assets. Denial leaves file drag-and-drop and manual dates
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
environment. The client uses the backend URL from Settings.

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
