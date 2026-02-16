import Foundation
import Combine

/// ViewModel for authentication screens (login/registration).
///
/// Manages form state, validation, and submission for login and registration flows.
///
/// ## Usage
///
/// ```swift
/// struct AuthView: View {
///     @StateObject private var viewModel: JukeAuthViewModel
///
///     init(session: JukeSessionStore) {
///         _viewModel = StateObject(wrappedValue: JukeAuthViewModel(session: session))
///     }
///
///     var body: some View {
///         VStack {
///             JukeCoreInputField(label: "Username", placeholder: "Enter username", text: $viewModel.username)
///             // ... other fields
///
///             Button("Submit") {
///                 Task { await viewModel.submit() }
///             }
///             .buttonStyle(JukeCoreButtonStyle())
///             .disabled(viewModel.isLoading)
///
///             JukeCoreStatusBanner(message: viewModel.errorMessage, variant: .error)
///             JukeCoreStatusBanner(message: viewModel.successMessage, variant: .success)
///         }
///     }
/// }
/// ```
@MainActor
public final class JukeAuthViewModel: ObservableObject {
    // MARK: - Form Fields

    /// The username field value.
    @Published public var username: String = ""

    /// The email field value (used for registration).
    @Published public var email: String = ""

    /// The password field value.
    @Published public var password: String = ""

    /// The password confirmation field value (used for registration).
    @Published public var passwordConfirm: String = ""

    // MARK: - Mode State

    /// Whether the form is in registration mode (vs login mode).
    @Published public var isRegistering: Bool = false

    // MARK: - Loading State

    /// Whether a submission is in progress.
    @Published public var isLoading: Bool = false

    // MARK: - Message State

    /// Error message to display (from validation or API).
    @Published public var errorMessage: String?

    /// Success message to display.
    @Published public var successMessage: String?

    // MARK: - Resend Verification State

    /// Whether to show the "resend verification" action.
    @Published public var showResendAction: Bool = false

    /// Whether a resend operation is in progress.
    @Published public var isResending: Bool = false

    /// Success message for resend operation.
    @Published public var resendMessage: String?

    /// Error message for resend operation.
    @Published public var resendError: String?

    // MARK: - Private Properties

    private let session: JukeSessionStore
    private let authService: JukeAuthService
    private let configuration: JukeAppConfiguration
    private let registrationDisabledMessage = "Registration is temporarily disabled. Please try again later."

    // MARK: - Computed Properties

    /// Whether registration is disabled by configuration.
    public var isRegistrationDisabled: Bool {
        configuration.isRegistrationDisabled
    }

    // MARK: - Initialization

    /// Creates an auth view model.
    /// - Parameters:
    ///   - session: The session store for login/register operations.
    ///   - authService: The auth service for resend verification. Defaults to a new instance.
    ///   - configuration: App configuration for registration disabled check. Defaults to `.shared`.
    public init(
        session: JukeSessionStore,
        authService: JukeAuthService = JukeAuthService(),
        configuration: JukeAppConfiguration = .shared
    ) {
        self.session = session
        self.authService = authService
        self.configuration = configuration
    }

    // MARK: - Mode Switching

    /// Sets the form mode (login or registration).
    /// - Parameter registering: Whether to show registration form.
    public func setMode(registering: Bool) {
        if configuration.isRegistrationDisabled && registering {
            errorMessage = registrationDisabledMessage
            return
        }
        guard registering != isRegistering else { return }
        isRegistering = registering
        clearMessages()
    }

    // MARK: - Form Submission

    /// Submits the form (login or registration).
    public func submit() async {
        clearMessages()

        // Validate required fields
        let trimmedUsername = username.trimmingCharacters(in: .whitespaces)
        guard !trimmedUsername.isEmpty else {
            errorMessage = "Username is required."
            return
        }
        guard !password.isEmpty else {
            errorMessage = "Password is required."
            return
        }

        if isRegistering {
            await submitRegistration(username: trimmedUsername)
        } else {
            await submitLogin(username: trimmedUsername)
        }
    }

    private func submitLogin(username: String) async {
        isLoading = true
        defer { isLoading = false }

        do {
            try await session.login(username: username, password: password)
            clearForm()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func submitRegistration(username: String) async {
        if configuration.isRegistrationDisabled {
            errorMessage = registrationDisabledMessage
            return
        }

        // Additional validation for registration
        let trimmedEmail = email.trimmingCharacters(in: .whitespaces)
        guard !trimmedEmail.isEmpty else {
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

        isLoading = true
        defer { isLoading = false }

        do {
            let message = try await session.register(
                username: username,
                email: trimmedEmail,
                password: password,
                passwordConfirm: passwordConfirm
            )
            successMessage = message
            clearFormPasswords()
            isRegistering = false
        } catch {
            let desc = error.localizedDescription
            errorMessage = desc
            // Show resend action if server indicates account already exists
            if desc.lowercased().contains("already exists") || desc.lowercased().contains("exists") {
                showResendAction = true
            }
        }
    }

    // MARK: - Resend Verification

    /// Resends the verification email to the current email address.
    public func resendVerification() async {
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

    // MARK: - Private Helpers

    private func clearMessages() {
        errorMessage = nil
        successMessage = nil
        showResendAction = false
        resendMessage = nil
        resendError = nil
    }

    private func clearForm() {
        password = ""
        passwordConfirm = ""
    }

    private func clearFormPasswords() {
        password = ""
        passwordConfirm = ""
    }
}
