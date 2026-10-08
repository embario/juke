import Foundation
import Testing
@testable import JukeApp

@MainActor @Suite struct MemoryPlayerTests {
    private final class FakeSpotify: MemorySpotifyPlaying, @unchecked Sendable {
        var played: [(String, Double)] = []
        var paused = 0
        var positionMs = 0
        var failPlay = false
        let trackID: String
        init(trackID: String) { self.trackID = trackID }

        private func snapshot() -> JukePlaybackState {
            JukePlaybackState(provider: "spotify", isPlaying: true, progressMs: positionMs,
                              track: .init(id: trackID, uri: nil, name: "Blue in Green", durationMs: nil, artworkURL: nil, album: nil, artists: nil),
                              device: .init(id: "dev", name: "Phone", type: "Smartphone"))
        }
        func play(token: String, spotifyID: String, startSeconds: Double) async throws -> JukePlaybackState? {
            if failPlay { throw PlaybackClientError.unavailable(404) }
            played.append((spotifyID, startSeconds)); return snapshot()
        }
        func state(token: String) async throws -> JukePlaybackState? { positionMs += 40_000; return snapshot() }
        func pause(token: String, deviceID: String?) async throws -> JukePlaybackState? { paused += 1; return nil }
    }

    private let spotifyID = "0aWMVrwxPNYkKmFthzmpRi"

    private func song(start: Double? = 30, end: Double? = 70) -> MemorySong {
        var song = MemorySong(title: "Blue in Green", artist: "Miles Davis", provider: "spotify", providerID: spotifyID)
        song.startSeconds = start; song.endSeconds = end
        return song
    }

    @Test func playsFromTheSavedMomentAndPausesAtItsEnd() async {
        let spotify = FakeSpotify(trackID: spotifyID)
        var mark: MemoryPlaybackMark?
        let player = MemoryPlayer(spotify: spotify, token: { "t" }, marked: { mark = $0 }, sleep: { _ in await Task.yield() })
        await player.play(song())
        #expect(spotify.played.first?.0 == spotifyID)
        #expect(spotify.played.first?.1 == 30)
        #expect(mark?.providerID == spotifyID)
        for _ in 0..<50 where spotify.paused == 0 { try? await Task.sleep(for: .milliseconds(20)) }
        #expect(spotify.paused == 1)
    }

    @Test func spotifyFailureHandsTheSongToSpotify() async {
        let spotify = FakeSpotify(trackID: spotifyID)
        spotify.failPlay = true
        var opened: URL?
        let player = MemoryPlayer(spotify: spotify, token: { "t" }, marked: { _ in }, open: { opened = $0 })
        await player.play(song(start: nil, end: nil))
        #expect(opened?.absoluteString == "spotify:track:\(spotifyID)")
        #expect(player.message != nil)
    }

    @Test func signedOutHandsOffWithoutCallingSpotify() async {
        let spotify = FakeSpotify(trackID: spotifyID)
        var opened: URL?
        let player = MemoryPlayer(spotify: spotify, token: { nil }, marked: { _ in }, open: { opened = $0 })
        await player.play(song())
        #expect(spotify.played.isEmpty)
        #expect(opened != nil)
    }

    @Test func invalidSongsAreRejected() async {
        let player = MemoryPlayer(spotify: FakeSpotify(trackID: spotifyID), token: { "t" }, marked: { _ in })
        await player.play(MemorySong(title: "x", artist: "y", provider: "manual"))
        #expect(player.message != nil)
    }
}
