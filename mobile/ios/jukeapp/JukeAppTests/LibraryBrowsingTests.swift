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
