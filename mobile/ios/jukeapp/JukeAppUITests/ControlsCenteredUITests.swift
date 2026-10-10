import XCTest

/// Previous / Play-Pause / Next stay centred in the viewport, whatever sits beside them.
final class ControlsCenteredUITests: XCTestCase {
    private func launch(_ extra: [String] = [], largeText: Bool = false) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["--uitesting", "--uitesting-authenticated"] + extra
        // Pin the text size either way: a simulator left at a large size must not decide the result.
        app.launchArguments += ["-UIPreferredContentSizeCategoryName", largeText ? "UICTContentSizeCategoryAccessibilityXXXL" : "UICTContentSizeCategoryL"]
        app.launch()
        return app
    }

    private func shot(_ name: String) -> XCTAttachment {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        return attachment
    }

    /// The centre of the three buttons together against the middle of the screen.
    private func assertCentered(_ app: XCUIApplication, _ ids: [String], file: StaticString = #filePath, line: UInt = #line) {
        let frames = ids.map { app.buttons[$0].frame }
        let left = frames.map(\.minX).min()!, right = frames.map(\.maxX).max()!
        XCTAssertEqual((left + right) / 2, app.frame.midX, accuracy: 2, "controls centred (left \(left), right \(right), screen \(app.frame.width))", file: file, line: line)
    }

    @MainActor
    func testRadioControlsAreCentred() {
        let app = launch()
        XCTAssertTrue(app.buttons["radio.playPause"].waitForExistence(timeout: 15))
        assertCentered(app, ["radio.previous", "radio.playPause", "radio.next"])
        XCTAssertLessThanOrEqual(app.buttons["radio.more"].frame.maxX, app.buttons["radio.previous"].frame.minX, "the menu is beside them, not among them")
        add(shot("Radio-controls-centered"))
    }

    @MainActor
    func testRadioControlsStayCentredAtLargeText() {
        let app = launch(largeText: true)
        XCTAssertTrue(app.buttons["radio.playPause"].waitForExistence(timeout: 15))
        app.swipeUp()
        assertCentered(app, ["radio.previous", "radio.playPause", "radio.next"])
    }

    @MainActor
    func testPlayerIslandControlsAreCentredOnOtherTabs() {
        let app = launch(["--uitesting-tab=library"])
        XCTAssertTrue(app.buttons["player.playPause"].waitForExistence(timeout: 15))
        assertCentered(app, ["player.previous", "player.playPause", "player.next"])
        add(shot("Island-controls-centered"))
    }

    @MainActor
    func testIslandControlsAreCentredWhileMemoryPlaysAndTitlesAreLong() {
        let app = launch(["--uitesting-tab=memories", "--uitesting-memories-sample"])
        XCTAssertTrue(app.buttons["player.playPause"].waitForExistence(timeout: 15))
        assertCentered(app, ["player.previous", "player.playPause", "player.next"])
        add(shot("Memories-island-controls-centered"))
    }

    @MainActor
    func testControlsAreCentredAboveTheKeyboardInChat() {
        let app = launch(["--uitesting-tab=chat", "--uitesting-focus-chat"])
        XCTAssertTrue(app.buttons["chat.dismissKeyboard"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.buttons["player.playPause"].waitForExistence(timeout: 5))
        assertCentered(app, ["player.previous", "player.playPause", "player.next"])
    }
}
