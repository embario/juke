import XCTest

/// Artist and album screens: the downward swipe reveals the details, the upward one returns,
/// and the buttons do the same without a gesture. Fixture catalog (Miles Davis / Kind of Blue).
final class DetailViewsUITests: XCTestCase {
    /// Track rows are buttons whose label joins the number, title and length.
    private func row(_ app: XCUIApplication, _ title: String) -> XCUIElement {
        app.buttons.matching(NSPredicate(format: "label CONTAINS %@", title)).firstMatch
    }

    private func launch(_ extra: [String]) -> XCUIApplication {
        let app = XCUIApplication()
        app.launchArguments = ["--uitesting", "--uitesting-authenticated"] + extra
        app.launch()
        return app
    }

    @MainActor
    func testAlbumTracklistComesDownWithASwipeAndGoesBackUp() {
        let app = launch(["--uitesting-tab=library", "--uitesting-kind=album", "--uitesting-browse"])
        let reveal = app.buttons["album.reveal"]
        XCTAssertTrue(reveal.waitForExistence(timeout: 15))
        XCTAssertTrue(app.buttons["album.play"].waitForExistence(timeout: 10))
        add(shot("Album-pane"))
        XCTAssertFalse(row(app, "Freddie Freeloader").exists, "the tracklist is not on screen yet")

        // Swipe down on the cover.
        let top = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.22))
        top.press(forDuration: 0.05, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.85)))
        XCTAssertTrue(row(app, "Freddie Freeloader").waitForExistence(timeout: 5))
        XCTAssertTrue(app.buttons["album.hide"].isHittable)
        sleep(1)
        add(shot("Album-tracks"))

        // Swipe up on the handle to return.
        app.buttons["album.hide"].swipeUp()
        XCTAssertTrue(app.buttons["album.play"].waitForExistence(timeout: 5))
        XCTAssertFalse(app.buttons["album.hide"].isHittable)
    }

    @MainActor
    func testAlbumRevealWorksWithoutTheGesture() {
        let app = launch(["--uitesting-tab=library", "--uitesting-kind=album", "--uitesting-browse"])
        XCTAssertTrue(app.buttons["album.reveal"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.buttons["album.play"].waitForExistence(timeout: 10))
        app.buttons["album.reveal"].tap()
        XCTAssertTrue(row(app, "So What").waitForExistence(timeout: 5))
        app.buttons["album.hide"].tap()
        XCTAssertTrue(app.buttons["album.play"].waitForExistence(timeout: 5))
    }

    @MainActor
    func testShortDragIsCancelled() {
        let app = launch(["--uitesting-tab=library", "--uitesting-kind=album", "--uitesting-browse"])
        XCTAssertTrue(app.buttons["album.play"].waitForExistence(timeout: 15))
        let top = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.22))
        top.press(forDuration: 0.05, thenDragTo: app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.28)))
        XCTAssertFalse(row(app, "Freddie Freeloader").exists, "a short drag does not keep the tracklist")
        XCTAssertTrue(app.buttons["album.play"].isHittable)
    }

    @MainActor
    func testArtistDetailsComeDownAndRelatedArtistsOpen() {
        let app = launch(["--uitesting-tab=library", "--uitesting-kind=artist", "--uitesting-browse"])
        XCTAssertTrue(app.buttons["artist.reveal"].waitForExistence(timeout: 15))
        XCTAssertTrue(app.buttons["artist.filter.albums"].waitForExistence(timeout: 10))
        add(shot("Artist-pane"))
        app.buttons["artist.reveal"].tap()
        XCTAssertTrue(app.staticTexts["Top songs"].waitForExistence(timeout: 5))
        XCTAssertTrue(app.staticTexts["John Coltrane"].exists)
        sleep(1)
        add(shot("Artist-details"))
        app.buttons["artist.hide"].tap()
        XCTAssertTrue(app.buttons["artist.filter.albums"].waitForExistence(timeout: 5))
    }

    @MainActor
    func testRadioOpensTheArtistAndAlbumInASheet() {
        let app = launch([])
        let artist = app.buttons["radio.artistDetails"]
        XCTAssertTrue(artist.waitForExistence(timeout: 15))
        artist.tap()
        XCTAssertTrue(app.buttons["artist.reveal"].waitForExistence(timeout: 10), "the artist screen opens from Radio")
        add(shot("Radio-artist-sheet"))
        app.buttons["detail.done"].tap()
        XCTAssertTrue(app.buttons["radio.albumDetails"].waitForExistence(timeout: 5))
        app.buttons["radio.albumDetails"].tap()
        XCTAssertTrue(app.buttons["album.reveal"].waitForExistence(timeout: 10), "the album screen opens from Radio")
    }

    private func shot(_ name: String) -> XCTAttachment {
        let attachment = XCTAttachment(screenshot: XCUIScreen.main.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        return attachment
    }
}
