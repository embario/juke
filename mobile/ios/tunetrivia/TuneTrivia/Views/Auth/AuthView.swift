//
//  AuthView.swift
//  TuneTrivia
//
//  Created by Juke Platform on 2026-01-22.
//

import SwiftUI
import JukeCore

struct AuthView: View {
    @ObservedObject var session: JukeSessionStore
    @StateObject private var viewModel: LoginViewModel

    init(session: JukeSessionStore) {
        self.session = session
        _viewModel = StateObject(wrappedValue: LoginViewModel())
    }

    var body: some View {
        ZStack {
            TuneTriviaBackground()

            ScrollView {
                VStack(spacing: 32) {
                    // Logo and title
                    VStack(spacing: 12) {
                        Image(systemName: "music.quarternote.3")
                            .font(.system(size: 60))
                            .foregroundColor(TuneTriviaPalette.accent)

                        Text("TuneTrivia")
                            .font(.system(size: 36, weight: .bold, design: .rounded))
                            .foregroundColor(TuneTriviaPalette.text)

                        Text("Name That Tune!")
                            .font(.subheadline)
                            .foregroundColor(TuneTriviaPalette.muted)
                    }
                    .padding(.top, 60)

                    // Verification deep link result
                    if let verificationMsg = session.verificationMessage {
                        TuneTriviaStatusBanner(message: verificationMsg, variant: .success)
                            .padding(.horizontal, 24)
                            .onAppear {
                                DispatchQueue.main.asyncAfter(deadline: .now() + 5) {
                                    session.verificationMessage = nil
                                }
                            }
                    }

                    // Form card
                    TuneTriviaCard {
                        VStack(spacing: 20) {
                            TuneTriviaStatusBanner(message: viewModel.errorMessage, variant: .error)

                            TuneTriviaInputField(
                                label: "Username",
                                placeholder: "Enter your username",
                                text: $viewModel.username,
                                textContentType: .username
                            )

                            TuneTriviaInputField(
                                label: "Password",
                                placeholder: "Enter your password",
                                text: $viewModel.password,
                                kind: .secure,
                                textContentType: .password
                            )

                            Button {
                                Task {
                                    await viewModel.login(session: session)
                                }
                            } label: {
                                if viewModel.isLoading {
                                    TuneTriviaSpinner()
                                } else {
                                    Text("Sign In")
                                }
                            }
                            .buttonStyle(TuneTriviaButtonStyle(variant: .primary))
                            .disabled(viewModel.isLoading)

                            // Divider
                            HStack {
                                Rectangle()
                                    .fill(TuneTriviaPalette.border)
                                    .frame(height: 1)
                                Text("or")
                                    .font(.caption)
                                    .foregroundColor(TuneTriviaPalette.muted)
                                Rectangle()
                                    .fill(TuneTriviaPalette.border)
                                    .frame(height: 1)
                            }
                            .padding(.vertical, 8)

                            // Register button - redirects to Juke app or web
                            Button {
                                openRegistration()
                            } label: {
                                Text("Create Account")
                            }
                            .buttonStyle(TuneTriviaButtonStyle(variant: .secondary))

                            Text("Registration is handled through the Juke app.")
                                .font(.caption)
                                .foregroundColor(TuneTriviaPalette.muted)
                                .multilineTextAlignment(.center)
                        }
                    }
                    .padding(.horizontal, 24)
                }
                .padding(.bottom, 40)
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

// MARK: - Login ViewModel (TuneTrivia-specific, login-only)

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
    AuthView(session: JukeSessionStore(keyPrefix: "tunetrivia"))
}
