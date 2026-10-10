import XCTest

final class MemoryDetailUITests: XCTestCase {
    @MainActor
    private func openBeachMemory(extra: [String] = []) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["--uitesting", "--uitesting-authenticated", "--uitesting-tab=memories", "--uitesting-memories-sample"] + extra
        app.launch()
        openBeachCard(in: app)
        return app
    }

    /// The deck opens on its first card each time it appears, so every visit steps to the Beach memory.
    @MainActor
    private func openBeachCard(in app: XCUIApplication) {
        let card = app.descendants(matching: .any).matching(identifier: "memory.card").firstMatch
        XCTAssertTrue(card.waitForExistence(timeout: 10))
        for _ in 0..<5 where !card.label.hasPrefix("Beach with the family") { app.buttons["memory.deck.next"].tap() }
        XCTAssertTrue(card.label.hasPrefix("Beach with the family"))
        card.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.92)).tap()
        XCTAssertTrue(app.buttons["memory.playMoment"].waitForExistence(timeout: 5))
    }

    @MainActor
    func testDetailShowsDescriptionPhotosTagsAndARingedPlayAtTheRightOfItsCapsule() {
        let app = openBeachMemory()
        XCTAssertTrue(app.staticTexts["memory.description"].exists)
        XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "memory.photo").firstMatch.waitForExistence(timeout: 5), "the photo renders")
        XCTAssertTrue(app.staticTexts["memory.media.summary"].label.contains("1 photo"))
        XCTAssertTrue(app.staticTexts["#summer"].exists && app.staticTexts["#family"].exists)
        add(shot("Memory-detail-top"))

        let capsule = app.descendants(matching: .any).matching(identifier: "memory.songCapsule").firstMatch
        let play = app.buttons["memory.playMoment"]
        XCTAssertTrue(capsule.exists)
        XCTAssertGreaterThanOrEqual(play.frame.width, 44)
        XCTAssertGreaterThanOrEqual(play.frame.height, 44)
        XCTAssertLessThanOrEqual(capsule.frame.maxX - play.frame.maxX, 20, "Play sits against the capsule's right edge")
        XCTAssertGreaterThan(play.frame.midX, capsule.frame.midX + capsule.frame.width * 0.3, "and not in the middle")
    }

    @MainActor
    func testTappingTheDetailImageOpensAndDismissesTheFullscreenViewer() {
        let app = openBeachMemory()
        let image = app.buttons["memory.detail.image"]
        XCTAssertTrue(image.waitForExistence(timeout: 5))
        image.tap()

        let close = app.buttons["memory.imageViewer.close"]
        XCTAssertTrue(close.waitForExistence(timeout: 5))
        XCTAssertTrue(app.descendants(matching: .any).matching(identifier: "memory.imageViewer.image").firstMatch.exists)
        add(shot("Memory-detail-fullscreen-image"))
        close.tap()
        XCTAssertTrue(image.waitForExistence(timeout: 5), "closing the viewer returns to the memory")

        let artwork = app.buttons["memory.song.artwork"]
        XCTAssertTrue(artwork.waitForExistence(timeout: 5))
        artwork.tap()
        let artworkViewerClose = app.buttons["memory.imageViewer.close"]
        XCTAssertTrue(artworkViewerClose.waitForExistence(timeout: 5), "song artwork also opens in the viewer")
        artworkViewerClose.tap()
    }

    @MainActor
    func testAtTheLargestTextSizePlayStaysReachableAndAtTheCapsuleEdge() {
        let app = openBeachMemory(extra: ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"])
        let play = app.buttons["memory.playMoment"]
        for _ in 0..<6 where !play.isHittable { app.swipeUp() }
        XCTAssertTrue(play.isHittable, "Play is reachable by scrolling")
        let capsule = app.descendants(matching: .any).matching(identifier: "memory.songCapsule").firstMatch
        XCTAssertLessThanOrEqual(capsule.frame.maxX - play.frame.maxX, 24)
        XCTAssertGreaterThanOrEqual(play.frame.height, 43.9)
        add(shot("Memory-detail-AccessibilityXXXL"))
    }

    @MainActor
    func testTheDescriptionCanBeEditedAndPersists() {
        let app = openBeachMemory()
        app.buttons["memory.description.edit"].tap()
        let field = app.textViews["memory.description.field"]
        XCTAssertTrue(field.waitForExistence(timeout: 5))
        for _ in 0..<4 where !field.isHittable { app.swipeUp() }
        let save = app.buttons["memory.description.save"]
        XCTAssertFalse(save.isEnabled, "nothing changed yet")
        field.tap()
        field.typeText(" We stayed for sunset.")
        XCTAssertTrue(save.isEnabled)
        add(shot("Memory-detail-editing-description"))
        save.tap()
        let text = app.staticTexts["memory.description"]
        XCTAssertTrue(text.waitForExistence(timeout: 5))
        XCTAssertTrue(text.label.contains("We stayed for sunset."), text.label)
        // Leaving and coming back shows the saved text.
        app.navigationBars.buttons.firstMatch.tap()
        openBeachCard(in: app)
        XCTAssertTrue(app.staticTexts["memory.description"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["memory.description"].label.contains("We stayed for sunset."))
    }

    @MainActor
    func testTagsCanBeAddedFromTheFieldAndFromSuggestions() {
        let app = openBeachMemory()
        let tagField = app.textFields["memory.tag.field"]
        for _ in 0..<6 where !tagField.isHittable { app.swipeUp() }
        tagField.tap()
        tagField.typeText("sunset\n")  // Return submits; the Add button can sit under the keyboard
        XCTAssertTrue(app.staticTexts["#sunset"].waitForExistence(timeout: 5))
        let suggestion = app.buttons["Add tag beach"]
        XCTAssertTrue(suggestion.exists, "classifier suggestions are one tap away")
        add(shot("Memory-detail-tags"))
        suggestion.tap()
        XCTAssertTrue(app.staticTexts["#beach"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["Add tag beach"].exists, "an adopted suggestion is no longer offered")
        app.buttons["Remove sunset"].tap()
        let gone = NSPredicate(format: "exists == false")
        expectation(for: gone, evaluatedWith: app.staticTexts["#sunset"])
        waitForExpectations(timeout: 5)
    }

    private func shot(_ name: String) -> XCTAttachment {
        let attachment = XCTAttachment(screenshot: XCUIApplication().screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        return attachment
    }
}
