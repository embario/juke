import Foundation
import Testing
@testable import JukeApp

@MainActor @Suite struct DetailRevealTests {
    private typealias Gesture = DetailRevealGesture

    // MARK: The pull-down

    @Test func detailsFollowTheFingerDown() {
        #expect(Gesture.progress(revealed: false, translation: 100, travel: 400) == 0.25)
        #expect(Gesture.progress(revealed: false, translation: 200, travel: 400) == 0.5)
    }

    @Test func progressNeverLeavesZeroToOne() {
        #expect(Gesture.progress(revealed: false, translation: 900, travel: 400) == 1)
        #expect(Gesture.progress(revealed: false, translation: -50, travel: 400) == 0, "an upward drag cannot reveal")
        #expect(Gesture.progress(revealed: true, translation: 50, travel: 400) == 1, "pulling further down does nothing")
        #expect(Gesture.progress(revealed: true, translation: -900, travel: 400) == 0)
    }

    @Test func detailsFollowTheFingerBackUp() {
        #expect(Gesture.progress(revealed: true, translation: -100, travel: 400) == 0.75)
    }

    @Test func noTravelDoesNotDivideByZero() {
        #expect(Gesture.progress(revealed: false, translation: 80, travel: 0) == 0)
        #expect(Gesture.progress(revealed: true, translation: -80, travel: 0) == 1)
    }

    // MARK: Letting go

    @Test func aSlowDragPastTheCommitPointKeepsTheDetails() {
        #expect(Gesture.settles(revealed: false, translation: 200, velocity: 10, travel: 400))
    }

    @Test func aShortSlowDragIsCancelled() {
        #expect(!Gesture.settles(revealed: false, translation: 80, velocity: 10, travel: 400), "20% of the way goes back")
    }

    @Test func draggingBackToTheStartCancelsTheGesture() {
        #expect(!Gesture.settles(revealed: false, translation: 0, velocity: 0, travel: 400))
        #expect(Gesture.settles(revealed: true, translation: 0, velocity: 0, travel: 400))
    }

    @Test func aQuickFlickDecidesByItsDirection() {
        #expect(Gesture.settles(revealed: false, translation: 30, velocity: 900, travel: 400), "a short flick down reveals")
        #expect(!Gesture.settles(revealed: true, translation: -30, velocity: -900, travel: 400), "a short flick up returns")
        #expect(!Gesture.settles(revealed: false, translation: 200, velocity: -900, travel: 400), "a flick back up cancels a long drag")
    }

    @Test func aSmallPushUpLeavesTheDetailsShown() {
        #expect(Gesture.settles(revealed: true, translation: -60, velocity: -20, travel: 400))
        #expect(!Gesture.settles(revealed: true, translation: -300, velocity: -20, travel: 400), "a long push up returns to the pane")
    }

    @Test func onlyMostlyVerticalDragsCount() {
        #expect(Gesture.isVertical(CGSize(width: 10, height: 40)))
        #expect(!Gesture.isVertical(CGSize(width: 40, height: 10)))
        #expect(!Gesture.isVertical(CGSize(width: 20, height: 20)))
    }

    // MARK: Routes and what the panes say

    private nonisolated static func track(artistID: String?, albumID: String?, album: String? = "Kind of Blue") -> Radio.Track {
        Radio.Track(spotifyId: "t", uri: "spotify:track:t", title: "So What", artist: "Miles Davis", artistId: artistID,
                    album: album, albumId: albumID, artworkUrl: nil, durationMs: 1000)
    }

    @Test func radioSongsOpenTheirArtistAndAlbum() {
        let song = Self.track(artistID: "artist1", albumID: "album1")
        #expect(DetailRoute.artist(of: song) == .artist(title: "Miles Davis", spotifyID: "artist1"))
        #expect(DetailRoute.album(of: song) == .album(title: "Kind of Blue", spotifyID: "album1", artist: "Miles Davis"))
    }

    @Test func aSongWithoutIdsOffersNothingToOpen() {
        #expect(DetailRoute.artist(of: Self.track(artistID: nil, albumID: "a")) == nil)
        #expect(DetailRoute.artist(of: Self.track(artistID: "", albumID: "a")) == nil)
        #expect(DetailRoute.album(of: Self.track(artistID: "x", albumID: nil)) == nil)
        #expect(DetailRoute.album(of: Self.track(artistID: "x", albumID: "a", album: nil)) == nil)
    }

    @Test func routesAreDistinctPerResource() {
        #expect(DetailRoute.artist(title: "A", spotifyID: "1").id != DetailRoute.album(title: "A", spotifyID: "1", artist: nil).id)
        #expect(DetailRoute.artist(title: "A", spotifyID: "1").id == DetailRoute.artist(title: "Other name", spotifyID: "1").id)
    }

    private nonisolated static func tracks(_ json: String) -> [CatalogTrackDetail] {
        try! JSONDecoder().decode([CatalogTrackDetail].self, from: Data(json.utf8))
    }

    @Test func aTracklistIsInPlayOrder() {
        let list = Self.tracks(#"[{"pk":1,"name":"B","track_number":2},{"pk":2,"name":"A","track_number":1},{"pk":3,"name":"C","track_number":3}]"#)
        let discs = LibraryBrowsing.discs(list)
        #expect(discs == [LibraryBrowsing.Disc(number: 1, tracks: [1, 0, 2])])
    }

    @Test func discsAreSeparateAndOrdered() {
        let list = Self.tracks(#"[{"pk":1,"name":"d2t1","track_number":1,"disc_number":2},{"pk":2,"name":"d1t2","track_number":2,"disc_number":1},{"pk":3,"name":"d1t1","track_number":1,"disc_number":1}]"#)
        let discs = LibraryBrowsing.discs(list)
        #expect(discs.map(\.number) == [1, 2])
        #expect(discs[0].tracks == [2, 1])
        #expect(discs[1].tracks == [0])
    }

    @Test func unnumberedTracksKeepTheirOrderAfterNumberedOnes() {
        let list = Self.tracks(#"[{"pk":1,"name":"x"},{"pk":2,"name":"y","track_number":1},{"pk":3,"name":"z"}]"#)
        #expect(LibraryBrowsing.discs(list) == [LibraryBrowsing.Disc(number: 1, tracks: [1, 0, 2])])
        #expect(LibraryBrowsing.discs([]).isEmpty)
    }

    private nonisolated static func album(_ json: String) -> CatalogAlbumDetail {
        try! JSONDecoder().decode(CatalogAlbumDetail.self, from: Data(json.utf8))
    }

    @Test func albumFactsNameTracksAndYear() {
        let full = Self.album(#"{"pk":1,"name":"KoB","release_date":"1959-08-17","tracks":[{"pk":1,"name":"a"},{"pk":2,"name":"b"}]}"#)
        #expect(LibraryBrowsing.albumFacts(full) == "2 tracks · 1959")
        let single = Self.album(#"{"pk":1,"name":"One","tracks":[{"pk":1,"name":"a"}]}"#)
        #expect(LibraryBrowsing.albumFacts(single) == "1 track")
        let counted = Self.album(#"{"pk":1,"name":"Counted","total_tracks":9,"release_date":"x"}"#)
        #expect(LibraryBrowsing.albumFacts(counted) == "9 tracks", "the provider's count stands in for an unloaded tracklist; a malformed date is dropped")
        #expect(LibraryBrowsing.albumFacts(Self.album(#"{"pk":1,"name":"Empty"}"#)).isEmpty)
    }

    @Test func genreLineIsShortAndOptional() {
        let artist = try! JSONDecoder().decode(CatalogArtistDetail.self, from: Data(
            #"{"pk":1,"name":"A","genres":[{"pk":1,"name":"jazz"},{"pk":2,"name":"bebop"},{"pk":3,"name":"cool"},{"pk":4,"name":"fusion"}]}"#.utf8))
        #expect(LibraryBrowsing.genreLine(artist) == "jazz · bebop · cool")
        #expect(LibraryBrowsing.genreLine(artist, limit: 1) == "jazz")
        #expect(LibraryBrowsing.genreLine(nil) == nil)
        let none = try! JSONDecoder().decode(CatalogArtistDetail.self, from: Data(#"{"pk":1,"name":"A"}"#.utf8))
        #expect(LibraryBrowsing.genreLine(none) == nil)
    }
}
