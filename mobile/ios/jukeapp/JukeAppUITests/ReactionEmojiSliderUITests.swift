import XCTest

final class ReactionEmojiSliderUITests: XCTestCase {
    @MainActor
    func testHoldingAndReleasingOnOneEmojiSelectsIt() {
        let app = launchRadio()
        let emoji = app.buttons["React with 🥹"]
        XCTAssertTrue(emoji.waitForExistence(timeout: 10))
        XCTAssertEqual(emoji.value as? String, "Not selected")

        emoji.press(forDuration: 0.8)

        XCTAssertEqual(app.buttons["React with 🥹"].value as? String, "Selected")
        XCTAssertTrue(app.buttons["React with 🥹"].isHittable)
    }

    @MainActor
    func testScrubbingToTheNeighborSelectsOnlyTheReleasedEmoji() {
        let app = launchRadio()
        let startingEmoji = app.buttons["React with 😌"]
        let releasedEmoji = app.buttons["React with ☀️"]
        XCTAssertTrue(startingEmoji.waitForExistence(timeout: 10))
        XCTAssertTrue(releasedEmoji.exists)
        XCTAssertEqual(startingEmoji.value as? String, "Not selected")
        XCTAssertEqual(releasedEmoji.value as? String, "Not selected")

        startingEmoji.press(forDuration: 0.8, thenDragTo: releasedEmoji)

        XCTAssertEqual(app.buttons["React with ☀️"].value as? String, "Selected")
        XCTAssertEqual(app.buttons["React with 😌"].value as? String, "Not selected")
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
        attachScreenshot(of: app, named: "Reaction-slider-with-word-reaction")
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
        XCTAssertTrue(app.buttons["React with 😌"].waitForExistence(timeout: 10))
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
