import SwiftUI

@MainActor
final class AuthViewModel: ObservableObject {
    @Published var username = ""
    @Published var email = ""
    @Published var password = ""
    @Published var passwordConfirm = ""
    @Published var isRegistering = false
    @Published var isLoading = false
    @Published var errorMessage: String?
    @Published var successMessage: String?

    private let authService: AuthService

    init(authService: AuthService = AuthService()) {
        self.authService = authService
    }

    func submit(session: SessionStore) async {
        errorMessage = nil
        successMessage = nil

        guard !username.trimmingCharacters(in: .whitespaces).isEmpty else {
            errorMessage = "Username is required."
            return
        }
        guard !password.isEmpty else {
            errorMessage = "Password is required."
            return
        }

        if isRegistering {
            guard !email.trimmingCharacters(in: .whitespaces).isEmpty else {
                errorMessage = "Email is required."
                return
            }
            guard password == passwordConfirm else {
                errorMessage = "Passwords do not match."
                return
            }
            guard password.count >= 8 else {
                errorMessage = "Password must be at least 8 characters."
                return
            }
        }

        isLoading = true
        defer { isLoading = false }

        do {
            if isRegistering {
                _ = try await authService.register(
                    username: username.trimmingCharacters(in: .whitespaces),
                    email: email.trimmingCharacters(in: .whitespaces),
                    password: password,
                    passwordConfirm: passwordConfirm
                )
                successMessage = "Account created! Check your email to verify, then log in."
                isRegistering = false
            } else {
                let token = try await authService.login(
                    username: username.trimmingCharacters(in: .whitespaces),
                    password: password
                )
                await session.login(token: token)
            }
        } catch let error as APIError {
            errorMessage = error.errorDescription
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}
