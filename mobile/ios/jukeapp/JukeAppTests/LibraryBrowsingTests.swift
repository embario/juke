import Foundation
import Testing
@testable import JukeApp

@Suite struct LibraryBrowsingTests {
    private func result(_ pk: Int, _ name: String, _ spotifyID: String?) -> CatalogSearchResult {
        CatalogSearchResult(pk: pk, name: name, spotifyID: spotifyID, albumName: nil, artistNames: nil, durationMs: nil, albumLink: nil, artworkURL: nil, spotifyData: nil)
    }

    private func album() throws -> CatalogAlbumDetail {
        try JSONDecoder().decode(CatalogAlbumDetail.self, from: Data("""
        {"pk":1,"name":"Kind of Blue","spotify_id":"alb","spotify_data":{"images":["https://i.example/a.jpg"]},
         "tracks":[{"pk":1,"name":"So What","spotify_id":"t1","duration_ms":562000,"track_number":1},{"pk":2,"name":"No Id","duration_ms":1}],"related_albums":[]}
        """.utf8))
    }

    @Test func matchRequiresTheExactSpotifyID() {
        let rows = [result(1, "Kind of Blue", "other"), result(2, "Kind of Blue (Remastered)", "alb")]
        #expect(LibraryBrowsing.match(rows, spotifyID: "alb")?.pk == 2)
        #expect(LibraryBrowsing.match([result(1, "Kind of Blue", "other")], spotifyID: "alb") == nil, "same name, different id is another album")
        #expect(LibraryBrowsing.match([result(3, "Kind of Blue", nil)], spotifyID: "alb") == nil)
    }

    @Test func trackAndAlbumSeeds() throws {
        let album = try album()
        let seed = try #require(LibraryBrowsing.trackSeed(album.tracks[0], in: album, artist: "Miles Davis"))
        #expect(seed.kind == .track && seed.spotifyId == "t1" && seed.subtitle == "Miles Davis")
        #expect(seed.artworkUrl == "https://i.example/a.jpg")
        #expect(LibraryBrowsing.trackSeed(album.tracks[1], in: album, artist: nil) == nil, "tracks without a Spotify id cannot seed a station")
        let albumSeed = try #require(LibraryBrowsing.albumSeed(album, artist: "Miles Davis"))
        #expect(albumSeed.kind == .album && albumSeed.spotifyId == "alb")
    }

    @Test func durationFormatting() {
        #expect(LibraryBrowsing.duration(562_000) == "9:22")
        #expect(LibraryBrowsing.duration(nil) == nil)
    }

    @Test func frontToBackLibraryCrateReservesSpaceAboveThePicker() {
        #expect(CrateLayout.libraryTopClearance(for: .sideToSide) == 0)
        #expect(CrateLayout.libraryTopClearance(for: .frontToBack) == 88)

        let frontToBackTop = (CrateLayout.wellHeight + 40 - CrateMode.frontToBack.sleeveSize) / 2 - 6 * 20
        #expect(frontToBackTop + CrateLayout.libraryTopClearance(for: .frontToBack) >= 16)
    }
}

@Suite struct LibrarySongRoutingTests {
    private func item(track: Radio.Track?) -> Radio.CrateItem {
        Radio.CrateItem(id: Radio.ID("1"), kind: .track, spotifyId: "t2", title: "Freddie Freeloader", subtitle: "Miles Davis", artworkUrl: nil, track: track)
    }

    private func track(albumID: String?, album: String?) -> Radio.Track {
        Radio.Track(spotifyId: "t2", uri: "spotify:track:t2", title: "Freddie Freeloader", artist: "Miles Davis", artistId: "a",
                    album: album, albumId: albumID, artworkUrl: nil, durationMs: 1000)
    }

    private func tracks() throws -> [CatalogTrackDetail] {
        try JSONDecoder().decode(CatalogAlbumDetail.self, from: Data("""
        {"pk":1,"name":"Kind of Blue","tracks":[{"pk":1,"name":"So What","spotify_id":"t1"},{"pk":2,"name":"Freddie Freeloader","spotify_id":"t2"},{"pk":3,"name":"No id"}],"related_albums":[]}
        """.utf8)).tracks
    }

    @Test func aSongThatNamesItsAlbumOpensIt() throws {
        let target = try #require(LibraryBrowsing.albumTarget(for: item(track: track(albumID: "alb", album: "Kind of Blue"))))
        #expect(target.title == "Kind of Blue" && target.spotifyID == "alb" && target.highlight == "t2" && target.artist == "Miles Davis")
    }

    @Test func aSongWithoutAnAlbumNeedsALookup() {
        #expect(LibraryBrowsing.albumTarget(for: item(track: nil)) == nil)
        #expect(LibraryBrowsing.albumTarget(for: item(track: track(albumID: nil, album: "Kind of Blue"))) == nil)
        #expect(LibraryBrowsing.albumTarget(for: item(track: track(albumID: "", album: "Kind of Blue"))) == nil)
    }

    @Test func aCatalogResultLinksTheAlbumByItsCatalogID() throws {
        let linked = CatalogSearchResult(pk: 9, name: "Freddie Freeloader", spotifyID: "t2", albumName: "Kind of Blue", artistNames: "Miles Davis",
                                         durationMs: nil, albumLink: URL(string: "https://x.example/api/v1/albums/1959/"), artworkURL: nil, spotifyData: nil)
        let target = try #require(LibraryBrowsing.albumTarget(for: item(track: nil), found: linked))
        #expect(target.catalogID == 1959 && target.title == "Kind of Blue" && target.highlight == "t2")
        let unlinked = CatalogSearchResult(pk: 9, name: "x", spotifyID: "t2", albumName: nil, artistNames: nil, durationMs: nil, albumLink: nil, artworkURL: nil, spotifyData: nil)
        #expect(LibraryBrowsing.albumTarget(for: item(track: nil), found: unlinked) == nil)
    }

    @Test func highlightMatchesTheExactSongOnly() throws {
        let rows = try tracks()
        #expect(LibraryBrowsing.highlightIndex(rows, spotifyID: "t2") == 1)
        #expect(LibraryBrowsing.highlightIndex(rows, spotifyID: "nope") == nil)
        #expect(LibraryBrowsing.highlightIndex(rows, spotifyID: nil) == nil)
        #expect(LibraryBrowsing.highlightIndex(rows, spotifyID: "") == nil, "an empty id never matches the track that has none")
    }

    // MARK: The swipe

    @Test func aLongDownwardDragOpens() {
        #expect(LibrarySwipe.opensDetails(translation: CGSize(width: 5, height: 90), velocity: 0))
    }

    @Test func aQuickShortFlickOpens() {
        #expect(LibrarySwipe.opensDetails(translation: CGSize(width: 0, height: 30), velocity: 900))
        #expect(!LibrarySwipe.opensDetails(translation: CGSize(width: 0, height: 30), velocity: 100), "short and slow is a wobble")
        #expect(!LibrarySwipe.opensDetails(translation: CGSize(width: 0, height: 10), velocity: 2000))
    }

    @Test func upwardAndSidewaysDragsNeverOpen() {
        #expect(!LibrarySwipe.opensDetails(translation: CGSize(width: 0, height: -120), velocity: -900))
        #expect(!LibrarySwipe.opensDetails(translation: CGSize(width: 120, height: 40), velocity: 900), "flipping the crate")
        #expect(!LibrarySwipe.opensDetails(translation: CGSize(width: 80, height: 90), velocity: 0), "a diagonal drag is not vertical enough")
    }

    @Test func aMostlyVerticalDragDoesNotFlipTheCrate() {
        #expect(LibrarySwipe.isVertical(CGSize(width: 10, height: -60)))
        #expect(!LibrarySwipe.isVertical(CGSize(width: 60, height: 10)))
    }
}
