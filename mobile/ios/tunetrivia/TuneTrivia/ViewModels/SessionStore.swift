//
//  SessionStore.swift
//  TuneTrivia
//
//  Created by Juke Platform on 2026-01-22.
//

import Foundation

@MainActor
final class SessionStore: ObservableObject {
    @Published private(set) var token: String?
    @Published private(set) var profile: MusicProfile?
    @Published private(set) var isLoadingProfile = false

    private let authService: AuthService
    private let profileService: ProfileService
    private let defaults: UserDefaults

    private let tokenKey = "tunetrivia.auth.token"

    init(
        authService: AuthService = AuthService(),
        profileService: ProfileService = ProfileService(),
        defaults: UserDefaults = .standard
    ) {
        self.authService = authService
        self.profileService = profileService
        self.defaults = defaults
        self.token = defaults.string(forKey: tokenKey)

        if token != nil {
            Task {
                try? await refreshProfile()
            }
        }
    }

    var isAuthenticated: Bool {
        token != nil
    }

    var currentUsername: String {
        profile?.username ?? "Player"
    }

    func login(username: String, password: String) async throws {
        let token = try await authService.login(username: username, password: password)
        self.token = token
        defaults.set(token, forKey: tokenKey)
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

    func refreshProfile() async throws {
        guard let token else {
            profile = nil
            return
        }
        isLoadingProfile = true
        defer { isLoadingProfile = false }
        profile = try await profileService.fetchMyProfile(token: token)
    }

    func logout() {
        token = nil
        profile = nil
        defaults.removeObject(forKey: tokenKey)
    }
}
