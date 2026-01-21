import SwiftUI

struct AuthView: View {
    @EnvironmentObject var session: SessionStore
    @StateObject private var viewModel = AuthViewModel()

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
                            // Mode toggle
                            HStack(spacing: 0) {
                                SCChip(label: "Login", isActive: !viewModel.isRegistering) {
                                    viewModel.isRegistering = false
                                }
                                SCChip(label: "Register", isActive: viewModel.isRegistering) {
                                    viewModel.isRegistering = true
                                }
                            }

                            SCInputField(
                                label: "Username",
                                placeholder: "Enter username",
                                text: $viewModel.username,
                                textContentType: .username
                            )

                            if viewModel.isRegistering {
                                SCInputField(
                                    label: "Email",
                                    placeholder: "Enter email",
                                    text: $viewModel.email,
                                    keyboard: .emailAddress,
                                    textContentType: .emailAddress
                                )
                            }

                            SCInputField(
                                label: "Password",
                                placeholder: "Enter password",
                                text: $viewModel.password,
                                kind: .secure,
                                textContentType: viewModel.isRegistering ? .newPassword : .password
                            )

                            if viewModel.isRegistering {
                                SCInputField(
                                    label: "Confirm Password",
                                    placeholder: "Re-enter password",
                                    text: $viewModel.passwordConfirm,
                                    kind: .secure,
                                    textContentType: .newPassword
                                )
                            }

                            SCStatusBanner(message: viewModel.errorMessage, variant: .error)
                            SCStatusBanner(message: viewModel.successMessage, variant: .success)

                            Button {
                                Task {
                                    await viewModel.submit(session: session)
                                }
                            } label: {
                                if viewModel.isLoading {
                                    SCSpinner()
                                } else {
                                    Text(viewModel.isRegistering ? "Create Account" : "Log In")
                                }
                            }
                            .buttonStyle(SCButtonStyle(variant: .primary))
                            .disabled(viewModel.isLoading)
                        }
                    }
                    .padding(.horizontal, 24)
                }
            }
        }
    }
}

#Preview {
    AuthView()
        .environmentObject(SessionStore())
}
