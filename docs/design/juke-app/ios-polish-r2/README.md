# Round 2 simulator evidence

## B — Chat Done and Send

Not verified on device. All Chat screenshots are XCTest attachments from the final code, using the DEBUG local-preview account without credentials or live chat requests.

| Capture | Verification |
| --- | --- |
| `b-chat-iPhone-18-Pro.png` / `b-comparison-iPhone-18-Pro.png` | iPhone 18 Pro, iOS 27.0, multiline draft and keyboard visible; normal-text UI case passed. |
| `b-chat-iPhone-17e.png` / `b-comparison-iPhone-17e.png` | iPhone 17e, iOS 27.0, multiline draft and keyboard visible; normal-text UI case passed. |
| `b-chat-iPhone-17e-large-text.png` / its comparison | iPhone 17e, accessibility XXXL text (`UICTContentSizeCategoryAccessibilityXXXL`); UI case passed. |

The UI cases verify both controls are hittable, at least 44 points wide/high, inside the screen, non-overlapping and above the keyboard. Done dismisses the keyboard without clearing the multiline draft; focusing the draft makes both controls available again. Visual inspection also verifies the fixed-size Send symbol stays inside its circle at XXXL text. Three composer unit tests cover blank/whitespace, nonblank/multiline and in-flight drafts.

`Round3.reference.html` has Radio, Memories and Browse, but no Chat screen or phone keyboard. Its Radio view provides the palette and rounded-surface reference. `b-round3-reference.png` is a static rendering of the HTML template and embedded `Component.renderVals()` with light-theme defaults; the repository does not contain the `support.js` runtime.

Local validation:
- Logic: `/tmp/juke-chat-unit.xcresult`, `/tmp/juke-chat-unit.log` (3 tests passed).
- Small phone: `/tmp/juke-chat-small-final.xcresult`, `/tmp/juke-chat-small-final.log` (2 UI tests passed).
- Pro: `/tmp/juke-chat-pro-final.xcresult`, `/tmp/juke-chat-pro-final.log` (1 UI test passed).
- Final script builds: `logs/ios-build-jukeapp-2D03DD7D-7F07-4887-8EF8-90FAC4A96700-20261008-182157.log` and `logs/ios-build-jukeapp-6A9957BE-0ED2-41D6-A5B5-FEC3022A7BF7-20261008-182639.log`.

Initial stalls were host memory pressure, diagnosed by the conductor. Verification resumed with one simulator and one build/test job at a time. Both used simulators (`2D03DD7D` and `6A9957BE`) were shut down after testing; the other worker's `170CE1B6` simulator was left untouched. No shared simulator service restart.
