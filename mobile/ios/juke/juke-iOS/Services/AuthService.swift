import Foundation

struct AuthTokenResponse: Decodable {
    let token: String
}

struct RegisterResponse: Decodable {
    let detail: String?
}

struct VerifyResponse: Decodable {
    let token: String?
    let username: String?
}

struct EmptyResponse: Decodable {}

struct LoginRequest: Encodable {
    let username: String
    let password: String
}

struct RegisterRequest: Encodable {
    let username: String
    let email: String
    let password: String
    let passwordConfirm: String

    enum CodingKeys: String, CodingKey {
        case username
        case email
        case password
        case passwordConfirm = "password_confirm"
    }
}

final class AuthService {
    private let client: APIClient
    private let encoder: JSONEncoder

    init(client: APIClient = .shared) {
        self.client = client
        self.encoder = JSONEncoder()
        self.encoder.keyEncodingStrategy = .convertToSnakeCase
    }

    func login(username: String, password: String) async throws -> String {
        let payload = LoginRequest(username: username, password: password)
        let body = try encoder.encode(payload)
        let response: AuthTokenResponse = try await client.send(
            "/api/v1/auth/api-auth-token/",
            method: .post,
            body: body
        )
        return response.token
    }

    func register(username: String, email: String, password: String, passwordConfirm: String) async throws -> RegisterResponse {
        let payload = RegisterRequest(username: username, email: email, password: password, passwordConfirm: passwordConfirm)
        let body = try encoder.encode(payload)
        return try await client.send(
            "/api/v1/auth/accounts/register/",
            method: .post,
            body: body
        )
    }

    func logout(token: String) async throws {
        // Best-effort session revocation — backend returns 204 with empty body
        let _: EmptyResponse = try await client.send(
            "/api/v1/auth/session/logout/",
            method: .post,
            token: token
        )
    }

    func resendVerification(email: String) async throws -> RegisterResponse {
        struct ResendRequest: Encodable {
            let email: String
        }
        let payload = ResendRequest(email: email)
        let body = try encoder.encode(payload)
        return try await client.send(
            "/api/v1/auth/accounts/resend-registration/",
            method: .post,
            body: body
        )
    }

    func verifyRegistration(userId: String, timestamp: String, signature: String) async throws -> VerifyResponse {
        struct VerifyRequest: Encodable {
            let userId: String
            let timestamp: String
            let signature: String

            enum CodingKeys: String, CodingKey {
                case userId = "user_id"
                case timestamp
                case signature
            }
        }
        let payload = VerifyRequest(userId: userId, timestamp: timestamp, signature: signature)
        let body = try encoder.encode(payload)
        return try await client.send(
            "/api/v1/auth/accounts/verify-registration/",
            method: .post,
            body: body
        )
    }
}
