import Foundation

struct SessionTrackItem: Codable, Identifiable {
    let id: String
    let trackId: Int
    let order: Int
    let startOffsetMs: Int
    let addedAt: String
    let trackName: String
    let trackArtist: String
    let trackAlbum: String
    let durationMs: Int
    let spotifyId: String
    let previewUrl: String?
    let addedBy: Int
    let addedByUsername: String
}
