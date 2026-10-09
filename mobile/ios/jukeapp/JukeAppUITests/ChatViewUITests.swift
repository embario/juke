import XCTest

final class ChatViewUITests: XCTestCase {
    @MainActor
    func testKeyboardControlsRemainSeparateAndDonePreservesDraft() {
        checkKeyboardControls(largeText: false)
    }

    @MainActor
    func testLargeTextKeyboardControlsRemainSeparateAndDonePreservesDraft() {
        checkKeyboardControls(largeText: true)
    }

    @MainActor
    private func checkKeyboardControls(largeText: Bool) {
        let app = XCUIApplication()
        app.launchArguments = ["--uitesting", "--uitesting-authenticated", "--uitesting-tab=chat", "--uitesting-focus-chat"]
        if largeText {
            app.launchArguments += ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"]
        }
        app.launch()

        let draft = app.descendants(matching: .any).matching(identifier: "chat.draft").firstMatch
        XCTAssertTrue(draft.waitForExistence(timeout: 10))
        let done = app.buttons["chat.dismissKeyboard"]
        let send = app.buttons["chat.send"]
        XCTAssertTrue(done.waitForExistence(timeout: 5))
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
        XCTAssertFalse(send.isEnabled)
        draft.typeText("Why does this song feel familiar?\nTell me a little more.")
        XCTAssertTrue(send.isEnabled)
        XCTAssertTrue(done.isHittable)
        XCTAssertTrue(send.isHittable)
        XCTAssertGreaterThanOrEqual(done.frame.height, 44)
        XCTAssertGreaterThanOrEqual(done.frame.width, 44)
        XCTAssertGreaterThanOrEqual(send.frame.height, 44)
        XCTAssertGreaterThanOrEqual(send.frame.width, 44)
        XCTAssertTrue(app.frame.contains(done.frame))
        XCTAssertTrue(app.frame.contains(send.frame))
        XCTAssertFalse(done.frame.intersects(send.frame))
        XCTAssertLessThanOrEqual(done.frame.maxY, send.frame.minY)
        XCTAssertLessThanOrEqual(send.frame.maxY, app.keyboards.firstMatch.frame.minY)
        let screenshot = XCTAttachment(screenshot: app.screenshot())
        screenshot.name = "Chat-keyboard-visible"
        screenshot.lifetime = .keepAlways
        add(screenshot)

        done.tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForNonExistence(timeout: 5))
        XCTAssertEqual(draft.value as? String, "Why does this song feel familiar?\nTell me a little more.")
        XCTAssertTrue(send.isEnabled)
        draft.tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
        XCTAssertTrue(done.isHittable)
        XCTAssertTrue(send.isHittable)
    }

    @MainActor
    func testPlayerControlsStayAvailableWithAndWithoutKeyboard() {
        let app = XCUIApplication()
        app.launchArguments = ["--uitesting", "--uitesting-authenticated", "--uitesting-tab=chat"]
        app.launch()

        let draft = app.descendants(matching: .any).matching(identifier: "chat.draft").firstMatch
        XCTAssertTrue(draft.waitForExistence(timeout: 10))
        for id in ["player.previous", "player.playPause", "player.next"] {
            XCTAssertTrue(app.buttons[id].waitForExistence(timeout: 5), "\(id) above the composer")
            XCTAssertTrue(app.buttons[id].isHittable)
        }
        let island = XCTAttachment(screenshot: app.screenshot())
        island.name = "Chat-player-island"
        island.lifetime = .keepAlways
        add(island)

        draft.tap()
        XCTAssertTrue(app.keyboards.firstMatch.waitForExistence(timeout: 5))
        let done = app.buttons["chat.dismissKeyboard"]
        let send = app.buttons["chat.send"]
        XCTAssertTrue(done.waitForExistence(timeout: 5))
        for id in ["player.previous", "player.playPause", "player.next"] {
            let button = app.buttons[id]
            XCTAssertTrue(button.exists && button.isHittable, "\(id) beside Done while typing")
            XCTAssertFalse(button.frame.intersects(done.frame))
            XCTAssertFalse(button.frame.intersects(send.frame))
            XCTAssertGreaterThanOrEqual(button.frame.height, 44)
        }
        let typing = XCTAttachment(screenshot: app.screenshot())
        typing.name = "Chat-player-controls-keyboard"
        typing.lifetime = .keepAlways
        add(typing)
    }
}
