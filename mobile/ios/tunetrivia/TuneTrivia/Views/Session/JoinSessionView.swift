//
//  JoinSessionView.swift
//  TuneTrivia
//
//  Created by Juke Platform on 2026-01-23.
//

import SwiftUI

struct JoinSessionView: View {
    @EnvironmentObject private var session: SessionStore
    @Environment(\.dismiss) private var dismiss

    @State private var gameCode = ""
    @State private var displayName = ""
    @State private var isLoading = false
    @State private var errorMessage: String?

    @State private var joinedSessionId: Int?
    @State private var navigateToLobby = false

    private let tuneTriviaService = TuneTriviaService()

    // For Party Mode (registered users), we don't need display name
    private var needsDisplayName: Bool {
        session.token == nil
    }

    var body: some View {
        ZStack {
            TuneTriviaBackground()

            ScrollView {
                VStack(spacing: 24) {
                    // Header
                    VStack(spacing: 8) {
                        Text("Join Game")
                            .font(.system(size: 28, weight: .bold, design: .rounded))
                            .foregroundColor(TuneTriviaPalette.text)

                        Text("Enter the game code to join")
                            .font(.subheadline)
                            .foregroundColor(TuneTriviaPalette.muted)
                    }
                    .padding(.top, 20)

                    if let errorMessage = errorMessage {
                        TuneTriviaStatusBanner(message: errorMessage, variant: .error)
                            .padding(.horizontal, 24)
                    }

                    // Join Card
                    TuneTriviaCard {
                        VStack(spacing: 20) {
                            // Game Code
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Game Code")
                                    .font(.subheadline.weight(.medium))
                                    .foregroundColor(TuneTriviaPalette.text)

                                TextField("", text: $gameCode)
                                    .font(.system(size: 32, weight: .bold, design: .monospaced))
                                    .multilineTextAlignment(.center)
                                    .textInputAutocapitalization(.characters)
                                    .autocorrectionDisabled()
                                    .padding()
                                    .background(
                                        RoundedRectangle(cornerRadius: 12)
                                            .fill(TuneTriviaPalette.background)
                                    )
                                    .overlay(
                                        RoundedRectangle(cornerRadius: 12)
                                            .stroke(TuneTriviaPalette.muted.opacity(0.3), lineWidth: 1)
                                    )
                                    .onChange(of: gameCode) { _, newValue in
                                        // Limit to 6 characters and uppercase
                                        gameCode = String(newValue.uppercased().prefix(6))
                                    }
                            }

                            // Display Name (for Host Mode / unregistered)
                            if needsDisplayName {
                                TuneTriviaInputField(
                                    label: "Your Name",
                                    placeholder: "Enter your name",
                                    text: $displayName,
                                    textContentType: .name,
                                    error: nil
                                )
                            }
                        }
                    }
                    .padding(.horizontal, 24)

                    // Join Button
                    Button {
                        Task {
                            await joinGame()
                        }
                    } label: {
                        if isLoading {
                            TuneTriviaSpinner()
                        } else {
                            Text("Join Game")
                        }
                    }
                    .buttonStyle(TuneTriviaButtonStyle(variant: .primary))
                    .disabled(!isFormValid || isLoading)
                    .opacity(isFormValid ? 1 : 0.6)
                    .padding(.horizontal, 24)

                    Spacer(minLength: 40)
                }
            }
        }
        .navigationBarTitleDisplayMode(.inline)
        .navigationDestination(isPresented: $navigateToLobby) {
            if let sessionId = joinedSessionId {
                SessionLobbyView(sessionId: sessionId)
            }
        }
    }

    private var isFormValid: Bool {
        gameCode.count == 6 && (!needsDisplayName || !displayName.isEmpty)
    }

    private func joinGame() async {
        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            let response = try await tuneTriviaService.joinSession(
                code: gameCode,
                displayName: needsDisplayName ? displayName : nil,
                token: session.token
            )
            joinedSessionId = response.session.id
            navigateToLobby = true
        } catch let error as APIError {
            errorMessage = error.errorDescription
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct JoinSessionView_Previews: PreviewProvider {
    static var previews: some View {
        NavigationStack {
            JoinSessionView()
                .environmentObject(SessionStore())
        }
    }
}
