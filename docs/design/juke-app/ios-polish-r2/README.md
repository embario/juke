# Round 2 simulator evidence

## B — Chat Done and Send (in progress)

Not verified on device. The preliminary iPhone 17e screenshot uses the DEBUG local-preview account, with no credentials or live chat requests. It shows the new Done row and empty-draft Send with the software keyboard visible, before the final explicit 44-point Done hit-area adjustment (the visible layout is unchanged).

`Round3.reference.html` includes Radio, Memories and Browse, but no Chat screen or phone keyboard. The reference snapshot is a static rendering of the HTML template and its embedded `Component.renderVals()` using light-theme defaults; the untracked `support.js` runtime is absent from the repository. Final side-by-side comparisons are pending.

The three composer logic tests passed. The added UI tests are intended to verify that Done and Send are hittable, have non-overlapping frames, and remain above the keyboard with multiline drafts and accessibility XXXL text. Done dismisses the keyboard and preserves the draft; focusing the draft makes both controls available again. **UI tests and final screenshots remain unverified:** simulator startup/installation and the test host stalled below app code in simulator `dyld` cache mapping.

Recovery handoff (2026-10-08):
- Dedicated Pro: `7AE170F3-FA62-4580-98F1-606F9242267E`; boot/install failed, then shutdown requested.
- Unused dedicated small phone: `064D2ADD-8490-428C-AB38-2191BCABB7A7` (Shutdown).
- Working small-phone baseline: `2D03DD7D-7F07-4887-8EF8-90FAC4A96700`; final build succeeded; fixture launch PID 10118, final script launch PID 13902, stalled test host PID 36457.
- Final successful build logs: `logs/ios-build-jukeapp-2D03DD7D-7F07-4887-8EF8-90FAC4A96700-20261008-175549.log` and `logs/ios-build-jukeapp-7AE170F3-FA62-4580-98F1-606F9242267E-20261008-180122.log`.
- Passing logic tests: `/tmp/juke-chat-unit.xcresult`, `/tmp/juke-chat-unit.log`.
- Interrupted UI runs: `/tmp/juke-chat-pro.log`, `/tmp/juke-chat-small.log`; simulator diagnosis: `/tmp/chat-small-host-sample.txt`, `/tmp/chat-simctl-install-sample.txt`.
- Coordinate simulator recovery with the conductor before restarting shared services; implementer-2 is using the existing Pro simulators.
