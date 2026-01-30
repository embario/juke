import SwiftUI

struct AuthView: View {
    @StateObject private var viewModel: AuthViewModel

    init(session: SessionStore) {
        _viewModel = StateObject(wrappedValue: AuthViewModel(session: session))
    }

    var body: some View {
        NavigationStack {
            ZStack {
                JukeBackground()
                ScrollView(showsIndicators: false) {
                    VStack(alignment: .leading, spacing: 24) {
                        hero
                        JukeCard {
                            VStack(alignment: .leading, spacing: 20) {
                                if viewModel.isRegistrationDisabled {
                                    JukeStatusBanner(
                                        message: "Registration is temporarily disabled while email delivery is offline.",
                                        variant: .warning
                                    )
                                } else {
                                    modeToggle
                                }
                                accountFields
                                securityFields
                                JukeStatusBanner(message: viewModel.successMessage, variant: .success)
                                JukeStatusBanner(message: viewModel.resendMessage, variant: .success)
                                JukeStatusBanner(message: viewModel.errorMessage, variant: .error)
                                JukeStatusBanner(message: viewModel.resendError, variant: .error)
                                if viewModel.showResendAction {
                                    resendButton
                                }
                                submitButton
                                Text("By continuing you agree to keep the vibes immaculate.")
                                    .font(.footnote)
                                    .foregroundColor(JukePalette.muted)
                            }
                        }
                    }
                    .padding(.horizontal, 24)
                    .padding(.vertical, 40)
                }
            }
            .toolbar(.hidden, for: .navigationBar)
        }
    }

    private var hero: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Welcome to Juke")
                .font(.system(size: 36, weight: .bold, design: .rounded))
                .foregroundColor(JukePalette.text)
            Text("Log in to sync your library or create an account to broadcast your sonic fingerprint.")
                .font(.subheadline)
                .foregroundColor(JukePalette.muted)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private enum AuthMode: String, CaseIterable, Identifiable {
        case login = "Log In"
        case register = "Register"

        var id: Self { self }
    }

    private var currentMode: AuthMode {
        viewModel.isRegistering ? .register : .login
    }

    private var modeToggle: some View {
        HStack(spacing: 12) {
            ForEach(AuthMode.allCases) { mode in
                Button(mode.rawValue) {
                    viewModel.setMode(registering: mode == .register)
                }
                .buttonStyle(.plain)
                .padding(.vertical, 10)
                .frame(maxWidth: .infinity)
                .background(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .fill(currentMode == mode ? JukePalette.accent.opacity(0.18) : Color.clear)
                )
                .overlay(
                    RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .stroke(currentMode == mode ? JukePalette.accent : JukePalette.border, lineWidth: 1)
                )
                .foregroundColor(currentMode == mode ? JukePalette.text : JukePalette.muted)
            }
        }
    }

    private var accountFields: some View {
        VStack(spacing: 16) {
            JukeInputField(
                label: "Username",
                placeholder: "your-handle",
                text: $viewModel.username,
                textContentType: .username
            )
            if viewModel.isRegistering {
                JukeInputField(
                    label: "Email",
                    placeholder: "you@juke.fm",
                    text: $viewModel.email,
                    keyboard: .emailAddress,
                    textContentType: .emailAddress
                )
            }
        }
    }

    private var securityFields: some View {
        VStack(spacing: 16) {
            JukeInputField(
                label: "Password",
                placeholder: "••••••••",
                text: $viewModel.password,
                kind: .secure,
                textContentType: .password
            )
            if viewModel.isRegistering {
                JukeInputField(
                    label: "Confirm Password",
                    placeholder: "Match the magic",
                    text: $viewModel.passwordConfirm,
                    kind: .secure,
                    textContentType: .password
                )
            }
        }
    }

    private var resendButton: some View {
        Button(action: resendVerification) {
            Text(viewModel.isResending ? "Resending…" : "Resend verification email")
                .font(.subheadline)
                .foregroundColor(JukePalette.accent)
        }
        .buttonStyle(.plain)
        .disabled(viewModel.isResending || viewModel.email.trimmingCharacters(in: .whitespaces).isEmpty)
        .opacity(viewModel.isResending || viewModel.email.trimmingCharacters(in: .whitespaces).isEmpty ? 0.5 : 1)
    }

    private var submitButton: some View {
        Button(action: submit) {
            if viewModel.isLoading {
                HStack {
                    Spacer()
                    JukeSpinner()
                    Spacer()
                }
            } else {
                Text(viewModel.isRegistering ? "Create Account" : "Log In")
                    .fontWeight(.semibold)
            }
        }
        .buttonStyle(JukeButtonStyle())
        .disabled(!canSubmit || viewModel.isLoading)
        .opacity(!canSubmit || viewModel.isLoading ? 0.6 : 1)
    }

    private var canSubmit: Bool {
        if viewModel.username.trimmingCharacters(in: .whitespaces).isEmpty {
            return false
        }
        if viewModel.password.isEmpty {
            return false
        }
        if viewModel.isRegistering {
            return !viewModel.email.trimmingCharacters(in: .whitespaces).isEmpty && !viewModel.passwordConfirm.isEmpty
        }
        return true
    }

    private func submit() {
        Task {
            await viewModel.submit()
        }
    }

    private func resendVerification() {
        Task {
            await viewModel.resendVerification()
        }
    }
}

#Preview {
    AuthView(session: SessionStore())
}
