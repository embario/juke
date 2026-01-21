import Foundation

struct SessionPlayer: Codable, Identifiable {
    let id: String
    let user: PlayerUser
    let joinedAt: String
    let isAdmin: Bool
}

struct PlayerUser: Codable {
    let id: Int
    let username: String
    let displayName: String?

    var preferredName: String {
        if let displayName, !displayName.isEmpty { return displayName }
        return username
    }
}
