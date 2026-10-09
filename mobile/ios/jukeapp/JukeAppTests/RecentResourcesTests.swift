import Foundation
import Testing
@testable import JukeApp

@Suite struct RecentResourcesTests {
    private func item(_ kind: Radio.SeedKind, _ id: String, _ title: String? = nil) -> Radio.CrateItem {
        Radio.CrateItem(id: Radio.ID("raw-\(id)"), kind: kind, spotifyId: id, title: title ?? id, subtitle: nil, artworkUrl: nil, track: nil)
    }

    private func ids(_ items: [Radio.CrateItem]) -> [String] { items.map(\.spotifyId) }

    @Test func recordPutsTheNewestFirst() {
        var recents: [Radio.CrateItem] = []
        for id in ["a", "b", "c"] { recents = RecentLibrary.record(item(.artist, id), into: recents) }
        #expect(ids(recents) == ["c", "b", "a"])
    }

    @Test func recordingAResourceAgainMovesItUpWithoutDuplicating() {
        var recents: [Radio.CrateItem] = []
        for id in ["a", "b", "c"] { recents = RecentLibrary.record(item(.artist, id), into: recents) }
        recents = RecentLibrary.record(item(.artist, "a", "A (again)"), into: recents)
        #expect(ids(recents) == ["a", "c", "b"])
        #expect(recents.first?.title == "A (again)", "the latest details replace the old entry")
    }

    @Test func recordingAgainWithoutDetailsKeepsTheEarlierArtworkAndSubtitle() {
        let withArt = Radio.CrateItem(id: "1", kind: .album, spotifyId: "alb", title: "Kind of Blue", subtitle: "Miles Davis", artworkUrl: "https://i.example/a.jpg", track: nil)
        let bare = Radio.CrateItem(id: "2", kind: .album, spotifyId: "alb", title: "Kind of Blue", subtitle: nil, artworkUrl: nil, track: nil)
        let recents = RecentLibrary.record(bare, into: RecentLibrary.record(withArt, into: []))
        #expect(recents.count == 1)
        #expect(recents.first?.artworkUrl == "https://i.example/a.jpg" && recents.first?.subtitle == "Miles Davis")
        let newer = Radio.CrateItem(id: "3", kind: .album, spotifyId: "alb", title: "Kind of Blue", subtitle: nil, artworkUrl: "https://i.example/b.jpg", track: nil)
        #expect(RecentLibrary.record(newer, into: recents).first?.artworkUrl == "https://i.example/b.jpg", "new artwork replaces the old")
    }

    @Test func theSameIDInAnotherKindIsAnotherResource() {
        var recents = RecentLibrary.record(item(.artist, "x"), into: [])
        recents = RecentLibrary.record(item(.album, "x"), into: recents)
        #expect(recents.count == 2)
    }

    @Test func resourcesWithoutASpotifyIDAreNotRecorded() {
        #expect(RecentLibrary.record(item(.artist, ""), into: []).isEmpty)
    }

    @Test func eachKindKeepsAtMostTwentyAndDropsTheOldest() {
        var recents: [Radio.CrateItem] = []
        for index in 1...25 { recents = RecentLibrary.record(item(.track, "t\(index)"), into: recents) }
        recents = RecentLibrary.record(item(.artist, "only-artist"), into: recents)
        let tracks = recents.filter { $0.kind == .track }
        #expect(tracks.count == RecentLibrary.cap)
        #expect(tracks.first?.spotifyId == "t25" && tracks.last?.spotifyId == "t6")
        #expect(recents.contains { $0.spotifyId == "only-artist" }, "another kind's history is untouched")
    }

    @Test func libraryShowsOnlyTheSelectedKindMostRecentFirst() {
        var recents: [Radio.CrateItem] = []
        for entry in [(Radio.SeedKind.artist, "a1"), (.album, "b1"), (.artist, "a2")] { recents = RecentLibrary.record(item(entry.0, entry.1), into: recents) }
        let fill = (1...12).map { item(.artist, "f\($0)") }
        let shown = RecentLibrary.library(kind: .artist, recents: recents, fill: fill)
        #expect(ids(shown).prefix(2) == ["a2", "a1"])
        #expect(!ids(shown).contains("b1"))
    }

    @Test func shortHistoryIsFilledFromRecommendationsUpToTen() {
        let recents = RecentLibrary.record(item(.artist, "a1"), into: [])
        let fill = (1...30).map { item(.artist, "f\($0)") }
        let shown = RecentLibrary.library(kind: .artist, recents: recents, fill: fill)
        #expect(shown.count == RecentLibrary.minimum)
        #expect(ids(shown) == ["a1"] + (1...9).map { "f\($0)" })
    }

    @Test func aRecommendationAlreadyInTheHistoryIsNotShownTwice() {
        let recents = RecentLibrary.record(item(.artist, "f2"), into: [])
        let fill = (1...30).map { item(.artist, "f\($0)") }
        let shown = RecentLibrary.library(kind: .artist, recents: recents, fill: fill)
        #expect(Set(ids(shown)).count == shown.count)
        #expect(shown.first?.spotifyId == "f2" && shown.count == RecentLibrary.minimum)
    }

    @Test func aLongHistoryIsNotPaddedAndNeverExceedsTwenty() {
        var recents: [Radio.CrateItem] = []
        for index in 1...30 { recents = RecentLibrary.record(item(.album, "r\(index)"), into: recents) }
        let shown = RecentLibrary.library(kind: .album, recents: recents, fill: (1...30).map { item(.album, "f\($0)") })
        #expect(shown.count == RecentLibrary.cap)
        #expect(!ids(shown).contains { $0.hasPrefix("f") })
    }

    @Test func withoutAnyHistoryTheRecommendationsStandInAndWithoutBothItIsEmpty() {
        let fill = (1...4).map { item(.track, "f\($0)") }
        #expect(ids(RecentLibrary.library(kind: .track, recents: [], fill: fill)) == ["f1", "f2", "f3", "f4"])
        #expect(RecentLibrary.library(kind: .track, recents: [], fill: []).isEmpty)
    }

    @Test func rowsKeepTheSameIdentityWhetherTheyComeFromHistoryOrTheFill() {
        let fromFill = RecentLibrary.library(kind: .artist, recents: [], fill: [item(.artist, "x")])
        let fromHistory = RecentLibrary.library(kind: .artist, recents: [item(.artist, "x")], fill: [])
        #expect(fromFill.first?.id == fromHistory.first?.id)
    }

    @MainActor @Test func theStoreKeepsHistoryPerAccountAcrossLaunches() throws {
        let suite = "juke.tests.recents.\(UUID().uuidString)"
        let defaults = try #require(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let first = RecentResources(defaults: defaults)
        first.record(kind: .artist, spotifyID: "a", title: "A")   // no account yet: nothing is kept
        #expect(first.items.isEmpty)
        first.use(accountID: "1")
        first.record(kind: .artist, spotifyID: "a", title: "A")
        first.record(kind: .album, spotifyID: "b", title: "B", subtitle: "Artist")

        let relaunched = RecentResources(defaults: defaults)
        relaunched.use(accountID: "1")
        #expect(ids(relaunched.items) == ["b", "a"])
        relaunched.use(accountID: "2")
        #expect(relaunched.items.isEmpty, "another account does not see this history")
        relaunched.use(accountID: nil)
        #expect(relaunched.items.isEmpty)
    }

    @MainActor @Test func aPlayedTrackIsRecordedWithItsArtist() {
        let defaults = UserDefaults(suiteName: "juke.tests.recents.track")!
        defer { defaults.removePersistentDomain(forName: "juke.tests.recents.track") }
        let store = RecentResources(defaults: defaults)
        store.use(accountID: "1")
        store.record(track: Radio.Track(spotifyId: "t1", uri: "spotify:track:t1", title: "So What", artist: "Miles Davis", artistId: nil, album: nil, albumId: nil, artworkUrl: "https://i.example/a.jpg", durationMs: 1))
        #expect(store.items.first?.kind == .track && store.items.first?.subtitle == "Miles Davis")
        #expect(store.items.first?.artworkUrl == "https://i.example/a.jpg")
    }
}
