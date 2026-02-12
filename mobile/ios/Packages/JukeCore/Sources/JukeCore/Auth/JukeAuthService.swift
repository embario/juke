import Foundation

/// Service for authentication operations.
///
/// Provides login, registration, logout, and email verification functionality.
///
/// ## Usage
///
/// ```swift
/// let authService = JukeAuthService()
///
/// // Login
/// let token = try await authService.login(username: "user", password: "pass")
///
/// // Register
/// let response = try await authService.register(
///     username: "newuser",
///     email: "user@example.com",
///     password: "password123",
///     passwordConfirm: "password123"
/// )
/// ```
public final class JukeAuthService: Sendable {
    private let client: JukeAPIClient
    private let encoder: JSONEncoder

    /// Creates an auth service with the given API client.
    /// - Parameter client: The API client to use. Defaults to `.shared`.
    public init(client: JukeAPIClient = .shared) {
        self.client = client
        self.encoder = JSONEncoder()
        self.encoder.keyEncodingStrategy = .convertToSnakeCase
    }

    // MARK: - Login

    /// Logs in a user with username and password.
    /// - Parameters:
    ///   - username: The username or email.
    ///   - password: The password.
    /// - Returns: The authentication token.
    /// - Throws: `JukeAPIError` on failure.
    public func login(username: String, password: String) async throws -> String {
        let payload = JukeLoginRequest(username: username, password: password)
        let body = try encoder.encode(payload)
        let response: JukeAuthTokenResponse = try await client.send(
            "/api/v1/auth/api-auth-token/",
            method: .post,
            body: body
        )
        return response.token
    }

    // MARK: - Registration

    /// Registers a new user.
    /// - Parameters:
    ///   - username: The desired username.
    ///   - email: The email address.
    ///   - password: The password.
    ///   - passwordConfirm: Password confirmation (must match password).
    /// - Returns: Registration response with detail message.
    /// - Throws: `JukeAPIError` on failure.
    public func register(
        username: String,
        email: String,
        password: String,
        passwordConfirm: String
    ) async throws -> JukeRegisterResponse {
        let payload = JukeRegisterRequest(
            username: username,
            email: email,
            password: password,
            passwordConfirm: passwordConfirm
        )
        let body = try encoder.encode(payload)
        return try await client.send(
            "/api/v1/auth/accounts/register/",
            method: .post,
            body: body
        )
    }

    // MARK: - Logout

    /// Logs out the current user by revoking their session on the server.
    ///
    /// This is a best-effort operation. Even if it fails, the local token
    /// should be cleared.
    /// - Parameter token: The current authentication token.
    /// - Throws: `JukeAPIError` on failure.
    public func logout(token: String) async throws {
        let _: JukeEmptyResponse = try await client.send(
            "/api/v1/auth/session/logout/",
            method: .post,
            token: token
        )
    }

    // MARK: - Email Verification

    /// Verifies a user's email address using the verification link parameters.
    /// - Parameters:
    ///   - userId: The user ID from the verification link.
    ///   - timestamp: The timestamp from the verification link.
    ///   - signature: The signature from the verification link.
    /// - Returns: Verification response (may include token for auto-login).
    /// - Throws: `JukeAPIError` on failure.
    public func verifyRegistration(
        userId: String,
        timestamp: String,
        signature: String
    ) async throws -> JukeVerifyResponse {
        let payload = JukeVerifyRegistrationRequest(
            userId: userId,
            timestamp: timestamp,
            signature: signature
        )
        let body = try encoder.encode(payload)
        return try await client.send(
            "/api/v1/auth/accounts/verify-registration/",
            method: .post,
            body: body
        )
    }

    /// Resends the verification email to the given address.
    /// - Parameter email: The email address to resend verification to.
    /// - Returns: Response with detail message.
    /// - Throws: `JukeAPIError` on failure.
    public func resendVerification(email: String) async throws -> JukeRegisterResponse {
        let payload = JukeResendVerificationRequest(email: email)
        let body = try encoder.encode(payload)
        return try await client.send(
            "/api/v1/auth/accounts/resend-registration/",
            method: .post,
            body: body
        )
    }
}
