import XCTest
import JukeKit
@testable import ShotClock

final class ShotClockTests: XCTestCase {
    private class MockURLProtocol: URLProtocol {
        static var requestHandler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

        override class func canInit(with request: URLRequest) -> Bool {
            true
        }

        override class func canonicalRequest(for request: URLRequest) -> URLRequest {
            request
        }

        override func startLoading() {
            guard let handler = Self.requestHandler else {
                XCTFail("Request handler not set")
                return
            }

            do {
                let (response, data) = try handler(request)
                client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
                client?.urlProtocol(self, didLoad: data)
                client?.urlProtocolDidFinishLoading(self)
            } catch {
                client?.urlProtocol(self, didFailWithError: error)
            }
        }

        override func stopLoading() {}
    }

    private var mockSession: URLSession!

    override func setUp() {
        super.setUp()
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockURLProtocol.self]
        mockSession = URLSession(configuration: config)
    }

    override func tearDown() {
        MockURLProtocol.requestHandler = nil
        mockSession = nil
        super.tearDown()
    }

    func testAPIClientBaseURL() {
        let config = JukeAPIConfiguration(baseURL: URL(string: "http://test.example.com")!)
        let client = JukeAPIClient(configuration: config)
        XCTAssertEqual(client.baseURL.absoluteString, "http://test.example.com")
    }

    func testUserProfilePreferredName_withDisplayName() {
        let profile = UserProfile(id: 1, username: "user1", displayName: "Display", bio: nil, avatarUrl: nil)
        XCTAssertEqual(profile.preferredName, "Display")
    }

    func testUserProfilePreferredName_withoutDisplayName() {
        let profile = UserProfile(id: 1, username: "user1", displayName: nil, bio: nil, avatarUrl: nil)
        XCTAssertEqual(profile.preferredName, "user1")
    }

    func testUserProfilePreferredName_emptyDisplayName() {
        let profile = UserProfile(id: 1, username: "user1", displayName: "", bio: nil, avatarUrl: nil)
        XCTAssertEqual(profile.preferredName, "user1")
    }

    func testLoginRequestEncoding() throws {
        let request = LoginRequest(username: "test", password: "pass123")
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(request)
        let dict = try JSONSerialization.jsonObject(with: data) as? [String: String]
        XCTAssertEqual(dict?["username"], "test")
        XCTAssertEqual(dict?["password"], "pass123")
    }

    func testRegisterRequestEncoding() throws {
        let request = RegisterRequest(username: "new", email: "a@b.com", password: "pass1234", passwordConfirm: "pass1234")
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(request)
        let dict = try JSONSerialization.jsonObject(with: data) as? [String: String]
        XCTAssertEqual(dict?["username"], "new")
        XCTAssertEqual(dict?["email"], "a@b.com")
        XCTAssertEqual(dict?["password_confirm"], "pass1234")
    }

    func testAppConfigurationEnvOverridesPlist() {
        let config = JukeAppConfiguration(
            environment: ["DISABLE_REGISTRATION": "yes"],
            plistValue: "false"
        )

        XCTAssertTrue(config.isRegistrationDisabled)
    }

    func testAppConfigurationPlistBooleanFallback() {
        let config = JukeAppConfiguration(
            environment: [:],
            plistValue: true
        )

        XCTAssertTrue(config.isRegistrationDisabled)
    }

    func testResolveBaseURLUsesEnvironment() {
        let config = JukeAPIConfiguration(
            environment: ["BACKEND_URL": "http://env.example.com"],
            backendPlist: "http://plist.example.com"
        )

        XCTAssertEqual(config.baseURL.absoluteString, "http://env.example.com")
    }

    func testResolveBaseURLUsesPlistWhenEnvironmentMissing() {
        let config = JukeAPIConfiguration(
            environment: [:],
            backendPlist: "http://plist.example.com"
        )

        XCTAssertEqual(config.baseURL.absoluteString, "http://plist.example.com")
    }

    @MainActor
    func testUpsertSession_insertsNewSessionAtTop() {
        let viewModel = HomeViewModel()
        let existing = makeSession(id: "existing")
        let created = makeSession(id: "created")
        viewModel.sessions = [existing]

        viewModel.upsertSession(created)

        XCTAssertEqual(viewModel.sessions.count, 2)
        XCTAssertEqual(viewModel.sessions.first?.id, "created")
    }

    @MainActor
    func testUpsertSession_replacesExistingSession() {
        let viewModel = HomeViewModel()
        let original = makeSession(id: "same-id", title: "Original")
        let updated = makeSession(id: "same-id", title: "Updated")
        viewModel.sessions = [original]

        viewModel.upsertSession(updated)

        XCTAssertEqual(viewModel.sessions.count, 1)
        XCTAssertEqual(viewModel.sessions.first?.title, "Updated")
    }

    @MainActor
    func testUpsertSession_removesEndedSession() {
        let viewModel = HomeViewModel()
        let existing = makeSession(id: "same-id", title: "Original")
        let ended = makeSession(id: "same-id", title: "Original", status: .ended)
        viewModel.sessions = [existing]

        viewModel.upsertSession(ended)

        XCTAssertTrue(viewModel.sessions.isEmpty)
    }

    func testVisibleSessions_filtersEndedSessions() {
        let active = makeSession(id: "active", status: .active)
        let ended = makeSession(id: "ended", status: .ended)
        let visible = HomeViewModel.visibleSessions(from: [active, ended])

        XCTAssertEqual(visible.count, 1)
        XCTAssertEqual(visible.first?.id, "active")
    }

    @MainActor
    func testCreateSessionViewModel_prefillsFromExistingSession() {
        let existing = PowerHourSession(
            id: "session-1",
            admin: 1,
            title: "Friday Night",
            inviteCode: "ABCDEFGH",
            tracksPerPlayer: 5,
            maxTracks: 42,
            secondsPerTrack: 75,
            transitionClip: "buzzer",
            hideTrackOwners: true,
            status: .lobby,
            currentTrackIndex: -1,
            createdAt: "2026-02-16T00:00:00Z",
            startedAt: nil,
            endedAt: nil,
            playerCount: 2,
            trackCount: 0
        )

        let viewModel = CreateSessionViewModel(session: existing)

        XCTAssertEqual(viewModel.title, "Friday Night")
        XCTAssertEqual(viewModel.tracksPerPlayer, 5)
        XCTAssertEqual(viewModel.maxTracks, 42)
        XCTAssertEqual(viewModel.secondsPerTrack, 75)
        XCTAssertEqual(viewModel.transitionClip, "buzzer")
        XCTAssertEqual(viewModel.hideTrackOwners, true)
    }

    @MainActor
    func testAddTracksViewModel_searchDebounceIsHalfSecond() {
        XCTAssertEqual(AddTracksViewModel.searchDebounceNanoseconds, 500_000_000)
    }

    @MainActor
    func testCreateSessionViewModel_updateSession_sendsPatchThenFetchesUpdatedSession() async {
        let patchExpectation = expectation(description: "PATCH update called")
        let getExpectation = expectation(description: "GET session called")
        let sessionID = "session-1"

        let sessionService = makeSessionService { [self] request in
            let normalizedPath = self.normalizedPath(request.url?.path)
            if request.httpMethod == "PATCH", normalizedPath == "/api/v1/powerhour/sessions/\(sessionID)" {
                patchExpectation.fulfill()
                let bodyData = try self.requestBodyData(from: request)
                let body = try XCTUnwrap(
                    JSONSerialization.jsonObject(with: bodyData) as? [String: Any]
                )
                XCTAssertEqual(body["title"] as? String, "Updated Session")
                XCTAssertEqual(body["tracks_per_player"] as? Int, 6)
                XCTAssertEqual(body["max_tracks"] as? Int, 45)
                XCTAssertEqual(body["seconds_per_track"] as? Int, 90)
                XCTAssertEqual(body["transition_clip"] as? String, "bell")
                XCTAssertEqual(body["hide_track_owners"] as? Bool, true)
                return (self.makeResponse(for: request, statusCode: 200), Data("{}".utf8))
            }

            if request.httpMethod == "GET", normalizedPath == "/api/v1/powerhour/sessions/\(sessionID)" {
                getExpectation.fulfill()
                return (
                    self.makeResponse(for: request, statusCode: 200),
                    self.makeSessionPayload(
                        id: sessionID,
                        title: "Updated Session",
                        status: .lobby,
                        tracksPerPlayer: 6,
                        maxTracks: 45,
                        secondsPerTrack: 90,
                        transitionClip: "bell",
                        hideTrackOwners: true
                    )
                )
            }

            XCTFail("Unexpected request: \(request.httpMethod ?? "nil") \(normalizedPath)")
            return (self.makeResponse(for: request, statusCode: 404), Data("{}".utf8))
        }

        let existing = makeSession(id: sessionID, title: "Original Session")
        let viewModel = CreateSessionViewModel(session: existing, sessionService: sessionService)
        viewModel.title = "  Updated Session  "
        viewModel.tracksPerPlayer = 6
        viewModel.maxTracks = 45
        viewModel.secondsPerTrack = 90
        viewModel.transitionClip = "bell"
        viewModel.hideTrackOwners = true

        let saved = await viewModel.updateSession(id: sessionID, token: "token-123")
        await fulfillment(of: [patchExpectation, getExpectation], timeout: 1.0)

        XCTAssertEqual(saved?.title, "Updated Session")
        XCTAssertEqual(saved?.tracksPerPlayer, 6)
        XCTAssertEqual(saved?.maxTracks, 45)
        XCTAssertEqual(saved?.secondsPerTrack, 90)
        XCTAssertEqual(saved?.transitionClip, "bell")
        XCTAssertEqual(saved?.hideTrackOwners, true)
        XCTAssertNil(viewModel.errorMessage)
    }

    @MainActor
    func testHomeViewModel_deleteSession_confirmationActionRemovesSession() async {
        let deleteExpectation = expectation(description: "DELETE session called")
        let sessionToDelete = "delete-me"

        let sessionService = makeSessionService { [self] request in
            XCTAssertEqual(request.httpMethod, "DELETE")
            XCTAssertEqual(
                self.normalizedPath(request.url?.path),
                "/api/v1/powerhour/sessions/\(sessionToDelete)"
            )
            deleteExpectation.fulfill()
            return (self.makeResponse(for: request, statusCode: 204), Data())
        }

        let viewModel = HomeViewModel(sessionService: sessionService)
        viewModel.sessions = [
            makeSession(id: "keep-me"),
            makeSession(id: sessionToDelete),
        ]

        let didDelete = await viewModel.deleteSession(id: sessionToDelete, token: "token-123")
        await fulfillment(of: [deleteExpectation], timeout: 1.0)

        XCTAssertTrue(didDelete)
        XCTAssertEqual(viewModel.sessions.map(\.id), ["keep-me"])
        XCTAssertNil(viewModel.errorMessage)
    }

    @MainActor
    func testPlaybackViewModel_endSession_confirmationActionAppliesEndedState() async {
        let endExpectation = expectation(description: "POST end session called")
        let sessionID = "session-1"

        let sessionService = makeSessionService { [self] request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(
                self.normalizedPath(request.url?.path),
                "/api/v1/powerhour/sessions/\(sessionID)/end"
            )
            endExpectation.fulfill()

            let response = """
            {
                "status": "ended",
                "current_track_index": 2,
                "started_at": "2026-02-16T00:00:00Z",
                "player_count": 2,
                "track_count": 5
            }
            """.data(using: .utf8)!

            return (self.makeResponse(for: request, statusCode: 200), response)
        }

        let viewModel = PlaybackViewModel(
            session: makeSession(id: sessionID, status: .active),
            tracks: [makeTrackItem(id: "track-1", order: 0)],
            sessionService: sessionService
        )

        await viewModel.endSession(token: "token-123")
        await fulfillment(of: [endExpectation], timeout: 1.0)

        XCTAssertTrue(viewModel.isEnded)
        XCTAssertEqual(viewModel.currentTrackIndex, 2)
        XCTAssertNil(viewModel.errorMessage)
    }

    func testPowerHourSessionDecodesSnakeCasePayload() throws {
        let json = """
        {
            "id": "session-1",
            "admin": 1,
            "title": "Friday Night",
            "invite_code": "ABCDEFGH",
            "tracks_per_player": 3,
            "max_tracks": 30,
            "seconds_per_track": 60,
            "transition_clip": "airhorn",
            "hide_track_owners": false,
            "status": "lobby",
            "current_track_index": -1,
            "created_at": "2026-02-16T00:00:00Z",
            "started_at": null,
            "ended_at": null,
            "player_count": 1,
            "track_count": 0
        }
        """.data(using: .utf8)!

        let decoder = JukeDateParsing.makeDecoder()
        let decoded = try decoder.decode(PowerHourSession.self, from: json)

        XCTAssertEqual(decoded.inviteCode, "ABCDEFGH")
        XCTAssertEqual(decoded.tracksPerPlayer, 3)
        XCTAssertEqual(decoded.playerCount, 1)
        XCTAssertEqual(decoded.trackCount, 0)
    }

    private func makeSession(
        id: String,
        title: String = "Session",
        status: SessionStatus = .lobby
    ) -> PowerHourSession {
        PowerHourSession(
            id: id,
            admin: 1,
            title: title,
            inviteCode: "ABCDEFGH",
            tracksPerPlayer: 3,
            maxTracks: 30,
            secondsPerTrack: 60,
            transitionClip: "airhorn",
            hideTrackOwners: false,
            status: status,
            currentTrackIndex: -1,
            createdAt: "2026-02-16T00:00:00Z",
            startedAt: nil,
            endedAt: nil,
            playerCount: 1,
            trackCount: 0
        )
    }

    private func makeTrackItem(id: String, order: Int) -> SessionTrackItem {
        SessionTrackItem(
            id: id,
            trackId: 1,
            order: order,
            startOffsetMs: 0,
            addedAt: "2026-02-16T00:00:00Z",
            trackName: "Track \(order)",
            trackArtist: "Artist",
            trackAlbum: "Album",
            durationMs: 180_000,
            spotifyId: "spotify-\(order)",
            previewUrl: nil,
            addedBy: 1,
            addedByUsername: "player1"
        )
    }

    private func makeSessionService(
        requestHandler: @escaping (URLRequest) throws -> (HTTPURLResponse, Data)
    ) -> SessionService {
        MockURLProtocol.requestHandler = requestHandler
        let apiConfig = JukeAPIConfiguration(baseURL: URL(string: "https://api.test.com")!)
        let client = JukeAPIClient(configuration: apiConfig, session: mockSession)
        return SessionService(api: client)
    }

    private func makeResponse(for request: URLRequest, statusCode: Int) -> HTTPURLResponse {
        HTTPURLResponse(
            url: request.url ?? URL(string: "https://api.test.com")!,
            statusCode: statusCode,
            httpVersion: nil,
            headerFields: nil
        )!
    }

    private func makeSessionPayload(
        id: String,
        title: String,
        status: SessionStatus,
        tracksPerPlayer: Int = 3,
        maxTracks: Int = 30,
        secondsPerTrack: Int = 60,
        transitionClip: String = "airhorn",
        hideTrackOwners: Bool = false
    ) -> Data {
        let json: [String: Any] = [
            "id": id,
            "admin": 1,
            "title": title,
            "invite_code": "ABCDEFGH",
            "tracks_per_player": tracksPerPlayer,
            "max_tracks": maxTracks,
            "seconds_per_track": secondsPerTrack,
            "transition_clip": transitionClip,
            "hide_track_owners": hideTrackOwners,
            "status": status.rawValue,
            "current_track_index": -1,
            "created_at": "2026-02-16T00:00:00Z",
            "started_at": NSNull(),
            "ended_at": NSNull(),
            "player_count": 1,
            "track_count": 0,
        ]
        return try! JSONSerialization.data(withJSONObject: json)
    }

    private func normalizedPath(_ path: String?) -> String {
        guard var path else { return "" }
        while path.count > 1 && path.hasSuffix("/") {
            path.removeLast()
        }
        return path
    }

    private func requestBodyData(from request: URLRequest) throws -> Data {
        if let body = request.httpBody {
            return body
        }

        guard let stream = request.httpBodyStream else {
            throw XCTSkip("Request body was not available on this URLRequest")
        }

        stream.open()
        defer { stream.close() }

        var data = Data()
        var buffer = [UInt8](repeating: 0, count: 1024)

        while stream.hasBytesAvailable {
            let read = stream.read(&buffer, maxLength: buffer.count)
            if read < 0 {
                throw stream.streamError ?? NSError(
                    domain: "ShotClockTests",
                    code: -1,
                    userInfo: [NSLocalizedDescriptionKey: "Failed to read request body stream."]
                )
            }
            if read == 0 {
                break
            }
            data.append(buffer, count: read)
        }

        return data
    }
}
