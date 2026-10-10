import Testing
@testable import JukeApp

@Suite struct SleeveActionsTests {
    private func track(albumID: String? = "alb", album: String? = "Kind of Blue") -> Radio.Track {
        Radio.Track(spotifyId: "t1", uri: "spotify:track:t1", title: "So What", artist: "Miles Davis", artistId: "a",
                    album: album, albumId: albumID, artworkUrl: nil, durationMs: 1000)
    }

    @Test func fourActionsInTheAgreedOrder() {
        #expect(SleeveActions.items(for: track()).map(\.action) == [.newStation, .browseAlbum, .favorite, .saveForLater])
    }

    @Test func stationAndAlbumAreAvailableForASongThatNamesItsAlbum() {
        let items = SleeveActions.items(for: track())
        #expect(items[0].isEnabled && items[0].note == nil)
        #expect(items[1].isEnabled && items[1].note == nil)
    }

    @Test func favoritesAndSaveForLaterAreListedButDisabledWithANote() {
        let items = SleeveActions.items(for: track())
        for item in items[2...] {
            #expect(!item.isEnabled)
            #expect(item.note?.isEmpty == false)
        }
    }

    @Test func aSongWithoutAnAlbumCannotBrowseButCanStartAStation() {
        let items = SleeveActions.items(for: track(albumID: nil, album: nil))
        #expect(items[0].isEnabled)
        #expect(!items[1].isEnabled && items[1].note != nil)
        #expect(SleeveActions.albumRoute(for: track(albumID: nil, album: nil)) == nil)
    }

    @Test func withNoSongNothingIsAvailable() {
        #expect(SleeveActions.items(for: nil).allSatisfy { !$0.isEnabled })
    }

    @Test func browseOpensTheSongsAlbum() {
        #expect(SleeveActions.albumRoute(for: track()) == .album(title: "Kind of Blue", spotifyID: "alb", artist: "Miles Davis"))
    }

    @Test func theSheetOpensOnlyWhenTheRecordGoesIntoItsSleeve() {
        #expect(SleeveActions.shouldPresent(wasPutAway: false, isPutAway: true))
        #expect(!SleeveActions.shouldPresent(wasPutAway: true, isPutAway: true), "already put away")
        #expect(!SleeveActions.shouldPresent(wasPutAway: true, isPutAway: false), "the record came back out")
        #expect(!SleeveActions.shouldPresent(wasPutAway: false, isPutAway: false))
    }
}
