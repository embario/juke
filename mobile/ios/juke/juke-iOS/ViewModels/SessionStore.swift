import Foundation

@MainActor
final class SessionStore: ObservableObject {
    @Published private(set) var token: String?
    @Published private(set) var username: String?
    @Published private(set) var profile: MusicProfile?
    @Published private(set) var isLoadingProfile = false

    private let authService: AuthService
    private let profileService: ProfileService
    private let defaults: UserDefaults

    private let tokenKey = "juke.auth.token"
    private let usernameKey = "juke.auth.username"

    init(
        authService: AuthService = AuthService(),
        profileService: ProfileService = ProfileService(),
        defaults: UserDefaults = .standard
    ) {
        self.authService = authService
        self.profileService = profileService
        self.defaults = defaults
        self.token = defaults.string(forKey: tokenKey)
        self.username = defaults.string(forKey: usernameKey)

        if token != nil {
            Task {
                await self.validateAndRefreshProfile()
            }
        }
    }

    var isAuthenticated: Bool {
        token != nil
    }

    func login(username: String, password: String) async throws {
        let token = try await authService.login(username: username, password: password)
        self.token = token
        defaults.set(token, forKey: tokenKey)
        self.username = username
        defaults.set(username, forKey: usernameKey)
        do {
            try await refreshProfile()
        } catch {
            logout()
            throw error
        }
    }

    func register(username: String, email: String, password: String, passwordConfirm: String) async throws -> String {
        let response = try await authService.register(
            username: username,
            email: email,
            password: password,
            passwordConfirm: passwordConfirm
        )
        let defaultMessage = "Check your inbox to confirm your account."
        return response.detail ?? defaultMessage
    }

    func authenticateWithToken(_ token: String, username: String) {
        self.token = token
        defaults.set(token, forKey: tokenKey)
        self.username = username
        defaults.set(username, forKey: usernameKey)
        // Kick off a profile refresh but don't block
        Task {
            try? await refreshProfile()
        }
    }

    func refreshProfile() async throws {
        guard let token else {
            profile = nil
            return
        }
        isLoadingProfile = true
        defer { isLoadingProfile = false }
        profile = try await profileService.fetchMyProfile(token: token)
        if let profile {
            username = profile.username
            defaults.set(profile.username, forKey: usernameKey)
        }
    }

    func logout() {
        let activeToken = token
        token = nil
        username = nil
        profile = nil
        defaults.removeObject(forKey: tokenKey)
        defaults.removeObject(forKey: usernameKey)
        // Best-effort backend session revocation — fire and forget
        if let activeToken {
            Task {
                try? await authService.logout(token: activeToken)
            }
        }
    }

    // Validates the stored token by fetching the profile.
    // On 401/403 the token is stale — clear session silently.
    private func validateAndRefreshProfile() async {
        do {
            try await refreshProfile()
        } catch let error as APIError {
            switch error {
            case .server(let status, _) where status == 401 || status == 403:
                logout()
            default:
                break
            }
        } catch {
            // Non-API errors (network, decoding) — leave token in place
            // so user isn't unexpectedly signed out on a flaky connection.
        }
    }
}
