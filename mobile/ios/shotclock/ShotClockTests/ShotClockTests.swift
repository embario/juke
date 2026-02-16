import XCTest
import JukeKit
@testable import ShotClock

final class ShotClockTests: XCTestCase {

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
}
