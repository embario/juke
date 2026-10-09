import XCTest

final class MemoryNextUITests: XCTestCase {
    @MainActor
    func testNextStepsToTheNextMemoryChronologically() {
        let app = XCUIApplication()
        app.launchArguments = ["--uitesting", "--uitesting-authenticated", "--uitesting-tab=memories", "--uitesting-memories-sample"]
        app.launch()

        // Newest first in the list; by date the order is Late night (3 days ago) < Sunday drive < Beach.
        let oldest = app.staticTexts["Late night listening"]
        XCTAssertTrue(oldest.waitForExistence(timeout: 10))
        oldest.tap()
        let play = app.buttons["memory.playMoment"]
        XCTAssertTrue(play.waitForExistence(timeout: 5))
        play.tap()
        let next = app.buttons["player.next"]
        XCTAssertTrue(next.waitForExistence(timeout: 5))
        XCTAssertTrue(next.isHittable, "player controls stay available inside a memory")
        add(shot("Memory-detail-playing"))

        next.tap()
        app.navigationBars.buttons.firstMatch.tap()
        XCTAssertTrue(playingRow("Sunday drive").waitForExistence(timeout: 5), "Next plays the next memory in time")
        XCTAssertFalse(playingRow("Late night listening").exists)
        add(shot("Memories-after-next-1"))

        next.tap()
        XCTAssertTrue(playingRow("Beach with the family").waitForExistence(timeout: 5))
        XCTAssertFalse(playingRow("Sunday drive").exists)
        add(shot("Memories-after-next-2"))

        next.tap()  // Beach is the latest memory with a song: nothing later to play
        XCTAssertTrue(app.alerts["Playback"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.alerts["Playback"].staticTexts["That's the latest memory."].exists)
        add(shot("Memories-latest-memory"))
        app.alerts["Playback"].buttons.firstMatch.tap()
        XCTAssertTrue(playingRow("Beach with the family").exists, "still playing the latest memory")

        app.buttons["player.previous"].tap()
        XCTAssertTrue(playingRow("Sunday drive").waitForExistence(timeout: 5), "Previous steps back in time")
    }

    private func playingRow(_ title: String) -> XCUIElement {
        XCUIApplication().cells.containing(.staticText, identifier: title).descendants(matching: .image).matching(identifier: "memory.playing").firstMatch
    }

    private func shot(_ name: String) -> XCTAttachment {
        let attachment = XCTAttachment(screenshot: XCUIApplication().screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        return attachment
    }
}
