import Foundation

/// The user's choice to let Juke notice songs played elsewhere. Shares the key
/// the Mac app uses (`JukeSettings.Key.backgroundRecognition`).
enum JukeRecognitionSetting {
    static let key = "juke.settings.backgroundRecognition"
}

/// Presents `NowPlayingObserver` (Apple Music, linked Spotify, Around Me) as a
/// `RecognitionFeed`, so the shared `BackgroundRecognizer` can follow it.
/// iOS suspends the app in the background, so this runs while Juke is open.
@MainActor
final class NowPlayingRecognitionFeed: RecognitionFeed {
    private let observer: NowPlayingObserver

    init(_ observer: NowPlayingObserver) { self.observer = observer }

    var track: RecognizedTrack? { observer.track.map { Self.recognized($0, matchOffset: observer.shazamOffset) } }
    var isPlaying: Bool { observer.isPlaying }
    var isAudioPresent: Bool { observer.isPlaying }

    nonisolated static func recognized(_ track: NowPlayingTrack, matchOffset: TimeInterval? = nil) -> RecognizedTrack {
        var namespace: String?
        var shazamID: String?
        switch track.source {
        case "Spotify": namespace = "spotify"
        case "Apple Music": namespace = "apple_music"
        default: shazamID = track.id
        }
        return RecognizedTrack(
            title: track.title,
            artist: track.artist,
            album: track.album,
            isrc: nil,
            artworkURL: track.artworkURL,
            appleMusicURL: nil,
            shazamID: shazamID,
            matchOffset: shazamID == nil ? nil : matchOffset,
            providerNamespace: namespace,
            providerTrackID: namespace == nil ? nil : track.id
        )
    }
}
