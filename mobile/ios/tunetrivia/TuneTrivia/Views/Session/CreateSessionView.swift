//
//  CreateSessionView.swift
//  TuneTrivia
//
//  Created by Juke Platform on 2026-01-23.
//

import SwiftUI

struct CreateSessionView: View {
    @EnvironmentObject private var session: SessionStore
    @Environment(\.dismiss) private var dismiss

    @State private var gameName = ""
    @State private var mode: SessionMode = .host
    @State private var numberOfSongs = 10
    @State private var secondsPerSong = 20
    @State private var enableTrivia = true
    @State private var isLoading = false
    @State private var errorMessage: String?

    @State private var createdSession: SessionDetailResponse?
    @State private var navigateToLobby = false

    private let tuneTriviaService = TuneTriviaService()

    var body: some View {
        ZStack {
            TuneTriviaBackground()

            ScrollView {
                VStack(spacing: 24) {
                    // Header
                    VStack(spacing: 8) {
                        Text("Create Game")
                            .font(.system(size: 28, weight: .bold, design: .rounded))
                            .foregroundColor(TuneTriviaPalette.text)

                        Text("Set up your Name That Tune game")
                            .font(.subheadline)
                            .foregroundColor(TuneTriviaPalette.muted)
                    }
                    .padding(.top, 20)

                    if let errorMessage = errorMessage {
                        TuneTriviaStatusBanner(message: errorMessage, variant: .error)
                            .padding(.horizontal, 24)
                    }

                    // Settings Card
                    TuneTriviaCard {
                        VStack(spacing: 20) {
                            // Game Name
                            TuneTriviaInputField(
                                label: "Game Name",
                                placeholder: "Friday Night Trivia",
                                text: $gameName,
                                textContentType: .name,
                                error: nil
                            )

                            // Mode Selection
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Game Mode")
                                    .font(.subheadline.weight(.medium))
                                    .foregroundColor(TuneTriviaPalette.text)

                                ForEach(SessionMode.allCases, id: \.self) { modeOption in
                                    ModeOptionButton(
                                        mode: modeOption,
                                        isSelected: mode == modeOption
                                    ) {
                                        mode = modeOption
                                    }
                                }
                            }

                            // Number of Songs
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Number of Songs: \(numberOfSongs)")
                                    .font(.subheadline.weight(.medium))
                                    .foregroundColor(TuneTriviaPalette.text)

                                Slider(
                                    value: Binding(
                                        get: { Double(numberOfSongs) },
                                        set: { numberOfSongs = Int($0) }
                                    ),
                                    in: 5...30,
                                    step: 1
                                )
                                .tint(TuneTriviaPalette.accent)
                            }

                            // Seconds per Song
                            VStack(alignment: .leading, spacing: 8) {
                                Text("Seconds per Song: \(secondsPerSong)")
                                    .font(.subheadline.weight(.medium))
                                    .foregroundColor(TuneTriviaPalette.text)

                                Slider(
                                    value: Binding(
                                        get: { Double(secondsPerSong) },
                                        set: { secondsPerSong = Int($0) }
                                    ),
                                    in: 10...30,
                                    step: 5
                                )
                                .tint(TuneTriviaPalette.accent)
                            }

                            // Enable Trivia Toggle
                            Toggle(isOn: $enableTrivia) {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text("Bonus Trivia")
                                        .font(.subheadline.weight(.medium))
                                        .foregroundColor(TuneTriviaPalette.text)
                                    Text("Extra trivia question per round (+50 pts)")
                                        .font(.caption)
                                        .foregroundColor(TuneTriviaPalette.muted)
                                }
                            }
                            .tint(TuneTriviaPalette.secondary)
                        }
                    }
                    .padding(.horizontal, 24)

                    // Create Button
                    Button {
                        Task {
                            await createGame()
                        }
                    } label: {
                        if isLoading {
                            TuneTriviaSpinner()
                        } else {
                            Text("Create Game")
                        }
                    }
                    .buttonStyle(TuneTriviaButtonStyle(variant: .primary))
                    .disabled(gameName.isEmpty || isLoading)
                    .opacity(gameName.isEmpty ? 0.6 : 1)
                    .padding(.horizontal, 24)

                    Spacer(minLength: 40)
                }
            }
        }
        .navigationBarTitleDisplayMode(.inline)
        .navigationDestination(isPresented: $navigateToLobby) {
            if let createdSession = createdSession {
                SessionLobbyView(sessionId: createdSession.id)
            }
        }
    }

    private func createGame() async {
        guard let token = session.token else { return }

        isLoading = true
        errorMessage = nil
        defer { isLoading = false }

        do {
            createdSession = try await tuneTriviaService.createSession(
                name: gameName,
                mode: mode,
                maxSongs: numberOfSongs,
                secondsPerSong: secondsPerSong,
                enableTrivia: enableTrivia,
                token: token
            )
            navigateToLobby = true
        } catch let error as APIError {
            errorMessage = error.errorDescription
        } catch {
            errorMessage = error.localizedDescription
        }
    }
}

struct ModeOptionButton: View {
    let mode: SessionMode
    let isSelected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                Image(systemName: isSelected ? "checkmark.circle.fill" : "circle")
                    .foregroundColor(isSelected ? TuneTriviaPalette.accent : TuneTriviaPalette.muted)
                    .font(.title3)

                VStack(alignment: .leading, spacing: 2) {
                    Text(mode.displayName)
                        .font(.subheadline.weight(.medium))
                        .foregroundColor(TuneTriviaPalette.text)

                    Text(mode.description)
                        .font(.caption)
                        .foregroundColor(TuneTriviaPalette.muted)
                }

                Spacer()
            }
            .padding(12)
            .background(
                RoundedRectangle(cornerRadius: 12)
                    .fill(isSelected ? TuneTriviaPalette.accent.opacity(0.1) : Color.clear)
            )
            .overlay(
                RoundedRectangle(cornerRadius: 12)
                    .stroke(isSelected ? TuneTriviaPalette.accent : TuneTriviaPalette.muted.opacity(0.3), lineWidth: 1)
            )
        }
    }
}

struct CreateSessionView_Previews: PreviewProvider {
    static var previews: some View {
        NavigationStack {
            CreateSessionView()
                .environmentObject(SessionStore())
        }
    }
}
