import XCTest

final class JukeMacUITests: XCTestCase {
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

        XCTAssertTrue(app.staticTexts["Juke"].waitForExistence(timeout: 4))
        XCTAssertTrue(app.buttons["authentication.signIn"].exists)
        XCTAssertTrue(app.buttons["authentication.createAccount"].exists)
    }

    func testRadioIsTheStartingSectionAndNavigationReachesEverySection() {
        launch(arguments: ["--uitesting-authenticated"])

        XCTAssertTrue(element("radio.screen").waitForExistence(timeout: 4))
        for section in ["radio", "library", "memories", "chat"] {
            XCTAssertTrue(app.buttons["nav.\(section)"].exists, section)
        }
        XCTAssertFalse(element("miniPlayer").exists, "Radio shows the full player, not the mini pill")
        attachScreenshot("radio")

        open("library")
        XCTAssertTrue(element("miniPlayer").waitForExistence(timeout: 2))
        attachScreenshot("library")
        open("memories")
        XCTAssertTrue(app.buttons["memory.new"].waitForExistence(timeout: 4))
        attachScreenshot("memories")
        open("chat")
        XCTAssertTrue(element("chat.composer").waitForExistence(timeout: 4))
        attachScreenshot("chat")

        app.buttons["miniPlayer.openRadio"].click()
        XCTAssertTrue(element("radio.screen").waitForExistence(timeout: 3))
        XCTAssertFalse(element("miniPlayer").waitForExistence(timeout: 1))

        app.typeKey("3", modifierFlags: .command)
        XCTAssertTrue(element("memories.screen").waitForExistence(timeout: 3))
    }

    func testAppearanceControlSwitchesLightAndDark() {
        launch(arguments: ["--uitesting-authenticated"])
        XCTAssertTrue(app.buttons["appearance.dark"].waitForExistence(timeout: 4))
        app.buttons["appearance.dark"].click()
        attachScreenshot("radio-dark")
        app.buttons["appearance.light"].click()
        attachScreenshot("radio-light")
        app.buttons["appearance.system"].click()
        XCTAssertTrue(element("radio.screen").exists)
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

        open("library")
        let search = element("discover.query")
        XCTAssertTrue(search.waitForExistence(timeout: 3))
        search.click()
        search.typeText("Miles Davis")
        app.buttons["discover.search"].click()
        XCTAssertTrue(app.staticTexts["Blue in Green"].waitForExistence(timeout: 4))
        XCTAssertFalse(app.buttons["Ask Juke about this"].exists)
        element("discover.result.1959").click()
        XCTAssertTrue(element("catalog.albumDetail").waitForExistence(timeout: 4))
        XCTAssertTrue(element("catalog.track.highlighted").exists)

        XCTAssertTrue(element("miniPlayer").exists)

        app.typeKey(",", modifierFlags: .command)
        XCTAssertTrue(element("settings.view").waitForExistence(timeout: 4))
        XCTAssertTrue(element("settings.chatTextSize").exists)
        XCTAssertTrue(element("settings.appearance").exists)
        XCTAssertTrue(element("settings.crateFlip").exists)
        XCTAssertTrue(element("settings.backgroundRecognition").exists)
        XCTAssertTrue(element("settings.backendURL").exists)
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
        element("nowPlaying.spectatorMode").click()
        XCTAssertTrue(app.staticTexts["Playback mode"].waitForExistence(timeout: 2))
        app.typeKey(.escape, modifierFlags: [])

        open("library")
        XCTAssertTrue(element("discover.spectatorMode").waitForExistence(timeout: 3))
        let search = element("discover.query")
        search.click()
        search.typeText("Miles Davis")
        app.buttons["discover.search"].click()
        XCTAssertTrue(app.staticTexts["Blue in Green"].waitForExistence(timeout: 4))
        element("discover.result.1959").click()
        XCTAssertTrue(element("catalog.albumDetail").waitForExistence(timeout: 4))
        XCTAssertTrue(element("catalog.spectatorHint").exists)
        XCTAssertFalse(app.buttons["Pause"].exists)
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

    func testAuthenticatedMemoryCanBeReviewedSavedBrowsedAndRetagged() {
        launch(arguments: ["--uitesting-authenticated"])
        open("memories")
        beginStory()
        let body = element("memory.body")
        body.click(); body.typeText("The long way home. #Rainy-walks")
        app.buttons["memory.next"].click()
        XCTAssertTrue(app.buttons["memory.save"].waitForExistence(timeout: 4))
        XCTAssertFalse(body.exists)
        app.buttons["memory.save"].click()
        XCTAssertTrue(app.buttons["memory.openSaved"].waitForExistence(timeout: 4))
        app.buttons["memory.openSaved"].click()
        XCTAssertTrue(element("memory.detail").waitForExistence(timeout: 4))
        XCTAssertTrue(app.staticTexts["#Rainy-walks"].exists)
        app.buttons["memory.editTags"].click()
        let editor = element("memory.tagEditor")
        XCTAssertTrue(editor.waitForExistence(timeout: 2))
        editor.click(); editor.typeKey("a", modifierFlags: .command); editor.typeText("Our song")
        app.buttons["memory.saveTags"].click()
        XCTAssertTrue(app.staticTexts["#Our song"].waitForExistence(timeout: 3))
        beginStory()
        element("memory.body").click(); element("memory.body").typeText("Another moment with the same song.")
        app.buttons["memory.next"].click()
        XCTAssertTrue(app.buttons["memory.tags"].waitForExistence(timeout: 4))
        app.buttons["memory.tags"].click()
        let reuse = app.buttons["memory.reuseTag.Our song"]
        XCTAssertTrue(reuse.waitForExistence(timeout: 3)); reuse.click()
        app.buttons["memory.next"].click()
        app.buttons["memory.save"].click()
        XCTAssertTrue(app.buttons["memory.openSaved"].waitForExistence(timeout: 4))
        app.buttons["memory.openSaved"].click()
        XCTAssertTrue(app.staticTexts["#Our song"].waitForExistence(timeout: 4))
    }

    func testMemoryComposerRequiresContentBeforeReview() {
        launch(arguments: ["--uitesting-authenticated"])
        open("memories")
        beginStory()
        XCTAssertFalse(app.buttons["memory.next"].isEnabled)
        XCTAssertFalse(element("memory.title").exists)
        XCTAssertFalse(app.buttons["memory.photos"].exists)
        XCTAssertFalse(element("nowPlaying.bar").exists)
        XCTAssertFalse(element("miniPlayer").exists, "the mini player hides during the memory journey")
        let body = element("memory.body")
        body.click(); body.typeText("A few words are enough.")
        XCTAssertTrue(app.buttons["memory.next"].isEnabled)
        app.buttons["memory.back"].click()
        XCTAssertTrue(app.buttons["memory.addCurrentSong"].waitForExistence(timeout: 3))
        XCTAssertFalse(body.exists)
        app.buttons["memory.next"].click()
        XCTAssertTrue(body.waitForExistence(timeout: 3))
        XCTAssertEqual(body.value as? String, "A few words are enough.")
    }

    func testInlineTimeTravelAndSongOnlyMemory() {
        launch(arguments: ["--uitesting-authenticated"])
        open("memories")
        XCTAssertTrue(app.buttons["memory.new"].waitForExistence(timeout: 4))
        app.buttons["memory.new"].click()
        XCTAssertFalse(element("memory.body").exists)
        XCTAssertFalse(app.sheets.firstMatch.exists)
        app.buttons["memory.next"].click()
        let song = app.buttons["memory.addCurrentSong"]
        XCTAssertTrue(song.waitForExistence(timeout: 3)); song.click()
        app.buttons["memory.next"].click()
        XCTAssertTrue(element("memory.body").waitForExistence(timeout: 3))
        app.buttons["memory.next"].click()
        XCTAssertTrue(app.buttons["memory.timeTravel"].waitForExistence(timeout: 4))
        app.buttons["memory.timeTravel"].click()
        let yesterday = app.buttons["memory.yesterday"]
        XCTAssertTrue(yesterday.waitForExistence(timeout: 3)); yesterday.click()
        app.buttons["memory.next"].click()
        app.buttons["memory.save"].click()
        XCTAssertTrue(app.buttons["memory.openSaved"].waitForExistence(timeout: 4))
        app.buttons["memory.openSaved"].click()
        XCTAssertTrue(element("memory.detail").waitForExistence(timeout: 4))
        XCTAssertTrue(app.staticTexts["Blue in Green"].firstMatch.exists)
        let day = Calendar.current.date(byAdding: .day, value: -1, to: Date())!
        XCTAssertTrue(app.staticTexts[day.formatted(date: .long, time: .omitted)].exists)
    }

    private func beginStory() {
        XCTAssertTrue(app.buttons["memory.new"].waitForExistence(timeout: 4))
        app.buttons["memory.new"].click()
        XCTAssertTrue(app.buttons["memory.next"].waitForExistence(timeout: 3))
        app.buttons["memory.next"].click()
        XCTAssertTrue(app.buttons["memory.addCurrentSong"].waitForExistence(timeout: 3))
        app.buttons["memory.next"].click()
        XCTAssertTrue(element("memory.body").waitForExistence(timeout: 3))
    }

    @MainActor
    func testLiveBackendAuthenticatedMemoryPersistsAndReusesTags() async throws {
        guard FileManager.default.fileExists(atPath: "/tmp/juke-vibe-live-ui-enabled") else {
            throw XCTSkip("Live memory backend testing requires the explicit local opt-in marker.")
        }
        let credentialsURL = URL(fileURLWithPath: "/tmp/juke-vibe-test-credentials.json")
        guard let credentialData = try? Data(contentsOf: credentialsURL),
              let credentials = try? JSONDecoder().decode(LiveMemoryCredentials.self, from: credentialData),
              let origin = URL(string: credentials.baseURL),
              ["127.0.0.1", "localhost"].contains(origin.host ?? "") else {
            XCTFail("Live memory testing requires valid private credentials for the isolated local backend.")
            return
        }
        let session = URLSession(configuration: .ephemeral)
        defer { session.invalidateAndCancel() }
        var login = URLRequest(url: origin.appending(path: "api/v1/auth/accounts/login/"))
        login.httpMethod = "POST"
        login.setValue("application/json", forHTTPHeaderField: "Content-Type")
        login.httpBody = try JSONEncoder().encode(LiveMemoryLogin(login: credentials.username, password: credentials.password))
        let (loginData, loginResponse) = try await session.data(for: login)
        guard (loginResponse as? HTTPURLResponse)?.statusCode == 200,
              let authentication = try? JSONDecoder().decode(LiveMemoryAuthentication.self, from: loginData),
              !authentication.token.isEmpty else {
            XCTFail("The isolated Juke backend did not authenticate the test account.")
            return
        }
        let base = origin.appending(path: "api/v1/vibe/", directoryHint: .isDirectory)
        app.launchEnvironment["VIBE_MEMORY_E2E_TOKEN"] = authentication.token
        app.launchEnvironment["VIBE_MEMORY_E2E_ACCOUNT_ID"] = credentials.accountID
        app.launchEnvironment["VIBE_MEMORY_E2E_BASE_URL"] = base.absoluteString
        launch(arguments: ["--uitesting-authenticated"])
        open("memories")

        let unique = String(UUID().uuidString.prefix(8))
        let memoryTitle = "Live memory \(unique)"
        let firstTag = "Rainy walks \(unique)"
        let reusedTag = "Our song \(unique)"
        let newMemory = app.buttons["memory.new"]
        XCTAssertTrue(newMemory.waitForExistence(timeout: 8))
        newMemory.click()
        app.buttons["memory.next"].click()
        let song = app.buttons["memory.addCurrentSong"]
        XCTAssertTrue(song.waitForExistence(timeout: 4))
        song.click()
        app.buttons["memory.next"].click()
        let body = element("memory.body")
        reveal(body, scrollDown: false)
        reveal(body)
        body.click(); body.typeText(memoryTitle + " #" + firstTag.replacingOccurrences(of: " ", with: "-"))
        app.buttons["memory.next"].click()
        XCTAssertTrue(app.buttons["memory.save"].waitForExistence(timeout: 12))
        app.buttons["memory.save"].click()
        XCTAssertTrue(app.buttons["memory.openSaved"].waitForExistence(timeout: 12))
        app.buttons["memory.openSaved"].click()
        XCTAssertTrue(element("memory.detail").waitForExistence(timeout: 4))
        let edit = app.buttons["memory.editTags"]
        reveal(edit)
        edit.click()
        let editor = element("memory.tagEditor")
        XCTAssertTrue(editor.waitForExistence(timeout: 3))
        editor.click(); editor.typeKey("a", modifierFlags: .command); editor.typeText(reusedTag)
        app.buttons["memory.saveTags"].click()
        XCTAssertTrue(app.staticTexts["#\(reusedTag)"].waitForExistence(timeout: 8))
        app.typeKey(.escape, modifierFlags: [])

        newMemory.click()
        app.buttons["memory.next"].click()
        app.buttons["memory.next"].click()
        XCTAssertTrue(element("memory.body").waitForExistence(timeout: 4))
        let secondTitle = "Another live memory \(unique)"
        let secondBody = element("memory.body")
        reveal(secondBody)
        secondBody.click(); secondBody.typeText(secondTitle)
        app.buttons["memory.next"].click()
        XCTAssertTrue(app.buttons["memory.tags"].waitForExistence(timeout: 12))
        app.buttons["memory.tags"].click()
        let reusable = app.buttons["memory.reuseTag.\(reusedTag)"]
        reveal(reusable)
        XCTAssertTrue(reusable.exists)
        reusable.click()
        app.buttons["memory.next"].click()
        XCTAssertTrue(app.buttons["memory.save"].waitForExistence(timeout: 12))
        app.buttons["memory.save"].click()
        XCTAssertTrue(app.buttons["memory.openSaved"].waitForExistence(timeout: 12))
        app.buttons["memory.openSaved"].click()
        XCTAssertTrue(element("memory.detail").waitForExistence(timeout: 12))

        var listRequest = URLRequest(url: base.appending(path: "memories/"))
        listRequest.setValue("Token \(authentication.token)", forHTTPHeaderField: "Authorization")
        let (data, response) = try await session.data(for: listRequest)
        XCTAssertEqual((response as? HTTPURLResponse)?.statusCode, 200)
        let persisted = try JSONDecoder().decode(LiveMemoryList.self, from: data).memories
        let first = try XCTUnwrap(persisted.first { $0.body.hasPrefix(memoryTitle) })
        XCTAssertTrue(first.body.hasPrefix(memoryTitle))
        XCTAssertEqual(first.place, "")
        XCTAssertEqual(first.people, [])
        XCTAssertEqual(first.tags, [reusedTag])
        XCTAssertEqual(first.songs.first?.title, "Blue in Green")
        XCTAssertNil(first.songs.first?.segmentStartSeconds)
        XCTAssertNil(first.songs.first?.segmentEndSeconds)
        XCTAssertEqual(first.classification.status, "unavailable")
        let second = try XCTUnwrap(persisted.first { $0.body == secondTitle })
        XCTAssertEqual(second.tags, [reusedTag])
    }

    private func reveal(_ target: XCUIElement, scrollDown: Bool = true) {
        for _ in 0..<12 {
            let canvas = app.scrollViews["memory.canvas.scroll"]
            let scroll = canvas.exists ? canvas : app.scrollViews.firstMatch
            guard scroll.exists else { return }
            var down = scrollDown
            if target.exists {
                let center = CGPoint(x: target.frame.midX, y: target.frame.midY)
                if target.isHittable && scroll.frame.insetBy(dx: 0, dy: 24).contains(center) { return }
                down = target.frame.midY > scroll.frame.midY
            }
            scroll.scroll(byDeltaX: 0, deltaY: down ? -150 : 150)
        }
    }

    private func launchAuthenticated(additionalArguments: [String] = []) {
        launch(arguments: ["--uitesting-authenticated"] + additionalArguments)
        if !additionalArguments.contains("--uitesting-show-privacy-welcome") {
            open("chat")
        }
    }

    /// Clicks a section in the header nav and waits for its screen.
    private func open(_ section: String) {
        let tab = app.buttons["nav.\(section)"]
        XCTAssertTrue(tab.waitForExistence(timeout: 4), section)
        tab.click()
        XCTAssertTrue(element("\(section).screen").waitForExistence(timeout: 3), section)
    }

    private func attachScreenshot(_ name: String) {
        Thread.sleep(forTimeInterval: 1.2) // let the stage and colour transitions settle
        let attachment = XCTAttachment(screenshot: app.windows.firstMatch.screenshot())
        attachment.name = name
        attachment.lifetime = .keepAlways
        add(attachment)
    }

    private func launch(arguments: [String] = []) {
        app.launchArguments = ["--uitesting"] + arguments
        app.launch()
    }

    private func element(_ identifier: String) -> XCUIElement {
        app.descendants(matching: .any)[identifier]
    }
}

private struct LiveMemoryCredentials: Decodable {
    let username: String
    let password: String
    let accountID: String
    let baseURL: String
}

private struct LiveMemoryLogin: Encodable {
    let login: String
    let password: String
}

private struct LiveMemoryAuthentication: Decodable { let token: String }

private struct LiveMemoryList: Decodable {
    struct Memory: Decodable {
        struct Song: Decodable {
            let title: String
            let segmentStartSeconds: Double?
            let segmentEndSeconds: Double?
        }
        struct Classification: Decodable { let status: String }
        let title: String
        let body: String
        let place: String
        let people: [String]
        let tags: [String]
        let songs: [Song]
        let classification: Classification
    }
    let memories: [Memory]
}
