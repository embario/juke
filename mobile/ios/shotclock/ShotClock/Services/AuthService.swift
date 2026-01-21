import Foundation

struct AuthService {
    private let api: APIClient

    init(api: APIClient = .shared) {
        self.api = api
    }

    func login(username: String, password: String) async throws -> String {
        let body = LoginRequest(username: username, password: password)
        let response: TokenResponse = try await api.post("/auth/api-auth-token/", body: body)
        return response.token
    }

    func register(username: String, email: String, password: String, passwordConfirm: String) async throws -> RegisterResponse {
        let body = RegisterRequest(
            username: username,
            email: email,
            password: password,
            passwordConfirm: passwordConfirm
        )
        return try await api.post("/auth/accounts/register/", body: body)
    }

    func verifyRegistration(userId: String, timestamp: String, signature: String) async throws {
        let body = VerifyRegistrationRequest(
            userId: userId,
            timestamp: timestamp,
            signature: signature
        )
        try await api.postNoResponse("/auth/accounts/verify-registration/", body: body)
    }
}
