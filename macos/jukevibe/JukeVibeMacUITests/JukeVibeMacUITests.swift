import XCTest

final class JukeVibeMacUITests: XCTestCase {
    private var app: XCUIApplication!

    override func setUp() {
        super.setUp()
        continueAfterFailure = false
        app = XCUIApplication()
    }

    override func tearDown() {
        app?.terminate()
        app = nil
        super.tearDown()
    }

    func testSignedOutExperienceExposesAccountFlows() {
        launch()

        XCTAssertTrue(app.staticTexts["Juke Vibe"].waitForExistence(timeout: 4))
        XCTAssertTrue(app.buttons["authentication.signIn"].exists)
        XCTAssertTrue(app.buttons["authentication.createAccount"].exists)
    }

    func testChatRespondsAsynchronouslyWithTypingFeedback() {
        launchAuthenticated()
        let composer = element("chat.composer")
        XCTAssertTrue(composer.waitForExistence(timeout: 4))

        composer.click()
        composer.typeText("Why does this recording feel so spacious?")
        app.buttons["chat.send"].click()

        XCTAssertTrue(app.staticTexts["Why does this recording feel so spacious?"].waitForExistence(timeout: 2))
        XCTAssertTrue(element("chat.typingIndicator").waitForExistence(timeout: 2))
        XCTAssertFalse(app.staticTexts["Juke is typing"].exists)
        XCTAssertTrue(app.staticTexts["That muted trumpet opens a spacious conversation. What part of the performance draws you back in?"].waitForExistence(timeout: 4))
        XCTAssertFalse(element("chat.typingIndicator").exists)
        composer.click()
        composer.typeText("A follow-up")
        XCTAssertEqual(composer.value as? String, "A follow-up")
    }

    func testDiscoveryLibraryNowPlayingAndSettingsAreReachable() {
        launchAuthenticated()

        XCTAssertTrue(element("nowPlaying.bar").waitForExistence(timeout: 4))
        XCTAssertTrue(app.staticTexts["Blue in Green"].exists)
        XCTAssertTrue(app.sliders["Playback position"].exists)
        let pause = app.buttons["Pause"]
        XCTAssertTrue(pause.isEnabled)
        pause.click()
        XCTAssertTrue(app.buttons["Play"].waitForExistence(timeout: 2))

        app.buttons["sidebar.discover"].click()
        let search = element("discover.query")
        XCTAssertTrue(search.waitForExistence(timeout: 3))
        search.click()
        search.typeText("Miles Davis")
        app.buttons["discover.search"].click()
        XCTAssertTrue(app.staticTexts["Kind of Blue"].waitForExistence(timeout: 4))
        XCTAssertFalse(app.buttons["Ask Juke about this"].exists)
        app.staticTexts["Kind of Blue"].doubleClick()
        XCTAssertTrue(app.buttons["Pause"].waitForExistence(timeout: 2))

        app.buttons["sidebar.library"].click()
        XCTAssertTrue(app.staticTexts["Your Juke library"].waitForExistence(timeout: 3))

        app.buttons["sidebar.settings"].click()
        XCTAssertTrue(element("settings.view").waitForExistence(timeout: 4))
        XCTAssertTrue(app.staticTexts["Conversation privacy"].exists)
    }

    func testEncryptionEducationIsAOneTimeLoginMoment() {
        launchAuthenticated(additionalArguments: ["--uitesting-show-privacy-welcome", "--uitesting-reset-privacy-welcome"])

        let acknowledgment = app.sheets.firstMatch.buttons["Got it"]
        XCTAssertTrue(acknowledgment.waitForExistence(timeout: 4))
        acknowledgment.click()
        XCTAssertFalse(acknowledgment.exists)

        app.terminate()
        launchAuthenticated(additionalArguments: ["--uitesting-show-privacy-welcome"])
        XCTAssertFalse(app.sheets.firstMatch.buttons["Got it"].waitForExistence(timeout: 1))
    }

    func testSpotifySpectatorModeRemovesPlaybackActions() {
        launchAuthenticated(additionalArguments: ["--uitesting-spectator"])

        XCTAssertTrue(element("nowPlaying.spectatorMode").waitForExistence(timeout: 4))
        XCTAssertFalse(app.buttons["Pause"].exists)
        XCTAssertFalse(app.buttons["Play"].exists)
        XCTAssertFalse(app.sliders["Playback position"].exists)
        XCTAssertTrue(element("nowPlaying.passiveProgress").exists)

        app.buttons["sidebar.discover"].click()
        XCTAssertTrue(element("discover.spectatorMode").waitForExistence(timeout: 3))
        let search = element("discover.query")
        search.click()
        search.typeText("Miles Davis")
        app.buttons["discover.search"].click()
        XCTAssertTrue(app.staticTexts["Kind of Blue"].waitForExistence(timeout: 4))
        app.staticTexts["Kind of Blue"].doubleClick()
        XCTAssertFalse(app.buttons["Pause"].exists)
        XCTAssertTrue(element("discover.spectatorMode").exists)
    }

    func testChatRemainsResponsiveAcrossFocusChanges() {
        launchAuthenticated()
        let composer = element("chat.composer")
        XCTAssertTrue(composer.waitForExistence(timeout: 4))

        let finder = XCUIApplication(bundleIdentifier: "com.apple.finder")
        for _ in 0..<5 {
            finder.activate()
            app.activate()
            XCTAssertTrue(composer.waitForExistence(timeout: 2))
        }

        composer.click()
        composer.typeText("Still responsive")
        XCTAssertEqual(composer.value as? String, "Still responsive")
    }

    private func launchAuthenticated(additionalArguments: [String] = []) {
        launch(arguments: ["--uitesting-authenticated"] + additionalArguments)
    }

    private func launch(arguments: [String] = []) {
        app.launchArguments = ["--uitesting"] + arguments
        app.launch()
    }

    private func element(_ identifier: String) -> XCUIElement {
        app.descendants(matching: .any)[identifier]
    }
}
