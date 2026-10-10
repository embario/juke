import XCTest
@testable import Juke

final class MemoryPlaybackTests: XCTestCase {
    private let spotifyID = "0aWMVrwxPNYkKmFthzmpRi"

    func testSpotifyURLResolvesToCanonicalTrackReference() throws {
        let request = try MemoryPlaybackRequest(
            provider: "Spotify", providerID: nil,
            playbackURL: URL(string: "https://open.spotify.com/track/\(spotifyID)?si=shared"),
            startSeconds: 42, endSeconds: 58
        )
        XCTAssertEqual(request.providerID, spotifyID)
        XCTAssertEqual(request.playbackURL?.absoluteString, "spotify:track:\(spotifyID)")
        XCTAssertEqual(request.startSeconds, 42)
        XCTAssertEqual(request.endSeconds, 58)
    }

    func testUntrustedAndNonTrackURLsAreRejectedEvenWithValidID() {
        for url in [
            "https://open.spotify.com.evil.test/track/\(spotifyID)",
            "https://attacker@open.spotify.com/track/\(spotifyID)",
            "https://open.spotify.com:8443/track/\(spotifyID)",
            "https://open.spotify.com/album/\(spotifyID)",
            "spotify:artist:\(spotifyID)",
            "file:///tmp/song", "javascript:alert(1)"
        ] {
            XCTAssertThrowsError(try MemoryPlaybackRequest(provider: "spotify", providerID: spotifyID,
                playbackURL: URL(string: url), startSeconds: nil, endSeconds: nil), url)
        }
    }

    func testMismatchedSpotifyIDAndURLAreRejected() {
        XCTAssertThrowsError(try MemoryPlaybackRequest(provider: "spotify", providerID: spotifyID,
            playbackURL: URL(string: "spotify:track:4uLU6hMCjMI75M1A2tKUQC"), startSeconds: nil, endSeconds: nil))
    }

    func testAppleLibraryPersistentIDCanPlayWithoutWebURL() throws {
        let request = try MemoryPlaybackRequest(provider: "apple_music", providerID: "0123456789ABCDEF",
            playbackURL: nil, startSeconds: nil, endSeconds: nil)
        XCTAssertEqual(request.providerID, "0123456789ABCDEF")
        XCTAssertEqual(request.startSeconds, 0)
        XCTAssertNil(request.playbackURL)
    }

    func testAppleCatalogIDProvidesHonestHandoffURL() throws {
        let request = try MemoryPlaybackRequest(provider: "Apple Music", providerID: "1234567890",
            playbackURL: nil, startSeconds: nil, endSeconds: nil)
        XCTAssertEqual(request.playbackURL?.absoluteString, "https://music.apple.com/song/1234567890")
        XCTAssertFalse(MemoryPlaybackRequest.isAppleLibraryID(request.providerID!))
    }

    func testAppleScriptInjectionAndUntrustedURLsAreRejected() {
        XCTAssertThrowsError(try MemoryPlaybackRequest(provider: "apple_music", providerID: "\" & do shell script \"touch /tmp/test",
            playbackURL: nil, startSeconds: nil, endSeconds: nil))
        XCTAssertThrowsError(try MemoryPlaybackRequest(provider: "apple_music", providerID: nil,
            playbackURL: URL(string: "https://music.apple.com.evil.test/song/123"), startSeconds: nil, endSeconds: nil))
    }

    func testSegmentsRejectNegativeNonFiniteAndReversedBounds() {
        for (start, end) in [(-1.0, 20.0), (.nan, 20), (.infinity, 30), (10, 10), (10, 9), (0, .infinity), (0, .nan)] {
            XCTAssertThrowsError(try MemoryPlaybackRequest(provider: "spotify", providerID: spotifyID,
                playbackURL: nil, startSeconds: start, endSeconds: end))
        }
    }

    func testSegmentWaitsUntilObservedPositionReachesEnd() {
        let segment = MemorySegmentGuard(trackID: spotifyID, deviceID: "mac", endSeconds: 58)
        XCTAssertEqual(segment.decision(trackID: spotifyID, deviceID: "mac", isPlaying: true, position: 57.9), .keepWaiting)
        XCTAssertEqual(segment.decision(trackID: spotifyID, deviceID: "mac", isPlaying: true, position: 58), .pause)
    }

    func testSegmentNeverPausesAnotherSongDeviceOrPausedPlayback() {
        let segment = MemorySegmentGuard(trackID: spotifyID, deviceID: "mac", endSeconds: 58)
        XCTAssertEqual(segment.decision(trackID: "other", deviceID: "mac", isPlaying: true, position: 80), .cancel)
        XCTAssertEqual(segment.decision(trackID: spotifyID, deviceID: "phone", isPlaying: true, position: 80), .cancel)
        XCTAssertEqual(segment.decision(trackID: spotifyID, deviceID: nil, isPlaying: true, position: 80), .cancel)
        XCTAssertEqual(segment.decision(trackID: spotifyID, deviceID: "mac", isPlaying: false, position: 80), .cancel)
        XCTAssertEqual(segment.decision(trackID: spotifyID, deviceID: "mac", isPlaying: true, position: .nan), .cancel)
    }
}
