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
    private let configuration: AppConfiguration
    private let registrationDisabledMessage = "Registration is temporarily disabled. Please try again later."

    var isRegistrationDisabled: Bool {
        configuration.isRegistrationDisabled
    }

    init(authService: AuthService = AuthService(), configuration: AppConfiguration = .shared) {
        self.authService = authService
        self.configuration = configuration
    }

    func setMode(registering: Bool) {
        if configuration.isRegistrationDisabled && registering {
            errorMessage = registrationDisabledMessage
            return
        }
        guard registering != isRegistering else { return }
        isRegistering = registering
        errorMessage = nil
        successMessage = nil
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
            if configuration.isRegistrationDisabled {
                errorMessage = registrationDisabledMessage
                return
            }
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

struct AppConfiguration {
    static let shared = AppConfiguration()

    let isRegistrationDisabled: Bool

    init(bundle: Bundle = .main, processInfo: ProcessInfo = .processInfo) {
        let plistValue = bundle.object(forInfoDictionaryKey: "DISABLE_REGISTRATION")
        self.init(env: processInfo.environment, plistValue: plistValue)
    }

    init(env: [String: String], plistValue: Any?) {
        if let envValue = env["DISABLE_REGISTRATION"] {
            isRegistrationDisabled = AppConfiguration.parseFlag(envValue)
            return
        }
        if let plistValue = plistValue as? String {
            isRegistrationDisabled = AppConfiguration.parseFlag(plistValue)
            return
        }
        if let plistValue = plistValue as? Bool {
            isRegistrationDisabled = plistValue
            return
        }
        isRegistrationDisabled = false
    }

    private static func parseFlag(_ value: String) -> Bool {
        return ["1", "true", "yes", "on"].contains(value.trimmingCharacters(in: .whitespacesAndNewlines).lowercased())
    }
}
