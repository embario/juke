import XCTest

/// Every failed Next says what happened: out of songs, a temporary failure, or offline.
/// The fixture radio fails every pick (`--uitesting-next-fails=`).
final class NextFeedbackUITests: XCTestCase {
    private func launch(_ failure: String, tab: String = "radio") -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["--uitesting", "--uitesting-authenticated", "--uitesting-tab=\(tab)", "--uitesting-next-fails=\(failure)"]
        app.launch()
        return app
    }

    private func message(_ app: XCUIApplication) -> XCUIElement { app.staticTexts["radio.issueMessage"] }

    @MainActor
    func testAnExhaustedStationAnswersEveryNextEvenAfterDismissal() {
        let app = launch("exhausted")
        let next = app.buttons["Next song"]
        XCTAssertTrue(next.waitForExistence(timeout: 15))
        XCTAssertFalse(message(app).exists)

        next.tap()
        XCTAssertTrue(message(app).waitForExistence(timeout: 5))
        XCTAssertTrue(message(app).label.contains("run out of new songs"), message(app).label)
        XCTAssertTrue(app.buttons["radio.issueNewStation"].exists)
        XCTAssertFalse(app.staticTexts["radio.issueTries"].exists, "one failure is a plain message")
        add(shot("Next-exhausted"))

        // The original bug: after dismissing, another Next said nothing.
        app.buttons["radio.dismissIssue"].tap()
        XCTAssertTrue(message(app).waitForNonExistence(timeout: 5))
        next.tap()
        XCTAssertTrue(message(app).waitForExistence(timeout: 5), "a second failed Next is answered again")
        XCTAssertEqual(app.staticTexts["radio.issueTries"].label, "Tried 2 times")

        // And with the banner still up, a third press is counted on the same banner, not stacked.
        next.tap()
        let tries = app.staticTexts["radio.issueTries"]
        XCTAssertTrue(tries.waitForExistence(timeout: 5))
        expectation(for: NSPredicate(format: "label == %@", "Tried 3 times"), evaluatedWith: tries)
        waitForExpectations(timeout: 5)
        XCTAssertEqual(app.staticTexts.matching(identifier: "radio.issueMessage").count, 1)
        add(shot("Next-exhausted-again"))
    }

    @MainActor
    func testATemporaryFailureReadsDifferentlyAndOffersTryAgain() {
        let app = launch("temporary")
        let next = app.buttons["Next song"]
        XCTAssertTrue(next.waitForExistence(timeout: 15))
        next.tap()
        XCTAssertTrue(message(app).waitForExistence(timeout: 5))
        XCTAssertTrue(message(app).label.contains("isn’t empty"), message(app).label)
        XCTAssertFalse(app.buttons["radio.issueNewStation"].exists)
        add(shot("Next-temporary"))

        app.buttons["radio.tryAgain"].tap()
        let tries = app.staticTexts["radio.issueTries"]
        XCTAssertTrue(tries.waitForExistence(timeout: 5), "Try again that fails is answered too")
        XCTAssertEqual(tries.label, "Tried 2 times")
    }

    @MainActor
    func testOfflineSaysSo() {
        let app = launch("offline")
        let next = app.buttons["Next song"]
        XCTAssertTrue(next.waitForExistence(timeout: 15))
        next.tap()
        XCTAssertTrue(message(app).waitForExistence(timeout: 5))
        XCTAssertTrue(message(app).label.contains("offline"), message(app).label)
        XCTAssertTrue(app.buttons["radio.tryAgain"].exists)
        add(shot("Next-offline"))
    }

    @MainActor
    func testTheCompactPlayerAnswersAFailedNextAwayFromRadio() {
        let app = launch("exhausted", tab: "library")
        let next = app.buttons["player.next"]
        XCTAssertTrue(next.waitForExistence(timeout: 15))
        let status = app.staticTexts["miniPlayer.status"]
        XCTAssertNotEqual(status.label, "No new songs on this station")
        next.tap()
        expectation(for: NSPredicate(format: "label == %@", "No new songs on this station"), evaluatedWith: status)
        waitForExpectations(timeout: 5)
        add(shot("Next-exhausted-mini-player"))
        // The line goes back to the artist by itself, and a new press brings it back.
        expectation(for: NSPredicate(format: "label != %@", "No new songs on this station"), evaluatedWith: status)
        waitForExpectations(timeout: 12)
        next.tap()
        expectation(for: NSPredicate(format: "label == %@", "No new songs on this station"), evaluatedWith: status)
        waitForExpectations(timeout: 5)
    }

    private func shot(_ name: String) -> XCTAttachment {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        return attachment
    }
}
