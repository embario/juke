import Foundation

@MainActor
final class AuthViewModel: ObservableObject {
    @Published var username: String = ""
    @Published var email: String = ""
    @Published var password: String = ""
    @Published var passwordConfirm: String = ""
    @Published var isRegistering: Bool = false
    @Published var isLoading: Bool = false
    @Published var errorMessage: String?
    @Published var successMessage: String?
    @Published var showResendAction: Bool = false
    @Published var isResending: Bool = false
    @Published var resendMessage: String?
    @Published var resendError: String?

    private let session: SessionStore
    private let authService: AuthService
    private let configuration: AppConfiguration
    private let registrationDisabledMessage = "Registration is temporarily disabled. Please try again later."

    var isRegistrationDisabled: Bool {
        configuration.isRegistrationDisabled
    }

    init(session: SessionStore, configuration: AppConfiguration = .shared) {
        self.session = session
        self.configuration = configuration
        self.authService = AuthService()
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
        showResendAction = false
        resendMessage = nil
        resendError = nil
    }

    func submit() async {
        errorMessage = nil
        successMessage = nil
        showResendAction = false
        resendMessage = nil
        resendError = nil
        isLoading = true
        defer { isLoading = false }

        do {
            if isRegistering {
                if configuration.isRegistrationDisabled {
                    errorMessage = registrationDisabledMessage
                    return
                }
                guard password == passwordConfirm else {
                    errorMessage = "Passwords do not match."
                    return
                }
                let message = try await session.register(
                    username: username,
                    email: email,
                    password: password,
                    passwordConfirm: passwordConfirm
                )
                successMessage = message
                password = ""
                passwordConfirm = ""
                isRegistering = false
            } else {
                try await session.login(username: username, password: password)
                password = ""
                passwordConfirm = ""
            }
        } catch {
            let desc = error.localizedDescription
            errorMessage = desc
            // Show resend action if server indicates account already exists
            if desc.lowercased().contains("already exists") || desc.lowercased().contains("exists") {
                showResendAction = true
            }
        }
    }

    func resendVerification() async {
        let trimmedEmail = email.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !trimmedEmail.isEmpty else {
            resendError = "Enter your email to resend verification."
            return
        }
        isResending = true
        resendMessage = nil
        resendError = nil
        defer { isResending = false }

        do {
            _ = try await authService.resendVerification(email: trimmedEmail)
            resendMessage = "Verification email sent. Please check your inbox."
        } catch {
            resendError = error.localizedDescription
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
