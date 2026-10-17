# PR P: Library front-to-back crate spacing

- [iPhone 18 Pro, iOS 27.0](p-library-iphone-18-pro-ios-27.png): Songs, Artists, and Albums remain readable above the Library crate.
- [iPhone 17e, iOS 27.0, accessibility text](p-library-iphone-17e-accessibility-text-ios-27.png): all three selector labels remain visible at the largest accessibility text size.
- The screenshots were compared with [Round 3 reference](../b-round3-reference.png), rendered from `Round3.reference.html`. That reference shows the app's shared visual language; it does not depict the Library crate.
- `LibraryBrowsingTests.frontToBackLibraryCrateReservesSpaceAboveThePicker` verifies the crate's top-clearance calculation.
- **Not verified on device.** Both captures are from iOS simulators.
