import XCTest

/// The Library's recent resources: history first, newest on top, topped up with recommendations.
final class RecentLibraryUITests: XCTestCase {
    private func card(_ app: XCUIApplication, _ title: String) -> XCUIElement {
        app.buttons.matching(NSPredicate(format: "label CONTAINS %@", title)).firstMatch
    }

    @MainActor
    func testLibraryListsRecentArtistsNewestFirstThenRecommendations() {
        let app = XCUIApplication()
        app.launchArguments = ["--uitesting", "--uitesting-authenticated", "--uitesting-tab=library", "--uitesting-kind=artist", "--uitesting-recents"]
        app.launch()
        // The crate opens on the newest recent artist (the crate/grid choice is remembered between launches).
        if app.buttons["Show as crate"].waitForExistence(timeout: 15) { app.buttons["Show as crate"].tap() }
        XCTAssertTrue(app.staticTexts["John Coltrane"].waitForExistence(timeout: 15))
        add(shot("Library-recents-crate"))

        if app.buttons["Show as grid"].exists { app.buttons["Show as grid"].tap() }
        let coltrane = card(app, "John Coltrane"), miles = card(app, "Miles Davis"), mingus = card(app, "Charles Mingus")
        XCTAssertTrue(coltrane.waitForExistence(timeout: 5))
        XCTAssertTrue(miles.exists && mingus.exists)
        XCTAssertLessThan(coltrane.frame.minY, miles.frame.minY + 1, "newest first")
        XCTAssertTrue(card(app, "Record 2").exists, "a short history is topped up with recommendations")
        XCTAssertEqual(app.buttons.matching(NSPredicate(format: "label CONTAINS 'Miles Davis'")).count, 1, "no duplicates")
        add(shot("Library-recents-grid"))
    }

    @MainActor
    func testOpeningAResourceMovesItToTheFront() {
        let app = XCUIApplication()
        app.launchArguments = ["--uitesting", "--uitesting-authenticated", "--uitesting-tab=library", "--uitesting-kind=artist"]
        app.launch()
        // The crate/grid choice is remembered between launches; make sure it is the grid.
        XCTAssertTrue(app.buttons["Show as grid"].waitForExistence(timeout: 15) || app.buttons["Show as crate"].waitForExistence(timeout: 1))
        if app.buttons["Show as grid"].exists { app.buttons["Show as grid"].tap() }
        let record3 = card(app, "Record 3")
        XCTAssertTrue(record3.waitForExistence(timeout: 10))
        record3.tap()
        XCTAssertTrue(app.buttons["artist.reveal"].waitForExistence(timeout: 15))
        app.navigationBars.buttons.element(boundBy: 0).tap()
        let first = card(app, "Record 3")
        let second = card(app, "Miles Davis")
        XCTAssertTrue(second.waitForExistence(timeout: 10))
        XCTAssertLessThan(first.frame.minY, second.frame.minY + 1)
        XCTAssertLessThan(first.frame.minX, second.frame.minX, "Record 3 is now the first card")
    }

    private func shot(_ name: String) -> XCTAttachment {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name; attachment.lifetime = .keepAlways
        return attachment
    }
}
