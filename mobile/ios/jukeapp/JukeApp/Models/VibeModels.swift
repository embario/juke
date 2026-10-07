import Foundation
import SwiftData
import UIKit

@Model
final class EncryptedChatMessage {
    @Attribute(.unique) var id: UUID
    var accountID: String
    var role: String
    var createdAt: Date
    var encryptedContent: Data
    var trackIdentity: String?

    init(id: UUID, accountID: String, role: String, encryptedContent: Data, trackIdentity: String?, createdAt: Date = .now) {
        self.id = id; self.accountID = accountID; self.role = role; self.createdAt = createdAt
        self.encryptedContent = encryptedContent; self.trackIdentity = trackIdentity
    }
}

struct ChatLine: Identifiable, Equatable {
    let id: UUID
    let role: String
    let content: String
    let createdAt: Date
}

struct NowPlayingTrack: Equatable {
    let id: String
    let title: String
    let artist: String
    let album: String?
    let artworkURL: URL?
    let localArtwork: UIImage?
    let source: String

    static func == (lhs: Self, rhs: Self) -> Bool { lhs.id == rhs.id && lhs.source == rhs.source }
    var label: String { "\(title) — \(artist)" }
}

struct CatalogItem: Decodable, Identifiable, Sendable {
    let pk: Int
    let name: String
    let artistNames: String?
    let albumName: String?
    let spotifyData: SpotifyData?
    var id: Int { pk }
    struct SpotifyData: Decodable, Sendable { let images: [String]? }
    enum CodingKeys: String, CodingKey { case pk, name; case artistNames = "artist_names"; case albumName = "album_name"; case spotifyData = "spotify_data" }
    var subtitle: String { artistNames ?? albumName ?? "Juke catalog" }
    var artworkURL: URL? { spotifyData?.images?.first.flatMap(URL.init(string:)) }
}
