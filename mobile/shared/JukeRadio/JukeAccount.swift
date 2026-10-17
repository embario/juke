import Foundation

struct JukeAccount: Codable, Equatable, Identifiable, Sendable {
    let id: String
    let displayName: String
    let email: String?
    let cloudAIEnabled: Bool

    static let localPreview = JukeAccount(
        id: "local-preview",
        displayName: "Listener",
        email: nil,
        cloudAIEnabled: false
    )
}

struct JukeSession: Codable, Equatable, Sendable {
    let account: JukeAccount
    let accessToken: String?
    let authenticatedAt: Date

    var isLocalPreview: Bool { account.id == JukeAccount.localPreview.id }
}
