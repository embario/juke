import SwiftUI

@MainActor
final class SessionStore: ObservableObject {
    private static let tokenKey = "shotclock.auth.token"

    @Published var token: String? {
        didSet {
            if let token {
                UserDefaults.standard.set(token, forKey: Self.tokenKey)
            } else {
                UserDefaults.standard.removeObject(forKey: Self.tokenKey)
            }
        }
    }
    @Published var profile: UserProfile?
    @Published var isLoadingProfile = false
    @Published var verificationMessage: String?

    private let api: APIClient

    init(api: APIClient = .shared) {
        self.api = api
        self.token = UserDefaults.standard.string(forKey: Self.tokenKey)
        if token != nil {
            Task { await refreshProfile() }
        }
    }

    func login(token: String) async {
        self.token = token
        await refreshProfile()
    }

    func logout() {
        token = nil
        profile = nil
    }

    func refreshProfile() async {
        guard let token else { return }
        isLoadingProfile = true
        defer { isLoadingProfile = false }
        do {
            let fetched: UserProfile = try await api.get("/auth/music-profiles/me/", token: token)
            self.profile = fetched
        } catch let error as APIError where error.errorDescription == APIError.unauthorized.errorDescription {
            self.logout()
        } catch {
            // Profile fetch failed but keep token - may be transient
        }
    }
}
