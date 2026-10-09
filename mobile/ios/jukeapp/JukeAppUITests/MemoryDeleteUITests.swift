import XCTest

final class MemoryDeleteUITests: XCTestCase {
    @MainActor
    func testDeletingAMemoryRequiresConfirmationAndRemovesItFromTheDeck() {
        let app = XCUIApplication()
        app.launchArguments = ["--uitesting", "--uitesting-authenticated", "--uitesting-tab=memories", "--uitesting-memories-sample"]
        app.launch()

        let card = app.descendants(matching: .any).matching(identifier: "memory.card").firstMatch
        XCTAssertTrue(card.waitForExistence(timeout: 10))
        XCTAssertEqual(app.staticTexts["memory.position"].label, "1 of 4")
        let doomed = card.label

        app.buttons["memory.menu"].tap()
        let delete = app.buttons["memory.delete"]
        XCTAssertTrue(delete.waitForExistence(timeout: 5))
        delete.tap()

        let confirm = app.buttons["Delete Memory"]
        XCTAssertTrue(confirm.waitForExistence(timeout: 5), "deleting asks first")
        XCTAssertEqual(app.staticTexts["memory.position"].label, "1 of 4", "nothing is deleted until confirmed")
        attachScreenshot(of: app, named: "Memories-delete-confirmation")
        confirm.tap()

        XCTAssertTrue(app.staticTexts["memory.position"].waitForExistence(timeout: 5))
        let gone = NSPredicate(format: "label == %@", "1 of 3")
        expectation(for: gone, evaluatedWith: app.staticTexts["memory.position"])
        waitForExpectations(timeout: 5)
        XCTAssertNotEqual(card.label, doomed, "the deleted memory is no longer on top")
        for _ in 0..<3 {
            XCTAssertNotEqual(card.label, doomed)
            app.buttons["memory.deck.next"].tap()
        }
    }

    @MainActor
    private func attachScreenshot(of app: XCUIApplication, named name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
