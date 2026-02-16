import Foundation

// MARK: - Response Models

/// Response from the login endpoint containing the auth token.
public struct JukeAuthTokenResponse: Decodable, Sendable {
    /// The authentication token.
    public let token: String

    public init(token: String) {
        self.token = token
    }
}

/// Response from the registration endpoint.
public struct JukeRegisterResponse: Decodable, Sendable {
    /// Detail message from the server (e.g., "Check your inbox to confirm your account.").
    public let detail: String?

    public init(detail: String?) {
        self.detail = detail
    }
}

/// Response from the verify registration endpoint.
public struct JukeVerifyResponse: Decodable, Sendable {
    /// The authentication token (if auto-login is enabled).
    public let token: String?
    /// The username of the verified user.
    public let username: String?

    public init(token: String?, username: String?) {
        self.token = token
        self.username = username
    }
}

// MARK: - Request Models

/// Request body for the login endpoint.
public struct JukeLoginRequest: Encodable, Sendable {
    /// The username or email.
    public let username: String
    /// The password.
    public let password: String

    public init(username: String, password: String) {
        self.username = username
        self.password = password
    }
}

/// Request body for the registration endpoint.
public struct JukeRegisterRequest: Encodable, Sendable {
    /// The desired username.
    public let username: String
    /// The email address.
    public let email: String
    /// The password.
    public let password: String
    /// Password confirmation.
    public let passwordConfirm: String

    public init(username: String, email: String, password: String, passwordConfirm: String) {
        self.username = username
        self.email = email
        self.password = password
        self.passwordConfirm = passwordConfirm
    }

    enum CodingKeys: String, CodingKey {
        case username
        case email
        case password
        case passwordConfirm = "password_confirm"
    }
}

/// Request body for the verify registration endpoint.
public struct JukeVerifyRegistrationRequest: Encodable, Sendable {
    /// The user ID from the verification link.
    public let userId: String
    /// The timestamp from the verification link.
    public let timestamp: String
    /// The signature from the verification link.
    public let signature: String

    public init(userId: String, timestamp: String, signature: String) {
        self.userId = userId
        self.timestamp = timestamp
        self.signature = signature
    }

    enum CodingKeys: String, CodingKey {
        case userId = "user_id"
        case timestamp
        case signature
    }
}

/// Request body for resending a verification email.
public struct JukeResendVerificationRequest: Encodable, Sendable {
    /// The email address to resend verification to.
    public let email: String

    public init(email: String) {
        self.email = email
    }
}

// MARK: - Empty Response

/// Placeholder for endpoints that return no content.
public struct JukeEmptyResponse: Decodable, Sendable {
    public init() {}
}
