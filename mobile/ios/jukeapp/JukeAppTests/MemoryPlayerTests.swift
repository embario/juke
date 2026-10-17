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

    @Test func aSecondPlayWhileStartingDoesNotDropTheFirstEndTimer() async {
        final class Slow: MemorySpotifyPlaying, @unchecked Sendable {
            let inner: FakeSpotify
            var release: CheckedContinuation<Void, Never>?
            init(_ inner: FakeSpotify) { self.inner = inner }
            func play(token: String, spotifyID: String, startSeconds: Double) async throws -> JukePlaybackState? {
                await withCheckedContinuation { release = $0 }
                return try await inner.play(token: token, spotifyID: spotifyID, startSeconds: startSeconds)
            }
            func state(token: String) async throws -> JukePlaybackState? { try await inner.state(token: token) }
            func pause(token: String, deviceID: String?) async throws -> JukePlaybackState? { try await inner.pause(token: token, deviceID: deviceID) }
        }
        let fake = FakeSpotify(trackID: spotifyID)
        let slow = Slow(fake)
        let player = MemoryPlayer(spotify: slow, token: { "t" }, sleep: { _ in await Task.yield() })
        let first = Task { await player.play(song()) }
        for _ in 0..<50 where slow.release == nil { try? await Task.sleep(for: .milliseconds(10)) }
        await player.play(song())   // ignored: still starting
        slow.release?.resume()
        await first.value
        for _ in 0..<50 where fake.paused == 0 { try? await Task.sleep(for: .milliseconds(20)) }
        #expect(fake.paused == 1)
    }

    @Test func appleTimingStopsWhenTheSongChangesOrStops() {
        let library = AppleSegmentGuard(id: "00000000000000AB", endSeconds: 70)
        let ok = AppleMusicSnapshot(libraryID: "00000000000000ab", storeID: nil, isPlaying: true, time: 20)
        #expect(library.decision(ok) == .keepWaiting)
        #expect(library.decision(.init(libraryID: "00000000000000ab", storeID: nil, isPlaying: true, time: 70)) == .pause)
        #expect(library.decision(.init(libraryID: "00000000000000CD", storeID: nil, isPlaying: true, time: 70)) == .cancel)
        #expect(library.decision(.init(libraryID: "00000000000000ab", storeID: nil, isPlaying: false, time: 70)) == .cancel)
        #expect(library.decision(nil) == .cancel)
        let catalog = AppleSegmentGuard(id: "1234567", endSeconds: 70)
        #expect(catalog.decision(.init(libraryID: nil, storeID: "1234567", isPlaying: true, time: 71)) == .pause)
        #expect(catalog.decision(.init(libraryID: nil, storeID: "999", isPlaying: true, time: 71)) == .cancel)
    }
}
