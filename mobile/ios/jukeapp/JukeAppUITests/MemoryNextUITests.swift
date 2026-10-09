import XCTest

final class MemoryNextUITests: XCTestCase {
    @MainActor
    func testNextStepsToTheNextMemoryChronologically() {
        let app = XCUIApplication()
        app.launchArguments = ["--uitesting", "--uitesting-authenticated", "--uitesting-tab=memories", "--uitesting-memories-sample"]
        app.launch()

        // Deck order is shuffled; by date the order is Late night (3 days ago) < Sunday drive < Beach.
        XCTAssertTrue(card(app).waitForExistence(timeout: 10))
        bringToTop("Late night listening", in: app)
        card(app).tap()
        let play = app.buttons["memory.playMoment"]
        XCTAssertTrue(play.waitForExistence(timeout: 5))
        play.tap()
        let next = app.buttons["player.next"]
        XCTAssertTrue(next.waitForExistence(timeout: 5))
        XCTAssertTrue(next.isHittable, "player controls stay available inside a memory")
        add(shot("Memory-detail-playing"))

        next.tap()
        app.navigationBars.buttons.firstMatch.tap()
        XCTAssertTrue(isPlaying("Sunday drive", in: app), "Next plays the next memory in time")
        XCTAssertFalse(isPlaying("Late night listening", in: app))
        add(shot("Memories-after-next-1"))

        next.tap()
        XCTAssertTrue(isPlaying("Beach with the family", in: app))
        XCTAssertFalse(isPlaying("Sunday drive", in: app))
        add(shot("Memories-after-next-2"))

        next.tap()  // Beach is the latest memory with a song: nothing later to play
        XCTAssertTrue(app.alerts["Playback"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.alerts["Playback"].staticTexts["That's the latest memory."].exists)
        add(shot("Memories-latest-memory"))
        app.alerts["Playback"].buttons.firstMatch.tap()
        XCTAssertTrue(isPlaying("Beach with the family", in: app), "still playing the latest memory")

        app.buttons["player.previous"].tap()
        XCTAssertTrue(isPlaying("Sunday drive", in: app), "Previous steps back in time")
    }

    private func card(_ app: XCUIApplication) -> XCUIElement {
        app.descendants(matching: .any).matching(identifier: "memory.card").firstMatch
    }

    private func bringToTop(_ title: String, in app: XCUIApplication) {
        for _ in 0..<5 where !card(app).label.hasPrefix(title) { app.buttons["memory.deck.next"].tap() }
        XCTAssertTrue(card(app).label.hasPrefix(title))
    }

    /// Walks the deck to the memory's card and reads its "Playing" value.
    private func isPlaying(_ title: String, in app: XCUIApplication) -> Bool {
        Thread.sleep(forTimeInterval: 1)
        bringToTop(title, in: app)
        return (card(app).value as? String) == "Playing"
    }

    private func shot(_ name: String) -> XCTAttachment {
        let attachment = XCTAttachment(screenshot: XCUIApplication().screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        return attachment
    }
}
