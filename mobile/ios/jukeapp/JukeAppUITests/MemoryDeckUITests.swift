import XCTest

final class MemoryDeckUITests: XCTestCase {
    private let sample = ["--uitesting", "--uitesting-authenticated", "--uitesting-tab=memories", "--uitesting-memories-sample"]

    @MainActor
    private func launch(_ arguments: [String]) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = arguments
        app.launch()
        return app
    }

    private func topCard(_ app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any).matching(identifier: "memory.card").firstMatch
    }

    @MainActor
    func testDeckShowsOneCardAtATimeAndStepsThroughAll() {
        let app = launch(sample)
        let card = topCard(app)
        XCTAssertTrue(card.waitForExistence(timeout: 10))
        XCTAssertEqual(app.staticTexts["memory.position"].label, "1 of 4")
        XCTAssertTrue(card.isHittable)
        add(shot("Memories-deck"))

        var seen = [card.label]
        for expected in ["2 of 4", "3 of 4", "4 of 4"] {
            app.buttons["memory.deck.next"].tap()
            XCTAssertEqual(app.staticTexts["memory.position"].label, expected)
            seen.append(topCard(app).label)
        }
        XCTAssertEqual(Set(seen).count, 4, "every memory is dealt once per lap")
        app.buttons["memory.deck.next"].tap()
        XCTAssertEqual(app.staticTexts["memory.position"].label, "1 of 4")
        XCTAssertEqual(topCard(app).label, seen[0], "a full lap comes back to the first card")
        app.buttons["memory.deck.previous"].tap()
        XCTAssertEqual(app.staticTexts["memory.position"].label, "4 of 4")
    }

    @MainActor
    func testSwipingTheTopCardAwayShowsTheNextOne() {
        let app = launch(sample)
        let card = topCard(app)
        XCTAssertTrue(card.waitForExistence(timeout: 10))
        let first = card.label
        card.swipeLeft()
        let moved = NSPredicate(format: "label != %@", first)
        expectation(for: moved, evaluatedWith: topCard(app))
        waitForExpectations(timeout: 5)
        XCTAssertEqual(app.staticTexts["memory.position"].label, "2 of 4")
        add(shot("Memories-deck-after-swipe"))
    }

    @MainActor
    func testShuffleDealsADifferentTopCard() {
        let app = launch(sample)
        let card = topCard(app)
        XCTAssertTrue(card.waitForExistence(timeout: 10))
        let first = card.label
        app.buttons["memory.deck.shuffle"].tap()
        let moved = NSPredicate(format: "label != %@", first)
        expectation(for: moved, evaluatedWith: topCard(app))
        waitForExpectations(timeout: 5)
        XCTAssertEqual(app.staticTexts["memory.position"].label, "1 of 4")
    }

    @MainActor
    func testTappingTheTopCardOpensTheMemory() {
        let app = launch(sample)
        let card = topCard(app)
        XCTAssertTrue(card.waitForExistence(timeout: 10))
        card.tap()
        XCTAssertTrue(app.navigationBars.buttons.firstMatch.waitForExistence(timeout: 5))
        XCTAssertFalse(topCard(app).isHittable)
        add(shot("Memory-opened-from-card"))
    }

    @MainActor
    func testWithoutMemoriesTheDeckGivesWayToAnInvitation() {
        let app = launch(["--uitesting", "--uitesting-authenticated", "--uitesting-tab=memories"])
        XCTAssertTrue(app.staticTexts["No memories yet"].waitForExistence(timeout: 10))
        XCTAssertTrue(app.buttons["memory.empty.new"].exists)
        XCTAssertFalse(topCard(app).exists)
        add(shot("Memories-empty"))
    }

    private func shot(_ name: String) -> XCTAttachment {
        let attachment = XCTAttachment(screenshot: XCUIApplication().screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        return attachment
    }
}
