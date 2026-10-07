import Foundation

struct RecognizedTrack: Equatable, Sendable {
    let title: String
    let artist: String
    let album: String?
    let isrc: String?
    let artworkURL: URL?
    let appleMusicURL: URL?
    let shazamID: String?
    let matchOffset: TimeInterval?
    let matchConfidence: Double?
    let trackDuration: TimeInterval?
    let providerNamespace: String?
    let providerTrackID: String?
    let providerPlaybackURL: URL?

    init(
        title: String,
        artist: String,
        album: String?,
        isrc: String?,
        artworkURL: URL?,
        appleMusicURL: URL?,
        shazamID: String?,
        matchOffset: TimeInterval? = nil,
        matchConfidence: Double? = nil,
        trackDuration: TimeInterval? = nil,
        providerNamespace: String? = nil,
        providerTrackID: String? = nil,
        providerPlaybackURL: URL? = nil
    ) {
        self.title = title
        self.artist = artist
        self.album = album
        self.isrc = isrc
        self.artworkURL = artworkURL
        self.appleMusicURL = appleMusicURL
        self.shazamID = shazamID
        self.matchOffset = matchOffset
        self.matchConfidence = matchConfidence
        self.trackDuration = trackDuration
        self.providerNamespace = providerNamespace
        self.providerTrackID = providerTrackID
        self.providerPlaybackURL = providerPlaybackURL
    }

    var identityKey: String {
        if let isrc, !isrc.isEmpty { return "isrc:\(isrc.uppercased())" }
        if let providerNamespace, let providerTrackID, !providerTrackID.isEmpty {
            return "provider:\(providerNamespace):\(providerTrackID)"
        }
        if let shazamID, !shazamID.isEmpty { return "shazam:\(shazamID)" }
        return "metadata:\(artist.identityNormalized)|\(title.identityNormalized)"
    }

    func isLikelySameRecording(as other: RecognizedTrack) -> Bool {
        if let isrc, let otherISRC = other.isrc, !isrc.isEmpty, !otherISRC.isEmpty {
            return isrc.caseInsensitiveCompare(otherISRC) == .orderedSame
        }
        if let shazamID, let otherShazamID = other.shazamID,
           !shazamID.isEmpty, !otherShazamID.isEmpty {
            return shazamID == otherShazamID
        }
        return artist.identityNormalized == other.artist.identityNormalized
            && title.identityNormalized == other.title.identityNormalized
    }
}

private extension String {
    var identityNormalized: String {
        precomposedStringWithCanonicalMapping
            .split(whereSeparator: \.isWhitespace)
            .joined(separator: " ")
            .lowercased()
    }
}
