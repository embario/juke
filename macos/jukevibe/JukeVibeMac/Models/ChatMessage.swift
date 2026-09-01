import Foundation
import SwiftData

@Model
final class ChatMessage {
    @Attribute(.unique) var id: UUID
    var accountID: String
    var roleRawValue: String
    var createdAt: Date
    var encryptedContent: Data
    var trackIdentity: String?

    init(id: UUID = UUID(), accountID: String, role: Role, encryptedContent: Data, trackIdentity: String? = nil, createdAt: Date = .now) {
        self.id = id
        self.accountID = accountID
        roleRawValue = role.rawValue
        self.createdAt = createdAt
        self.encryptedContent = encryptedContent
        self.trackIdentity = trackIdentity
    }

    enum Role: String, Codable {
        case user
        case assistant
    }
}
