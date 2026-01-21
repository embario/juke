import Foundation

struct UserProfile: Codable, Identifiable {
    let id: Int
    let username: String
    let displayName: String?
    let bio: String?
    let avatarUrl: String?

    var preferredName: String {
        if let displayName, !displayName.isEmpty { return displayName }
        return username
    }
}

struct TokenResponse: Decodable {
    let token: String
}

struct RegisterRequest: Encodable {
    let username: String
    let email: String
    let password: String
    let passwordConfirm: String
}

struct RegisterResponse: Decodable {
    let id: Int
    let username: String
    let email: String
}

struct LoginRequest: Encodable {
    let username: String
    let password: String
}

struct VerifyRegistrationRequest: Encodable {
    let userId: String
    let timestamp: String
    let signature: String
}
