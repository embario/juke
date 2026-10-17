import XCTest

/// Sliding the record into its sleeve pauses playback and offers actions. Fixture radio.
final class SleeveActionsUITests: XCTestCase {
    private func launch() -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["--uitesting", "--uitesting-authenticated", "-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryL"]
        app.launch()
        return app
    }

    private func shot(_ name: String) -> XCTAttachment {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        return attachment
    }

    private func putRecordAwayFromTheMenu(_ app: XCUIApplication) {
        // `radio.more` once the transport row is centred (PR X); before that the menu is just "More".
        let more = app.buttons.matching(NSPredicate(format: "identifier == 'radio.more' OR label == 'More'")).firstMatch
        XCTAssertTrue(more.waitForExistence(timeout: 15))
        more.tap()
        app.buttons["Put the record away"].tap()
    }

    /// The record going into its sleeve (by the slide, or by "Put the record away") pauses playback and
    /// shows the actions. A synthetic XCUI drag did not register on the record, so this drives the same
    /// `putAway()` through the menu; the slide itself is covered by `VinylSleeveTests` and was not exercised in UI tests.
    @MainActor
    func testPuttingTheRecordAwayPausesAndShowsTheActions() {
        let app = launch()
        XCTAssertFalse(app.otherElements["sleeve.sheet"].exists)
        putRecordAwayFromTheMenu(app)
        XCTAssertTrue(app.buttons["sleeve.newStation"].waitForExistence(timeout: 10), "the actions sheet opens")
        XCTAssertTrue(app.staticTexts["Paused"].exists)
        XCTAssertTrue(app.buttons["sleeve.browseAlbum"].isEnabled)
        XCTAssertFalse(app.buttons["sleeve.favorite"].isEnabled)
        XCTAssertFalse(app.buttons["sleeve.saveForLater"].isEnabled)
        add(shot("Sleeve-actions"))
    }

    @MainActor
    func testKeepingItPausedLeavesTheRecordInTheSleeve() {
        let app = launch()
        putRecordAwayFromTheMenu(app)
        XCTAssertTrue(app.buttons["sleeve.keepPaused"].waitForExistence(timeout: 10))
        app.buttons["sleeve.keepPaused"].tap()
        XCTAssertTrue(app.staticTexts["Record put away"].waitForExistence(timeout: 5), "still paused, record in the sleeve")
        XCTAssertTrue(app.buttons["Play again"].exists)
        XCTAssertFalse(app.buttons["sleeve.newStation"].exists)
    }

    @MainActor
    func testPlayAgainFromTheSheetBringsTheRecordBack() {
        let app = launch()
        putRecordAwayFromTheMenu(app)
        XCTAssertTrue(app.buttons["sleeve.playAgain"].waitForExistence(timeout: 10))
        app.buttons["sleeve.playAgain"].tap()
        XCTAssertTrue(app.staticTexts["Record put away"].waitForNonExistence(timeout: 10))
    }

    @MainActor
    func testBrowseTheAlbumOpensItAfterTheSheetCloses() {
        let app = launch()
        putRecordAwayFromTheMenu(app)
        XCTAssertTrue(app.buttons["sleeve.browseAlbum"].waitForExistence(timeout: 10))
        app.buttons["sleeve.browseAlbum"].tap()
        XCTAssertTrue(app.buttons["album.play"].waitForExistence(timeout: 10), "the album screen opens")
        XCTAssertFalse(app.buttons["sleeve.browseAlbum"].exists)
        add(shot("Sleeve-browse-album"))
    }

    @MainActor
    func testStartANewStationFromTheSong() {
        let app = launch()
        putRecordAwayFromTheMenu(app)
        XCTAssertTrue(app.buttons["sleeve.newStation"].waitForExistence(timeout: 10))
        app.buttons["sleeve.newStation"].tap()
        XCTAssertTrue(app.buttons["sleeve.newStation"].waitForNonExistence(timeout: 10), "the sheet closes")
        XCTAssertTrue(app.staticTexts["Record put away"].waitForNonExistence(timeout: 15), "the new station is on air")
    }
}
