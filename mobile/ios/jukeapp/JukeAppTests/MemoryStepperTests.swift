import Foundation
import Testing
@testable import JukeApp

@MainActor @Suite struct MemoryStepperTests {
    private static let base = Date(timeIntervalSince1970: 1_700_000_000)

    /// A valid 22-character Spotify id for a one-letter memory title.
    private static func spotifyID(_ title: String) -> String { "0aWMVrwxPNYkKmFthzm00" + title }

    private static func memory(_ title: String, day: Int, songs: [MemorySong]? = nil) -> MusicMemory {
        let list = songs ?? [MemorySong(title: "\(title) song", artist: "Artist", provider: "spotify", providerID: Self.spotifyID(title))]
        return MusicMemory(id: UUID(), title: title, text: "", occurredAt: base.addingTimeInterval(Double(day) * 86_400), createdAt: base,
                           place: "", people: [], songs: list, media: [], tags: [], classification: .unavailable)
    }

    @Test func orderingIsByWhenItHappenedNotWhenItWasSaved() {
        let late = Self.memory("late", day: 9), early = Self.memory("early", day: 1), mid = Self.memory("mid", day: 5)
        #expect(MemoryChronology.ordered([late, early, mid]).map(\.title) == ["early", "mid", "late"])
    }

    @Test func nextAndPreviousSkipMemoriesWithNothingToPlay() {
        let a = Self.memory("a", day: 1), silent = Self.memory("silent", day: 2, songs: []), c = Self.memory("c", day: 3)
        let all = [c, silent, a]
        #expect(MemoryChronology.step(from: a.id, direction: 1, in: all)?.title == "c")
        #expect(MemoryChronology.step(from: c.id, direction: -1, in: all)?.title == "a")
        #expect(MemoryChronology.step(from: c.id, direction: 1, in: all) == nil, "no wrap past the latest")
        #expect(MemoryChronology.step(from: a.id, direction: -1, in: all) == nil)
        #expect(MemoryChronology.step(from: UUID(), direction: 1, in: all) == nil, "a deleted memory has no place in the order")
    }

    @Test func aMemorySongIsMatchedToWhatIsPlayingById() {
        let song = MemorySong(title: "Blue in Green", artist: "Miles", provider: "spotify", providerID: "t1")
        func track(_ id: String, _ title: String) -> NowPlayingTrack {
            NowPlayingTrack(id: id, title: title, artist: "x", album: nil, artworkURL: nil, localArtwork: nil, source: "Spotify")
        }
        #expect(MemoryStepper.matches(song, track("t1", "Other")))
        #expect(MemoryStepper.matches(song, track("zzz", " blue in green ")))
        #expect(!MemoryStepper.matches(song, track("zzz", "So What")))
    }

    private final class Spotify: MemorySpotifyPlaying, @unchecked Sendable {
        var played: [String] = []
        func play(token: String, spotifyID: String, startSeconds: Double) async throws -> JukePlaybackState? { played.append(spotifyID); return nil }
        func state(token: String) async throws -> JukePlaybackState? { nil }
        func pause(token: String, deviceID: String?) async throws -> JukePlaybackState? { nil }
    }

    private struct Rig {
        let player: MemoryPlayer, spotify: Spotify, stepper: MemoryStepper
        let a: MusicMemory, b: MusicMemory, c: MusicMemory
        let clock: Clock
    }
    @MainActor private final class Clock { var now = Date(); var track: NowPlayingTrack? }

    private func rig() -> Rig {
        let a = Self.memory("a", day: 1), b = Self.memory("b", day: 2), c = Self.memory("c", day: 3)
        let spotify = Spotify(), clock = Clock()
        let player = MemoryPlayer(spotify: spotify, token: { "t" }, marked: { _ in }, sleep: { _ in await Task.yield() })
        let stepper = MemoryStepper(player: player, memories: { [c, a, b] }, track: { clock.track }, now: { clock.now })
        return Rig(player: player, spotify: spotify, stepper: stepper, a: a, b: b, c: c, clock: clock)
    }

    @Test func nothingIsActiveUntilAMemorySongIsPlayed() async {
        let rig = rig()
        #expect(!rig.stepper.isActive)
        #expect(await rig.stepper.step(1) == false)
    }

    @Test func nextPlaysTheFollowingMemoryAndPreviousGoesBack() async {
        let rig = rig()
        await rig.player.play(rig.a.songs[0], in: rig.a.id)
        #expect(rig.stepper.isActive)
        #expect(await rig.stepper.step(1))
        #expect(rig.spotify.played == [Self.spotifyID("a"), Self.spotifyID("b")])
        #expect(await rig.stepper.step(1))
        #expect(rig.spotify.played.last == Self.spotifyID("c"))
        #expect(await rig.stepper.step(1) == false, "c is the latest memory")
        #expect(await rig.stepper.step(-1))
        #expect(rig.spotify.played.last == Self.spotifyID("b"))
    }

    @Test func stopsBeingActiveOnceSomethingElseIsPlaying() async {
        let rig = rig()
        await rig.player.play(rig.a.songs[0], in: rig.a.id)
        rig.clock.now = rig.clock.now.addingTimeInterval(60)
        rig.clock.track = NowPlayingTrack(id: "someone-else", title: "Another Song", artist: "x", album: nil, artworkURL: nil, localArtwork: nil, source: "Spotify")
        #expect(!rig.stepper.isActive, "Next should go to Spotify's queue again")
        rig.clock.track = NowPlayingTrack(id: Self.spotifyID("a"), title: "a song", artist: "x", album: nil, artworkURL: nil, localArtwork: nil, source: "Spotify")
        #expect(rig.stepper.isActive)
    }

    @Test func staysActiveWhileTheObserverStillReportsTheOldSong() async {
        let rig = rig()
        rig.clock.track = NowPlayingTrack(id: "old", title: "Old", artist: "x", album: nil, artworkURL: nil, localArtwork: nil, source: "Spotify")
        await rig.player.play(rig.a.songs[0], in: rig.a.id)
        #expect(rig.stepper.isActive, "inside the start grace a quick second press must not leak to Spotify")
    }

    @Test func signingOutForgetsTheMemory() async {
        let rig = rig()
        await rig.player.play(rig.a.songs[0], in: rig.a.id)
        rig.player.reset()
        #expect(!rig.stepper.isActive)
    }

    @Test func aMemoryDeletedWhilePlayingIsNoLongerSteppedFrom() async {
        let a = Self.memory("a", day: 1)
        var list = [a]
        let player = MemoryPlayer(spotify: Spotify(), token: { "t" }, marked: { _ in }, sleep: { _ in await Task.yield() })
        let stepper = MemoryStepper(player: player, memories: { list }, track: { nil })
        await player.play(a.songs[0], in: a.id)
        list = []
        #expect(!stepper.isActive)
    }
}
