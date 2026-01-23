//
//  AuthView.swift
//  TuneTrivia
//
//  Created by Juke Platform on 2026-01-22.
//

import SwiftUI

struct AuthView: View {
    @EnvironmentObject private var session: SessionStore

    @State private var mode: AuthMode = .login
    @State private var username = ""
    @State private var email = ""
    @State private var password = ""
    @State private var passwordConfirm = ""
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var successMessage: String?

    // Field-level validation errors
    @State private var usernameError: String?
    @State private var emailError: String?
    @State private var passwordError: String?
    @State private var passwordConfirmError: String?

    enum AuthMode {
        case login
        case register
    }

    private var isFormValid: Bool {
        switch mode {
        case .login:
            return !username.isEmpty && !password.isEmpty
        case .register:
            return !username.isEmpty && !email.isEmpty && !password.isEmpty && !passwordConfirm.isEmpty
        }
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

                    // Form card
                    TuneTriviaCard {
                        VStack(spacing: 20) {
                            // Success message
                            if let successMessage = successMessage {
                                TuneTriviaStatusBanner(message: successMessage, variant: .success)
                            }

                            // Error message
                            if let errorMessage = errorMessage {
                                TuneTriviaStatusBanner(message: errorMessage, variant: .error)
                            }

                            // Form fields
                            TuneTriviaInputField(
                                label: "Username",
                                placeholder: "Enter your username",
                                text: $username,
                                textContentType: .username,
                                error: usernameError
                            )

                            if mode == .register {
                                TuneTriviaInputField(
                                    label: "Email",
                                    placeholder: "Enter your email",
                                    text: $email,
                                    keyboard: .emailAddress,
                                    textContentType: .emailAddress,
                                    error: emailError
                                )
                            }

                            TuneTriviaInputField(
                                label: "Password",
                                placeholder: "Enter your password",
                                text: $password,
                                kind: .secure,
                                textContentType: mode == .login ? .password : .newPassword,
                                error: passwordError
                            )

                            if mode == .register {
                                TuneTriviaInputField(
                                    label: "Confirm Password",
                                    placeholder: "Confirm your password",
                                    text: $passwordConfirm,
                                    kind: .secure,
                                    textContentType: .newPassword,
                                    error: passwordConfirmError
                                )
                            }

                            // Submit button
                            Button {
                                Task {
                                    await submit()
                                }
                            } label: {
                                if isLoading {
                                    TuneTriviaSpinner()
                                } else {
                                    Text(mode == .login ? "Sign In" : "Create Account")
                                }
                            }
                            .buttonStyle(TuneTriviaButtonStyle(variant: .primary))
                            .disabled(!isFormValid || isLoading)
                            .opacity(isFormValid ? 1 : 0.6)

                            // Toggle mode
                            Button {
                                toggleMode()
                            } label: {
                                Text(mode == .login ? "Don't have an account? Sign Up" : "Already have an account? Sign In")
                                    .font(.subheadline)
                            }
                            .buttonStyle(TuneTriviaButtonStyle(variant: .link, isFullWidth: false))
                        }
                    }
                    .padding(.horizontal, 24)
                }
                .padding(.bottom, 40)
            }
        }
    }

    private func toggleMode() {
        mode = mode == .login ? .register : .login
        clearErrors()
        clearFields()
    }

    private func submit() async {
        guard isFormValid else { return }

        clearErrors()
        isLoading = true
        defer { isLoading = false }

        do {
            switch mode {
            case .login:
                try await session.login(username: username, password: password)
            case .register:
                if !validateRegistration() {
                    return
                }
                let message = try await session.register(
                    username: username,
                    email: email,
                    password: password,
                    passwordConfirm: passwordConfirm
                )
                successMessage = message
                mode = .login
                clearFields()
            }
        } catch let error as APIError {
            errorMessage = error.errorDescription
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func validateRegistration() -> Bool {
        var isValid = true

        if username.count < 3 {
            usernameError = "Username must be at least 3 characters"
            isValid = false
        }

        if !email.contains("@") || !email.contains(".") {
            emailError = "Please enter a valid email address"
            isValid = false
        }

        if password.count < 8 {
            passwordError = "Password must be at least 8 characters"
            isValid = false
        }

        if password != passwordConfirm {
            passwordConfirmError = "Passwords do not match"
            isValid = false
        }

        return isValid
    }

    private func clearErrors() {
        errorMessage = nil
        successMessage = nil
        usernameError = nil
        emailError = nil
        passwordError = nil
        passwordConfirmError = nil
    }

    private func clearFields() {
        username = ""
        email = ""
        password = ""
        passwordConfirm = ""
    }
}

struct AuthView_Previews: PreviewProvider {
    static var previews: some View {
        AuthView()
            .environmentObject(SessionStore())
    }
}
