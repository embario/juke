import XCTest

final class ArtistCatalogUITests: XCTestCase {
    @MainActor
    func testArtistCatalogFiltersAndPaginates() {
        let app = XCUIApplication()
        app.launchArguments = ["--uitesting", "--uitesting-authenticated", "--uitesting-tab=library", "--uitesting-kind=artist"]
        app.launch()

        XCTAssertTrue(app.navigationBars["Library"].waitForExistence(timeout: 10))
        sleep(2)
        add(shot("Library-artists"))
        XCTAssertTrue(app.staticTexts["Miles Davis"].firstMatch.waitForExistence(timeout: 10))
        app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.42)).tap()  // the focused crate card

        // Albums and EPs first; categories with nothing in them are not offered.
        let albums = app.buttons["artist.filter.albums"]
        XCTAssertTrue(albums.waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["artist.filter.eps"].waitForExistence(timeout: 5))
        XCTAssertLessThan(albums.frame.minX, app.buttons["artist.filter.eps"].frame.minX)
        XCTAssertTrue(app.buttons["artist.filter.appearances"].exists, "categories with releases are offered")
        XCTAssertFalse(app.buttons["artist.filter.live"].exists && app.buttons["artist.filter.live"].frame.minX < albums.frame.minX)
        add(shot("Artist-catalog-albums"))

        // 45 albums come 30 at a time: scrolling to the end loads the second page.
        XCTAssertFalse(app.staticTexts["Albums 1"].exists)
        // The artist header takes room and the mini player floats over the lower part of the list, so
        // drag within the list above the player instead of swiping from its centre.
        let from = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.75))
        let to = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.48))
        for _ in 0..<40 where !app.staticTexts["Albums 1"].exists { from.press(forDuration: 0.05, thenDragTo: to) }
        XCTAssertTrue(app.staticTexts["Albums 1"].waitForExistence(timeout: 5), "the last of 45 albums loaded")
        add(shot("Artist-catalog-end-of-albums"))

        app.buttons["artist.filter.eps"].tap()
        XCTAssertTrue(app.staticTexts["EPs 3"].waitForExistence(timeout: 5))
        add(shot("Artist-catalog-eps"))
        app.buttons["artist.filter.eps"].swipeLeft()  // the filter bar scrolls sideways
        app.buttons["artist.filter.appearances"].tap()
        XCTAssertTrue(app.staticTexts["Appears on 2"].waitForExistence(timeout: 5))
        add(shot("Artist-catalog-appears-on"))
    }

    private func shot(_ name: String) -> XCTAttachment {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        return attachment
    }
}
