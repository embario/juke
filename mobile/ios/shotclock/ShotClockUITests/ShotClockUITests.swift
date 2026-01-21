import XCTest

final class ShotClockUITests: XCTestCase {

    override func setUpWithError() throws {
        continueAfterFailure = false
    }

    func testAppLaunchesShowingAuthView() throws {
        let app = XCUIApplication()
        app.launch()

        // The auth view should show the app title
        XCTAssertTrue(app.staticTexts["ShotClock"].exists)
    }
}
