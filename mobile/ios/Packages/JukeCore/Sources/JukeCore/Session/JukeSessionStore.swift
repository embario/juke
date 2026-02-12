import Foundation
import Combine

/// Protocol for receiving session state change notifications.
public protocol JukeSessionStoreDelegate: AnyObject {
    /// Called when the authentication state changes (login/logout).
    @MainActor func sessionStoreDidUpdateAuthState(_ store: JukeSessionStore)

    /// Called when the user profile is refreshed.
    @MainActor func sessionStore(_ store: JukeSessionStore, didUpdateProfile profile: JukeMusicProfile?)
}

/// Default empty implementations for optional delegate methods.
public extension JukeSessionStoreDelegate {
    func sessionStoreDidUpdateAuthState(_ store: JukeSessionStore) {}
    func sessionStore(_ store: JukeSessionStore, didUpdateProfile profile: JukeMusicProfile?) {}
}

/// Manages user session state including authentication and profile data.
///
/// `JukeSessionStore` handles:
/// - Token persistence in UserDefaults
/// - Login/logout flows
/// - Profile fetching and caching
/// - Token validation on app launch
///
/// ## Usage
///
/// ```swift
/// // Create with app-specific key prefix
/// let session = JukeSessionStore(keyPrefix: "myapp")
///
/// // Login
/// try await session.login(username: "user", password: "pass")
///
/// // Check auth state
/// if session.isAuthenticated {
///     print("Logged in as \(session.username ?? "unknown")")
/// }
///
/// // Logout
/// session.logout()
/// ```
@MainActor
public final class JukeSessionStore: ObservableObject {
    // MARK: - Published Properties

    /// The current authentication token, or nil if not logged in.
    @Published public private(set) var token: String?

    /// The current user's username.
    @Published public private(set) var username: String?

    /// The current user's music profile.
    @Published public private(set) var profile: JukeMusicProfile?

    /// Whether a profile fetch is in progress.
    @Published public private(set) var isLoadingProfile: Bool = false

    /// Message from deep link verification (success or error).
    @Published public var verificationMessage: String?

    // MARK: - Delegate

    /// Delegate for receiving session state change notifications.
    public weak var delegate: JukeSessionStoreDelegate?

    // MARK: - Private Properties

    private let authService: JukeAuthService
    private let profileService: JukeProfileService
    private let defaults: UserDefaults
    private let tokenKey: String
    private let usernameKey: String

    // MARK: - Initialization

    /// Creates a session store with the given configuration.
    /// - Parameters:
    ///   - keyPrefix: Prefix for UserDefaults keys (e.g., "juke", "shotclock", "tunetrivia").
    ///   - authService: Auth service for login/logout. Defaults to a new instance.
    ///   - profileService: Profile service for fetching profiles. Defaults to a new instance.
    ///   - defaults: UserDefaults for persistence. Defaults to `.standard`.
    public init(
        keyPrefix: String,
        authService: JukeAuthService = JukeAuthService(),
        profileService: JukeProfileService = JukeProfileService(),
        defaults: UserDefaults = .standard
    ) {
        self.authService = authService
        self.profileService = profileService
        self.defaults = defaults
        self.tokenKey = "\(keyPrefix).auth.token"
        self.usernameKey = "\(keyPrefix).auth.username"

        // Restore persisted state
        self.token = defaults.string(forKey: tokenKey)
        self.username = defaults.string(forKey: usernameKey)

        // Validate token and fetch profile if we have a stored token
        if token != nil {
            Task {
                await self.validateAndRefreshProfile()
            }
        }
    }

    // MARK: - Computed Properties

    /// Whether the user is currently authenticated.
    public var isAuthenticated: Bool {
        token != nil
    }

    /// The user's preferred display name, falling back to username or "User".
    public var currentDisplayName: String {
        profile?.preferredName ?? username ?? "User"
    }

    // MARK: - Authentication

    /// Logs in with username and password.
    /// - Parameters:
    ///   - username: The username or email.
    ///   - password: The password.
    /// - Throws: `JukeAPIError` on failure.
    public func login(username: String, password: String) async throws {
        let token = try await authService.login(username: username, password: password)
        self.token = token
        defaults.set(token, forKey: tokenKey)
        self.username = username
        defaults.set(username, forKey: usernameKey)

        // Fetch profile after login
        do {
            try await refreshProfile()
        } catch {
            // Profile fetch failed - logout to avoid inconsistent state
            logout()
            throw error
        }

        delegate?.sessionStoreDidUpdateAuthState(self)
    }

    /// Registers a new account.
    /// - Parameters:
    ///   - username: The desired username.
    ///   - email: The email address.
    ///   - password: The password.
    ///   - passwordConfirm: Password confirmation.
    /// - Returns: A message to display to the user (e.g., "Check your inbox...").
    /// - Throws: `JukeAPIError` on failure.
    public func register(
        username: String,
        email: String,
        password: String,
        passwordConfirm: String
    ) async throws -> String {
        let response = try await authService.register(
            username: username,
            email: email,
            password: password,
            passwordConfirm: passwordConfirm
        )
        return response.detail ?? "Check your inbox to confirm your account."
    }

    /// Authenticates with an existing token (e.g., from deep link verification).
    /// - Parameters:
    ///   - token: The authentication token.
    ///   - username: The username (optional).
    public func authenticateWithToken(_ token: String, username: String? = nil) {
        self.token = token
        defaults.set(token, forKey: tokenKey)

        if let username {
            self.username = username
            defaults.set(username, forKey: usernameKey)
        }

        // Kick off a profile refresh but don't block
        Task {
            try? await refreshProfile()
        }

        delegate?.sessionStoreDidUpdateAuthState(self)
    }

    /// Logs out the current user.
    ///
    /// Clears local state and attempts to revoke the session on the server
    /// (best-effort, failures are ignored).
    public func logout() {
        let activeToken = token

        // Clear local state immediately
        token = nil
        username = nil
        profile = nil
        defaults.removeObject(forKey: tokenKey)
        defaults.removeObject(forKey: usernameKey)

        delegate?.sessionStoreDidUpdateAuthState(self)

        // Best-effort server-side session revocation
        if let activeToken {
            Task {
                try? await authService.logout(token: activeToken)
            }
        }
    }

    // MARK: - Profile

    /// Refreshes the current user's profile from the server.
    /// - Throws: `JukeAPIError` on failure.
    public func refreshProfile() async throws {
        guard let token else {
            profile = nil
            return
        }

        isLoadingProfile = true
        defer { isLoadingProfile = false }

        let fetchedProfile = try await profileService.fetchMyProfile(token: token)
        profile = fetchedProfile

        // Update username from profile if available
        if !fetchedProfile.username.isEmpty {
            username = fetchedProfile.username
            defaults.set(fetchedProfile.username, forKey: usernameKey)
        }

        delegate?.sessionStore(self, didUpdateProfile: profile)
    }

    // MARK: - Token Validation

    /// Validates the stored token by fetching the profile.
    ///
    /// If the token is stale (401/403), the session is cleared silently.
    /// Network errors are ignored to avoid logging out on flaky connections.
    public func validateAndRefreshProfile() async {
        do {
            try await refreshProfile()
        } catch let error as JukeAPIError {
            switch error {
            case .unauthorized:
                // Token is stale - clear session
                logout()
            case .server(let status, _) where status == 403:
                // Forbidden - token might be revoked
                logout()
            default:
                // Other errors (network, decoding) - keep token
                break
            }
        } catch {
            // Non-API errors - keep token to avoid unexpected logout
        }
    }
}
