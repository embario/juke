import XCTest
@testable import JukeKit

final class JukeMusicProfileTests: XCTestCase {

    // MARK: - Decoding Tests

    func testBasicDecoding() throws {
        let json = """
        {
            "id": 1,
            "username": "testuser",
            "is_owner": true
        }
        """.data(using: .utf8)!

        let decoder = JukeDateParsing.makeDecoder()
        let profile = try decoder.decode(JukeMusicProfile.self, from: json)

        XCTAssertEqual(profile.id, 1)
        XCTAssertEqual(profile.username, "testuser")
        XCTAssertTrue(profile.isOwner)
        XCTAssertEqual(profile.favoriteGenres, [])
    }

    func testFullDecoding() throws {
        let json = """
        {
            "id": 42,
            "username": "musicfan",
            "name": "Music Fan",
            "display_name": "The Music Fan",
            "tagline": "Living for the beat",
            "bio": "I love all kinds of music",
            "location": "NYC",
            "avatar_url": "https://example.com/avatar.jpg",
            "favorite_genres": ["rock", "jazz"],
            "favorite_artists": ["Artist1", "Artist2"],
            "favorite_albums": ["Album1"],
            "favorite_tracks": ["Track1", "Track2", "Track3"],
            "is_owner": false
        }
        """.data(using: .utf8)!

        let decoder = JukeDateParsing.makeDecoder()
        let profile = try decoder.decode(JukeMusicProfile.self, from: json)

        XCTAssertEqual(profile.id, 42)
        XCTAssertEqual(profile.username, "musicfan")
        XCTAssertEqual(profile.name, "Music Fan")
        XCTAssertEqual(profile.displayName, "The Music Fan")
        XCTAssertEqual(profile.tagline, "Living for the beat")
        XCTAssertEqual(profile.bio, "I love all kinds of music")
        XCTAssertEqual(profile.location, "NYC")
        XCTAssertEqual(profile.avatarURL?.absoluteString, "https://example.com/avatar.jpg")
        XCTAssertEqual(profile.favoriteGenres, ["rock", "jazz"])
        XCTAssertEqual(profile.favoriteArtists, ["Artist1", "Artist2"])
        XCTAssertEqual(profile.favoriteAlbums, ["Album1"])
        XCTAssertEqual(profile.favoriteTracks, ["Track1", "Track2", "Track3"])
        XCTAssertFalse(profile.isOwner)
    }

    func testAvatarURLSanitization() throws {
        let json = """
        {
            "id": 1,
            "username": "testuser",
            "avatar_url": "  https://example.com/avatar.jpg  ",
            "is_owner": false
        }
        """.data(using: .utf8)!

        let decoder = JukeDateParsing.makeDecoder()
        let profile = try decoder.decode(JukeMusicProfile.self, from: json)

        XCTAssertEqual(profile.avatarURL?.absoluteString, "https://example.com/avatar.jpg")
    }

    func testEmptyAvatarURL() throws {
        let json = """
        {
            "id": 1,
            "username": "testuser",
            "avatar_url": "   ",
            "is_owner": false
        }
        """.data(using: .utf8)!

        let decoder = JukeDateParsing.makeDecoder()
        let profile = try decoder.decode(JukeMusicProfile.self, from: json)

        XCTAssertNil(profile.avatarURL)
    }

    // MARK: - Preferred Name Tests

    func testPreferredNameWithDisplayName() {
        let profile = JukeMusicProfile(
            id: 1,
            username: "user",
            name: "Real Name",
            displayName: "Display Name"
        )
        XCTAssertEqual(profile.preferredName, "Display Name")
    }

    func testPreferredNameWithName() {
        let profile = JukeMusicProfile(
            id: 1,
            username: "user",
            name: "Real Name",
            displayName: nil
        )
        XCTAssertEqual(profile.preferredName, "Real Name")
    }

    func testPreferredNameFallsBackToUsername() {
        let profile = JukeMusicProfile(
            id: 1,
            username: "user",
            name: nil,
            displayName: nil
        )
        XCTAssertEqual(profile.preferredName, "user")
    }

    func testPreferredNameIgnoresEmptyDisplayName() {
        let profile = JukeMusicProfile(
            id: 1,
            username: "user",
            name: "Real Name",
            displayName: ""
        )
        XCTAssertEqual(profile.preferredName, "Real Name")
    }

    // MARK: - Profile Summary Tests

    func testProfileSummaryDecoding() throws {
        let json = """
        {
            "username": "testuser",
            "display_name": "Test User",
            "tagline": "Hello world",
            "avatar_url": "https://example.com/avatar.jpg"
        }
        """.data(using: .utf8)!

        let summary = try JSONDecoder().decode(JukeMusicProfileSummary.self, from: json)

        XCTAssertEqual(summary.username, "testuser")
        XCTAssertEqual(summary.displayName, "Test User")
        XCTAssertEqual(summary.tagline, "Hello world")
        XCTAssertEqual(summary.avatarURL?.absoluteString, "https://example.com/avatar.jpg")
        XCTAssertEqual(summary.id, "testuser")
    }

    func testProfileSummaryPreferredName() {
        let withDisplayName = JukeMusicProfileSummary(
            username: "user",
            displayName: "Display"
        )
        XCTAssertEqual(withDisplayName.preferredName, "Display")

        let withoutDisplayName = JukeMusicProfileSummary(
            username: "user",
            displayName: nil
        )
        XCTAssertEqual(withoutDisplayName.preferredName, "user")
    }
}
