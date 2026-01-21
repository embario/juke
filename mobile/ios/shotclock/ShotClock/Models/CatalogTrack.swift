import Foundation

struct CatalogSearchResponse: Decodable {
    let href: String?
    let results: [CatalogTrack]
    let limit: Int?
    let count: Int?
    let offset: Int?
    let previous: String?
}

struct CatalogTrack: Decodable, Identifiable {
    let pk: Int
    let spotifyId: String
    let name: String
    let durationMs: Int
    let explicit: Bool
    let albumName: String?
    let artistNames: String?

    var id: Int { pk }

    var formattedDuration: String {
        let totalSeconds = durationMs / 1000
        let minutes = totalSeconds / 60
        let seconds = totalSeconds % 60
        return String(format: "%d:%02d", minutes, seconds)
    }
}

struct AddTrackRequest: Encodable {
    let trackId: Int
    let startOffsetMs: Int
}
