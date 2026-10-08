# Round 2 simulator evidence

## B — Chat Done and Send

Not verified on device. Screenshots use the DEBUG local-preview account, with no credentials or live chat requests.

- `b-chat-iPhone-18-Pro.png` and `b-comparison-iPhone-18-Pro.png`: final code, iPhone 18 Pro / iOS 27.0, software keyboard visible (empty draft, Send correctly disabled).
- `b-chat-iPhone-17e-preliminary.png` and its comparison: small-phone keyboard layout before the final explicit 44-point Done hit-area adjustment; the visible layout is unchanged. A final small-phone capture is pending.
- Multiline-draft, automated UI interaction and accessibility XXXL screenshots remain pending. The focused Pro UI test is running; the normal and large-text UI test cases are included in `ChatViewUITests.swift`.

`Round3.reference.html` has Radio, Memories and Browse, but no Chat screen or phone keyboard. Its Radio view provides the palette and rounded-surface reference. `b-round3-reference.png` is a static rendering of the HTML template and embedded `Component.renderVals()` with light-theme defaults; the untracked `support.js` runtime is absent from the repository.

Three composer logic tests passed: empty/whitespace drafts, nonblank/multiline drafts and the in-flight send guard. Final build script runs passed on iPhone 17e and iPhone 18 Pro. Initial simulator/test stalls were caused by host memory pressure (conductor diagnosis), rather than an app/runtime defect. After the conductor reduced booted simulators, Pro installation/launch and capture completed. Verification now uses one simulator at a time, shutting each down before booting another.

Local validation records:
- Passing logic tests: `/tmp/juke-chat-unit.xcresult`, `/tmp/juke-chat-unit.log`.
- Final small-phone build: `logs/ios-build-jukeapp-2D03DD7D-7F07-4887-8EF8-90FAC4A96700-20261008-175549.log`.
- Resumed Pro build: `logs/ios-build-jukeapp-6A9957BE-0ED2-41D6-A5B5-FEC3022A7BF7-20261008-180956.log`; fixture launch PID 72258.
- Resumed Pro UI test: `/tmp/juke-chat-pro-resumed.log`, `/tmp/juke-chat-pro-resumed.xcresult`.
