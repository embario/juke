# PR K: Emoji slider

The iOS Radio reaction slider supports hold, scrub, enlarged preview, and release to choose. Tap and VoiceOver controls remain available. Selected “In your words” reactions stay visible as removable chips below the emoji slider; JukeMac continues to show word reactions in its reaction strip.

| Round 3 reference | iPhone 18 Pro, iOS 27.0 |
| --- | --- |
| ![Round 3 reference](../b-round3-reference.png) | ![Emoji slider](k-emoji-slider-iphone-18-pro-ios-27.png) |

- UI tests cover holding and releasing on one emoji, scrubbing to the neighboring emoji, and keeping/removing a word reaction.
- Unit tests cover recency ordering, slot mapping, VoiceOver adjustment, and account-scoped persistence. JukeMac tests cover visibility and removal of a word reaction from its strip.
- **Not verified on device.** Simulator comparison evidence: iPhone 18 Pro on iOS 27.0.
