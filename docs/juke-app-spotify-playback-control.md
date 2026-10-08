# Juke app: Spotify playback control, pause/resume and device recovery

Written for iOS polish round 2, PR A (2026-10-08). It answers the owner's question: what
permission or setup does Juke need to control Spotify consistently from inside the app?

Short answer: nothing is missing in Apple signing or in the Spotify scopes Juke requests. The
limit is how Spotify works on an iPhone. Once iOS suspends the Spotify app, no remote command
can start it again; only bringing the Spotify app to the front does. Juke now keeps the paused
song and asks for that one step only when a play command really went unanswered.

## How Juke controls Spotify today

The Juke app does not play audio. It sends commands to the Juke backend, which calls the Spotify
Web API (`backend/catalog/services/playback.py`). The Spotify app on some device plays the music.

| Juke call | Spotify Web API call |
|---|---|
| `GET /api/v1/playback/state/` | `GET /me/player` |
| `POST /api/v1/playback/play/`, `pause/`, `next/`, `previous/`, `seek/` | the matching `/me/player/...` command |
| `POST /api/v1/radio/play/` | start or queue a song |

## What Spotify requires

| Requirement | State in Juke | Checked? |
|---|---|---|
| Spotify Premium on the listener's account. Spotify's reference says of the play command: "This API only works for users who have Spotify Premium." | Needed. | Not checked for the owner's account (agents do not read account data). Radio already played on the owner's phone, which would not work without it. |
| Scope `user-modify-playback-state` (play, pause, next, seek, queue). | Requested by default: `SOCIAL_AUTH_SPOTIFY_SCOPE` in `backend/settings/base.py`. | Default checked in code. The scopes actually granted to the owner's stored token were not checked. |
| Scope `user-read-playback-state` (state and devices), `user-read-currently-playing`. | Requested by default, same setting. | Same as above. |
| A Spotify device that is running. Without `device_id` a command goes to "the user's currently active device". | Juke remembers the device it last heard from and names it when it recovers playback. | Logic unit-tested. Not tested against Spotify. |
| Apple entitlement or capability. | None exists for this and none is needed. Opening `spotify://` needs no entitlement. | n/a |

If a Spotify account was linked to Juke before a scope was added, the account must be linked
again to grant it. Nothing suggests that is the case here.

## Why "open Spotify" appeared after a pause

Diagnosis from the code (no response from a real device was captured):

1. Spotify stops reporting a player that has been paused for a while: `GET /me/player` answers
   with no content. `RadioController.refresh` treated every empty answer as "no active device"
   and showed "Open Spotify on any device, then press play", although nothing was wrong yet.
2. The backend turns a Spotify 404 on a command ("no active device", "device not found") into
   an empty success. The app therefore could not tell a resume that worked from one that
   reached nobody, showed the song as playing, and then fell into case 1.

## What changed in PR A

- A paused song stays paused. An empty state while paused is not a problem and shows no message.
- While a song plays, one or two empty answers are ignored. Three in a row (about 6 seconds)
  count as a lost device; the song is kept, paused where Spotify was last heard from.
- Pressing play sends resume to the device radio was using. If Spotify reports no player with
  that song, Juke starts the same song at the same position on the last device it knew.
- A resume counts only once Spotify reports the song playing. If that does not happen within
  5 seconds, the song goes back to paused at its old position and Juke says "Juke can’t reach
  Spotify. Open Spotify, then press play."
- "Open Spotify" opens the Spotify app. When Juke is in front again it resumes the song by
  itself.
- The paused song (song, position, station) is saved, so it is still there after iOS ends Juke
  in the background. Pressing play then starts that exact song at that position.
- The compact player says "Paused", "Waiting for Spotify…" or "Open Spotify to keep playing".

## What is and is not verified

Verified by unit tests with a simulated Spotify (`macos/juke/JukeMacTests/RadioControllerTests.swift`,
the controller is shared by the Mac and iPhone apps), and by simulator screenshots with the
app's fixture player: every rule in the list above.

Not verified, because agents cannot play Spotify on a phone:

- That Spotify really returns an empty state after a pause on the owner's iPhone, and after how long.
- That naming the last device starts playback when the Spotify app is still running in the background.
- That after "Open Spotify" and returning to Juke the automatic resume starts the music. If the
  listener returns after iOS has suspended Spotify again, the same message comes back.
- How long iOS keeps a paused Spotify app alive. This decides how often the extra step is needed.

## Still open (not in PR A)

- **Backend reports unanswered commands.** The backend could return a distinct error (for
  example `playback_no_active_device`) instead of an empty success. The app would then know at
  once instead of waiting 5 seconds. It changes behaviour for the web app and other clients, so
  it belongs in its own backend PR.
- **Device list and transfer.** A backend endpoint over `GET /me/player/devices` would let Juke
  start on a Spotify app that is open but has not played yet on a phone Juke has never used
  (no remembered device). Today that case shows the "Open Spotify" message and needs one press
  of play in Spotify.

## Spotify App Remote (iOS SDK): not needed for this fix

App Remote would let Juke talk to the Spotify app on the same phone directly. It does not remove
the limit above. Spotify's own lifecycle guide says: "When the App Remote SDK wants to wake up
the Spotify client it must perform an app switch to do so", and recommends an "Open Spotify" or
"Resume Playback" button when the connection is gone. What it would add is a switch to Spotify
and back without the listener doing it by hand.

It would need the owner: registering the iOS app (bundle id `com.juke.app` and a redirect URI)
in the Spotify developer dashboard, then adding the SDK and a second authorization step. It is
out of scope for round 2 and was not started.

## Sources

- https://developer.spotify.com/documentation/web-api/reference/start-a-users-playback
- https://developer.spotify.com/documentation/web-api/reference/get-information-about-the-users-current-playback
- https://developer.spotify.com/documentation/ios/concepts/application-lifecycle
