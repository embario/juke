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
        XCTAssertGreaterThanOrEqual(send.frame.height, 44)
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
}
