# PR O: New Station wizard navigation

- Simulator capture: [iPhone 18 Pro, iOS 27.0](o-wizard-navigation-iphone-18-pro-ios-27.png)
- Round 3 visual reference: [Radio screen](../b-round3-reference.png)
- The Round 3 reference shows the app's shared visual language; it does not include the New Station wizard. The simulator capture shows the wizard after moving Back and Next/Skip into the top content row, with no `.bar` footer rectangle.
- `NewStationWizardTests.theChosenStepNeedsAPickButTheOtherStepNeverBlocks` covers the existing required-pick validation and optional-step behavior.
- **Not verified on device.** The screenshot was captured in the required iOS simulator.
