import XCTest

/// Now Playing: a much larger vinyl, and the tuner in a bottom drawer. Fixture radio.
final class RadioTunerUITests: XCTestCase {
    private func launch(largeText: Bool = false) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["--uitesting", "--uitesting-authenticated"]
        if largeText { app.launchArguments += ["-UIPreferredContentSizeCategoryName", "UICTContentSizeCategoryAccessibilityXXXL"] }
        app.launch()
        return app
    }

    private func shot(_ name: String) -> XCTAttachment {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        return attachment
    }

    @MainActor
    func testVinylIsLargeAndTheTunerStartsClosed() {
        let app = launch()
        let handle = app.buttons["radio.tuner.handle"]
        XCTAssertTrue(handle.waitForExistence(timeout: 15))
        XCTAssertTrue(handle.isHittable)
        // The sleeve (labelled with the song) is the left part of the sleeve-and-record row.
        let sleeve = app.descendants(matching: .any).matching(NSPredicate(format: "label == 'Blue in Green by Miles Davis'")).firstMatch
        XCTAssertTrue(sleeve.waitForExistence(timeout: 5))
        XCTAssertGreaterThanOrEqual(sleeve.frame.width, 200, "the sleeve was at most 196 pt (and 120 pt on this phone) before")
        add(shot("Radio-drawer-closed"))
    }

    @MainActor
    func testTapOpensAndClosesTheDrawer() {
        let app = launch()
        let handle = app.buttons["radio.tuner.handle"]
        XCTAssertTrue(handle.waitForExistence(timeout: 15))
        XCTAssertEqual(handle.label, "Tuner, closed")
        handle.tap()
        XCTAssertTrue(waitForLabel(handle, "Tuner, open"))
        sleep(1)
        add(shot("Radio-drawer-open"))
        handle.tap()
        XCTAssertTrue(waitForLabel(handle, "Tuner, closed"))
    }

    @MainActor
    func testDraggingTheHandleOpensAndClosesTheDrawer() {
        let app = launch()
        let handle = app.buttons["radio.tuner.handle"]
        XCTAssertTrue(handle.waitForExistence(timeout: 15))
        handle.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
            .press(forDuration: 0.05, thenDragTo: handle.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: -4)))
        XCTAssertTrue(waitForLabel(handle, "Tuner, open"), "an upward drag opens it")
        sleep(1)  // let the drawer finish moving before the next drag
        handle.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.5))
            .press(forDuration: 0.05, thenDragTo: handle.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 2)))
        add(shot("Radio-drawer-after-down-drag"))
        XCTAssertTrue(waitForLabel(handle, "Tuner, closed"), "a downward drag closes it")
    }

    @MainActor
    func testPlayerControlsAndDrawerHandleAreReachableAtLargeText() {
        let app = launch(largeText: true)
        let handle = app.buttons["radio.tuner.handle"]
        XCTAssertTrue(handle.waitForExistence(timeout: 15))
        XCTAssertTrue(handle.isHittable)
        XCTAssertGreaterThanOrEqual(handle.frame.height, 44)
        handle.tap()
        XCTAssertTrue(waitForLabel(handle, "Tuner, open"))
        XCTAssertTrue(handle.isHittable)
        add(shot("Radio-drawer-open-large-text"))
    }

    private func waitForLabel(_ element: XCUIElement, _ label: String) -> Bool {
        let expectation = XCTNSPredicateExpectation(predicate: NSPredicate(format: "label == %@", label), object: element)
        return XCTWaiter().wait(for: [expectation], timeout: 5) == .completed
    }
}
