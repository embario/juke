import Foundation
import Testing
@testable import JukeApp

@MainActor @Suite struct NowPlayingRecognitionFeedTests {
    private func track(id: String, source: String) -> NowPlayingTrack {
        NowPlayingTrack(id: id, title: "Blue in Green", artist: "Miles Davis", album: "Kind of Blue", artworkURL: nil, localArtwork: nil, source: source)
    }

    @Test func spotifyTracksKeepTheirSpotifyID() {
        let recognized = NowPlayingRecognitionFeed.recognized(track(id: "0aWMVrwxPNYkKmFthzmpRi", source: "Spotify"))
        #expect(SpotifyTrackMatcher.spotifyID(for: recognized) == "0aWMVrwxPNYkKmFthzmpRi")
        #expect(RecognitionSource(track: recognized) == .metadata)
    }

    @Test func appleMusicTracksNeedACatalogLookup() {
        let recognized = NowPlayingRecognitionFeed.recognized(track(id: "42", source: "Apple Music"))
        #expect(SpotifyTrackMatcher.spotifyID(for: recognized) == nil)
        #expect(RecognitionSource(track: recognized) == .metadata)
    }

    @Test func aroundMeMatchesCountAsShazam() {
        let recognized = NowPlayingRecognitionFeed.recognized(track(id: "shz-1", source: "Shazam · Around Me"), matchOffset: 31)
        #expect(RecognitionSource(track: recognized) == .shazam)
        #expect(recognized.matchOffset == 31)
    }

    @Test func aSongPlayedElsewherePostsOneRecognizedEvent() async {
        final class Feed: RecognitionFeed { var track: RecognizedTrack?; var isPlaying = true; var isAudioPresent = true }
        let feed = Feed()
        var posted: [Radio.EventRequest] = []
        let recognizer = BackgroundRecognizer(
            isEnabled: { true },
            resolveCatalog: { _ in "spotify-id" },
            post: { posted.append($0) },
            sleep: { _ in }
        )
        feed.track = NowPlayingRecognitionFeed.recognized(track(id: "42", source: "Apple Music"))
        recognizer.observe(feed.track, isAudible: true)
        await recognizer.pending?.value
        #expect(posted.count == 1)
        #expect(posted.first?.event == .recognized)
        #expect(posted.first?.spotifyTrackId == "spotify-id")

        recognizer.isRadioPlaying = { true }
        recognizer.observe(feed.track, isAudible: true)
        #expect(recognizer.pending == nil)
    }
}
