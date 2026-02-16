import SwiftUI
import JukeKit

struct AuthView: View {
    @ObservedObject var session: JukeSessionStore
    @StateObject private var viewModel: LoginViewModel

    init(session: JukeSessionStore) {
        self.session = session
        _viewModel = StateObject(wrappedValue: LoginViewModel())
    }

    var body: some View {
        ZStack {
            SCBackground()

            ScrollView {
                VStack(spacing: 24) {
                    // Logo area
                    VStack(spacing: 8) {
                        Text("ShotClock")
                            .font(.system(size: 36, weight: .bold))
                            .foregroundColor(SCPalette.text)
                            .neonGlow(color: SCPalette.accent)
                        Text("Power Hour, powered up.")
                            .font(.subheadline)
                            .foregroundColor(SCPalette.muted)
                    }
                    .padding(.top, 60)
                    .padding(.bottom, 20)

                    // Verification deep link result
                    if let verificationMsg = session.verificationMessage {
                        SCStatusBanner(message: verificationMsg, variant: .success)
                            .padding(.horizontal, 24)
                            .onAppear {
                                DispatchQueue.main.asyncAfter(deadline: .now() + 5) {
                                    session.verificationMessage = nil
                                }
                            }
                    }

                    SCCard {
                        VStack(spacing: 18) {
                            SCInputField(
                                label: "Username",
                                placeholder: "Enter username",
                                text: $viewModel.username,
                                textContentType: .username
                            )

                            SCInputField(
                                label: "Password",
                                placeholder: "Enter password",
                                text: $viewModel.password,
                                kind: .secure,
                                textContentType: .password
                            )

                            SCStatusBanner(message: viewModel.errorMessage, variant: .error)

                            Button {
                                Task {
                                    await viewModel.login(session: session)
                                }
                            } label: {
                                if viewModel.isLoading {
                                    SCSpinner()
                                } else {
                                    Text("Log In")
                                }
                            }
                            .buttonStyle(SCButtonStyle(variant: .primary))
                            .disabled(viewModel.isLoading)

                            // Divider
                            HStack {
                                Rectangle()
                                    .fill(SCPalette.border)
                                    .frame(height: 1)
                                Text("or")
                                    .font(.caption)
                                    .foregroundColor(SCPalette.muted)
                                Rectangle()
                                    .fill(SCPalette.border)
                                    .frame(height: 1)
                            }
                            .padding(.vertical, 8)

                            // Register button - redirects to Juke app or web
                            Button {
                                openRegistration()
                            } label: {
                                Text("Create Account")
                            }
                            .buttonStyle(SCButtonStyle(variant: .secondary))

                            Text("Registration is handled through the Juke app.")
                                .font(.caption)
                                .foregroundColor(SCPalette.muted)
                                .multilineTextAlignment(.center)
                        }
                    }
                    .padding(.horizontal, 24)
                }
            }
        }
    }

    private func openRegistration() {
        // Try to open the Juke app for registration
        if !JukeDeepLinkHandler.openJukeAppForRegistration() {
            // Fall back to web registration
            if let webURL = JukeDeepLinkHandler.webRegistrationURL(configuration: .shared) {
                JukeDeepLinkHandler.openURL(webURL)
            }
        }
    }
}

// MARK: - Login ViewModel (ShotClock-specific, login-only)

@MainActor
final class LoginViewModel: ObservableObject {
    @Published var username = ""
    @Published var password = ""
    @Published var isLoading = false
    @Published var errorMessage: String?

    func login(session: JukeSessionStore) async {
        errorMessage = nil

        guard !username.trimmingCharacters(in: .whitespaces).isEmpty else {
            errorMessage = "Username is required."
            return
        }
        guard !password.isEmpty else {
            errorMessage = "Password is required."
            return
        }

        isLoading = true
        defer { isLoading = false }

        do {
            try await session.login(
                username: username.trimmingCharacters(in: .whitespaces),
                password: password
            )
            // Clear form on success
            password = ""
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

#Preview {
    AuthView(session: JukeSessionStore(keyPrefix: "shotclock"))
}
