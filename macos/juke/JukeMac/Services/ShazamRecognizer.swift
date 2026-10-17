import AVFoundation
import Foundation
import ShazamKit

protocol TrackRecognizing: AnyObject, Sendable {
    var onMatch: (@Sendable (RecognizedTrack) -> Void)? { get set }
    var onError: (@Sendable (String) -> Void)? { get set }
    func process(_ buffer: AVAudioPCMBuffer, at time: AVAudioTime?)
    func invalidate()
}

final class ShazamRecognizer: NSObject, @unchecked Sendable, TrackRecognizing {
    var onMatch: (@Sendable (RecognizedTrack) -> Void)?
    var onError: (@Sendable (String) -> Void)?

    private let session = SHSession()

    override init() {
        super.init()
        session.delegate = self
    }

    func process(_ buffer: AVAudioPCMBuffer, at time: AVAudioTime?) {
        session.matchStreamingBuffer(buffer, at: time)
    }

    func invalidate() {
        session.delegate = nil
        onMatch = nil
        onError = nil
    }
}

extension ShazamRecognizer: SHSessionDelegate {
    func session(_ session: SHSession, didFind match: SHMatch) {
        guard let item = match.mediaItems.first else { return }
        let track = RecognizedTrack(
            title: item.title ?? "Unknown Track",
            artist: item.artist ?? item.subtitle ?? "Unknown Artist",
            album: item.songs.first?.albumTitle,
            isrc: item.isrc,
            artworkURL: item.artworkURL,
            appleMusicURL: item.appleMusicURL,
            shazamID: item.shazamID,
            matchOffset: item.predictedCurrentMatchOffset,
            matchConfidence: Double(item.confidence),
            trackDuration: item.songs.first?.duration
        )
        onMatch?(track)
    }

    func session(
        _ session: SHSession,
        didNotFindMatchFor signature: SHSignature,
        error: (any Error)?
    ) {
        if let error { onError?(error.localizedDescription) }
    }
}
