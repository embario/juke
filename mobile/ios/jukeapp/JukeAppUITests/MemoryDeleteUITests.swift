import XCTest

final class MemoryDeleteUITests: XCTestCase {
    @MainActor
    func testDeletingAMemoryRequiresConfirmationAndRemovesTheRow() {
        let app = XCUIApplication()
        app.launchArguments = [
            "--uitesting",
            "--uitesting-authenticated",
            "--uitesting-tab=memories",
            "--uitesting-memories-sample",
        ]
        app.launch()

        let memory = app.staticTexts["Beach with the family"]
        XCTAssertTrue(memory.waitForExistence(timeout: 10))
        attachScreenshot(of: app, named: "Memories-before-delete")

        let memoryRow = app.cells.containing(.staticText, identifier: "Beach with the family").firstMatch
        XCTAssertTrue(memoryRow.exists)
        memoryRow.swipeLeft()
        let delete = app.buttons["memory.delete"]
        XCTAssertTrue(delete.waitForExistence(timeout: 5))
        delete.tap()

        let confirm = app.buttons["Delete Memory"]
        XCTAssertTrue(confirm.waitForExistence(timeout: 5))
        attachScreenshot(of: app, named: "Memories-delete-confirmation")
        confirm.tap()

        XCTAssertTrue(memory.waitForNonExistence(timeout: 5))
    }

    @MainActor
    private func attachScreenshot(of app: XCUIApplication, named name: String) {
        let attachment = XCTAttachment(screenshot: app.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }
}
