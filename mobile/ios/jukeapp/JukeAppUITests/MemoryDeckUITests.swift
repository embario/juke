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
        card.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.92)).tap()
        XCTAssertTrue(app.navigationBars.buttons.firstMatch.waitForExistence(timeout: 5))
        XCTAssertFalse(topCard(app).isHittable)
        add(shot("Memory-opened-from-card"))
    }

    @MainActor
    func testTappingTheCardImageOpensAndDismissesTheFullscreenViewer() {
        let app = launch(sample)
        let card = topCard(app)
        XCTAssertTrue(card.waitForExistence(timeout: 10))
        for _ in 0..<5 where !card.label.hasPrefix("Beach with the family") { app.buttons["memory.deck.next"].tap() }
        XCTAssertTrue(card.label.hasPrefix("Beach with the family"))

        card.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.36)).tap()
        let close = app.buttons["memory.imageViewer.close"]
        XCTAssertTrue(close.waitForExistence(timeout: 5))
        XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "memory.imageViewer.image").firstMatch.exists)
        add(shot("Memory-card-fullscreen-image"))
        close.tap()
        XCTAssertTrue(card.waitForExistence(timeout: 5), "closing the viewer returns to the deck")
    }

    @MainActor
    func testVideoOnTheCardOpensInTheFullscreenViewer() {
        let app = launch(sample)
        let card = topCard(app)
        XCTAssertTrue(card.waitForExistence(timeout: 10))
        for _ in 0..<5 where !card.label.hasPrefix("Sunday drive") { app.buttons["memory.deck.next"].tap() }
        XCTAssertTrue(card.label.hasPrefix("Sunday drive"))
        XCTAssertEqual(app.buttons["memory.card.image"].label, "View memory video")

        card.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.36)).tap()
        let close = app.buttons["memory.imageViewer.close"]
        XCTAssertTrue(close.waitForExistence(timeout: 5))
        XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "memory.imageViewer.video").firstMatch.exists)
        add(shot("Memory-card-fullscreen-video"))
        close.tap()
    }

    /// At accessibility text sizes the card grows and the page scrolls: the buttons (the alternative to the
    /// swipe and long-press gestures) must be reachable and clear of the player island.
    @MainActor
    func testControlsStayReachableAtLargeTextSizes() {
        for size in ["UICTContentSizeCategoryAccessibilityL", "UICTContentSizeCategoryAccessibilityXXXL"] {
            let app = launch(sample + ["-UIPreferredContentSizeCategoryName", size])
            let card = topCard(app)
            XCTAssertTrue(card.waitForExistence(timeout: 10), size)
            add(shot("Memories-deck-\(size.replacingOccurrences(of: "UICTContentSizeCategory", with: ""))-top"))

            let next = app.buttons["memory.deck.next"]
            for _ in 0..<8 where !next.isHittable {
                // Drag in the page margin, clear of the card (which takes sideways swipes) and of the player island.
                app.coordinate(withNormalizedOffset: CGVector(dx: 0.97, dy: 0.6)).press(forDuration: 0.05, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.97, dy: 0.1)))
            }
            XCTAssertTrue(next.isHittable, "\(size): the arrows are reachable by scrolling")
            let island = app.descendants(matching: .any).matching(identifier: "player.island").firstMatch
            for id in ["memory.deck.previous", "memory.deck.next", "memory.deck.shuffle", "memory.menu"] {
                let button = app.buttons[id]
                XCTAssertTrue(button.exists && button.isHittable, "\(size): \(id)")
                XCTAssertGreaterThanOrEqual(button.frame.height, 43.9)
                if island.exists { XCTAssertLessThanOrEqual(button.frame.maxY, island.frame.minY, "\(size): \(id) is not under the player island") }
            }
            XCTAssertTrue(app.staticTexts["memory.position"].isHittable, size)
            add(shot("Memories-deck-\(size.replacingOccurrences(of: "UICTContentSizeCategory", with: ""))-controls"))

            let first = app.staticTexts["memory.position"].label
            next.tap()
            XCTAssertNotEqual(app.staticTexts["memory.position"].label, first, "\(size): Next works")
            app.terminate()
        }
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
