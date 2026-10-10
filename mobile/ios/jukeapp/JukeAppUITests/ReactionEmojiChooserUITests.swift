import XCTest

final class ReactionEmojiChooserUITests: XCTestCase {
    @MainActor
    func testCompactChooserOpensOnTapAndHoldScrubSelectsAndPromotesEmoji() {
        let app = launchRadio()
        let chooser = app.buttons["radio.openEmojiChooser"]
        XCTAssertTrue(chooser.waitForExistence(timeout: 10))
        XCTAssertFalse(app.buttons["radio.chooser.emoji.🚗"].exists)
        attachScreenshot(of: app, named: "Compact-emoji-chooser-at-rest")

        chooser.tap()
        let target = app.buttons["radio.chooser.emoji.🎧"]
        XCTAssertTrue(target.waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["Emotions"].exists)
        XCTAssertTrue(app.staticTexts["Objects"].exists)
        attachScreenshot(of: app, named: "Compact-emoji-chooser-open")

        chooser.press(forDuration: 0.8, thenDragTo: target)

        let selectedRecent = app.buttons["radio.recentEmoji.🎧"]
        XCTAssertTrue(selectedRecent.waitForExistence(timeout: 5))
        XCTAssertEqual(selectedRecent.value as? String, "Selected")
        let recentButtons = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "radio.recentEmoji."))
        XCTAssertEqual(recentButtons.element(boundBy: 0).identifier, "radio.recentEmoji.🎧")

        selectedRecent.tap()
        XCTAssertEqual(app.buttons["radio.recentEmoji.🎧"].value as? String, "Not selected")
    }

    @MainActor
    func testHoldAndSlideCanSelectEmojiFromLastCatalogueGroup() {
        let app = launchRadio()
        let chooser = app.buttons["radio.openEmojiChooser"]
        XCTAssertTrue(chooser.waitForExistence(timeout: 10))

        chooser.press(forDuration: 0.7)

        let lastGroup = app.staticTexts["Nature & Materials"]
        let target = app.buttons["radio.chooser.emoji.💎"]
        XCTAssertTrue(lastGroup.waitForExistence(timeout: 5))
        XCTAssertTrue(target.waitForExistence(timeout: 5))
        XCTAssertTrue(target.isHittable, "the last catalogue group must be visible to the hold-slide gesture")
        attachScreenshot(of: app, named: "Compact-emoji-chooser-last-group-visible")

        chooser.press(forDuration: 0.8, thenDragTo: target)

        let selectedRecent = app.buttons["radio.recentEmoji.💎"]
        XCTAssertTrue(selectedRecent.waitForExistence(timeout: 5))
        XCTAssertEqual(selectedRecent.value as? String, "Selected")
        let recentButtons = app.buttons.matching(NSPredicate(format: "identifier BEGINSWITH %@", "radio.recentEmoji."))
        XCTAssertEqual(recentButtons.element(boundBy: 0).identifier, "radio.recentEmoji.💎")
    }

    @MainActor
    func testHoldingChooserOpensPaletteForTapOrVoiceOverChoice() {
        let app = launchRadio()
        let chooser = app.buttons["radio.openEmojiChooser"]
        XCTAssertTrue(chooser.waitForExistence(timeout: 10))
        XCTAssertFalse(app.buttons["radio.chooser.emoji.😌"].exists)

        chooser.press(forDuration: 0.6)

        XCTAssertTrue(app.buttons["radio.chooser.emoji.😌"].waitForExistence(timeout: 5))
        app.buttons["radio.closeEmojiChooser"].tap()
        XCTAssertFalse(app.buttons["radio.chooser.emoji.😌"].exists)
    }

    @MainActor
    func testWordReactionRemainsVisibleAndCanBeRemoved() {
        let app = launchRadio()
        app.buttons["radio.addReaction"].tap()
        let words = app.textFields["A few words"]
        XCTAssertTrue(words.waitForExistence(timeout: 5))
        words.tap()
        words.typeText("mellow")
        app.buttons["Add"].tap()

        let reaction = app.buttons["Remove reaction mellow"]
        XCTAssertTrue(reaction.waitForExistence(timeout: 5))
        attachScreenshot(of: app, named: "Compact-emoji-chooser-with-word-reaction")
        reaction.tap()
        XCTAssertTrue(reaction.waitForNonExistence(timeout: 5))
    }

    @MainActor
    private func launchRadio() -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = [
            "--uitesting",
            "--uitesting-authenticated",
            "--uitesting-tab=radio",
        ]
        app.launch()
        XCTAssertTrue(app.buttons["radio.openEmojiChooser"].waitForExistence(timeout: 10))
        return app
    }

    @MainActor
    private func attachScreenshot(of app: XCUIApplication, named name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
