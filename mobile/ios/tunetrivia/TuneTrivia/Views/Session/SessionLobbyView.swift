//
//  SessionLobbyView.swift
//  TuneTrivia
//
//  Created by Juke Platform on 2026-01-23.
//

import SwiftUI

struct SessionLobbyView: View {
    @EnvironmentObject private var session: SessionStore
    @Environment(\.dismiss) private var dismiss

    let sessionId: Int

    @State private var sessionDetail: SessionDetailResponse?
    @State private var isLoading = true
    @State private var errorMessage: String?
    @State private var isStartingGame = false
    @State private var navigateToGame = false
    @State private var showAddPlayerSheet = false
    @State private var newPlayerName = ""

    private let tuneTriviaService = TuneTriviaService()
    private let pollTimer = Timer.publish(every: 3, on: .main, in: .common).autoconnect()

    var body: some View {
        ZStack {
            TuneTriviaBackground()

            if isLoading && sessionDetail == nil {
                VStack(spacing: 16) {
                    TuneTriviaSpinner()
                    Text("Loading game...")
                        .foregroundColor(TuneTriviaPalette.muted)
                }
            } else if let detail = sessionDetail {
                ScrollView {
                    VStack(spacing: 24) {
                        // Game Code Card
                        GameCodeCard(code: detail.session.code, name: detail.session.name)
                            .padding(.horizontal, 24)
                            .padding(.top, 20)

                        // Game Info
                        TuneTriviaCard(accentColor: TuneTriviaPalette.secondary) {
                            HStack(spacing: 16) {
                                InfoPill(icon: "music.note", value: "\(detail.session.maxSongs) songs")
                                InfoPill(icon: "clock", value: "\(detail.session.secondsPerSong)s each")
                                InfoPill(
                                    icon: detail.session.mode == .host ? "person.fill" : "person.3.fill",
                                    value: detail.session.mode.displayName
                                )
                            }
                        }
                        .padding(.horizontal, 24)

                        // Players Section
                        VStack(alignment: .leading, spacing: 12) {
                            HStack {
                                Text("Players (\(detail.players.count))")
                                    .font(.headline)
                                    .foregroundColor(TuneTriviaPalette.text)

                                Spacer()

                                if isHost(detail: detail) && detail.session.mode == .host {
                                    Button {
                                        showAddPlayerSheet = true
                                    } label: {
                                        Image(systemName: "plus.circle.fill")
                                            .foregroundColor(TuneTriviaPalette.accent)
                                    }
                                }
                            }
                            .padding(.horizontal, 24)

                            if detail.players.isEmpty {
                                TuneTriviaCard {
                                    Text("No players yet. Share the code!")
                                        .foregroundColor(TuneTriviaPalette.muted)
                                        .frame(maxWidth: .infinity)
                                }
                                .padding(.horizontal, 24)
                            } else {
                                ForEach(detail.players) { player in
                                    PlayerRow(player: player)
                                        .padding(.horizontal, 24)
                                }
                            }
                        }

                        // Tracks Section (for host)
                        if isHost(detail: detail) {
                            VStack(alignment: .leading, spacing: 12) {
                                HStack {
                                    Text("Tracks (\(detail.rounds.count)/\(detail.session.maxSongs))")
                                        .font(.headline)
                                        .foregroundColor(TuneTriviaPalette.text)

                                    Spacer()

                                    NavigationLink {
                                        AddTracksView(sessionId: sessionId, maxSongs: detail.session.maxSongs, currentCount: detail.rounds.count)
                                    } label: {
                                        Text("Add Tracks")
                                            .font(.subheadline.weight(.medium))
                                            .foregroundColor(TuneTriviaPalette.accent)
                                    }
                                }
                                .padding(.horizontal, 24)

                                if detail.rounds.isEmpty {
                                    TuneTriviaCard {
                                        Text("Add some tracks to get started!")
                                            .foregroundColor(TuneTriviaPalette.muted)
                                            .frame(maxWidth: .infinity)
                                    }
                                    .padding(.horizontal, 24)
                                } else {
                                    ForEach(detail.rounds.prefix(5)) { round in
                                        TrackRow(round: round)
                                            .padding(.horizontal, 24)
                                    }
                                    if detail.rounds.count > 5 {
                                        Text("+ \(detail.rounds.count - 5) more tracks")
                                            .font(.caption)
                                            .foregroundColor(TuneTriviaPalette.muted)
                                            .padding(.horizontal, 24)
                                    }
                                }
                            }
                        }

                        Spacer(minLength: 100)
                    }
                }

                // Bottom Action Button
                if isHost(detail: detail) {
                    VStack {
                        Spacer()

                        Button {
                            Task {
                                await startGame()
                            }
                        } label: {
                            if isStartingGame {
                                TuneTriviaSpinner()
                            } else {
                                Text("Start Game")
                            }
                        }
                        .buttonStyle(TuneTriviaButtonStyle(variant: .primary))
                        .disabled(!canStartGame(detail: detail) || isStartingGame)
                        .opacity(canStartGame(detail: detail) ? 1 : 0.6)
                        .padding(.horizontal, 24)
                        .padding(.bottom, 20)
                        .background(
                            LinearGradient(
                                colors: [TuneTriviaPalette.background.opacity(0), TuneTriviaPalette.background],
                                startPoint: .top,
                                endPoint: .bottom
                            )
                            .frame(height: 100)
                            .allowsHitTesting(false),
                            alignment: .bottom
                        )
                    }
                } else {
                    VStack {
                        Spacer()

                        TuneTriviaCard {
                            HStack {
                                Image(systemName: "hourglass")
                                    .foregroundColor(TuneTriviaPalette.secondary)
                                Text("Waiting for host to start...")
                                    .foregroundColor(TuneTriviaPalette.muted)
                            }
                        }
                        .padding(.horizontal, 24)
                        .padding(.bottom, 20)
                    }
                }
            } else if let error = errorMessage {
                VStack(spacing: 16) {
                    Image(systemName: "exclamationmark.triangle")
                        .font(.largeTitle)
                        .foregroundColor(TuneTriviaPalette.accent)
                    Text(error)
                        .foregroundColor(TuneTriviaPalette.muted)
                        .multilineTextAlignment(.center)
                    Button("Try Again") {
                        Task { await loadSession() }
                    }
                    .buttonStyle(TuneTriviaButtonStyle(variant: .secondary))
                }
                .padding(24)
            }
        }
        .navigationBarTitleDisplayMode(.inline)
        .navigationDestination(isPresented: $navigateToGame) {
            GamePlayView(sessionId: sessionId)
        }
        .sheet(isPresented: $showAddPlayerSheet) {
            AddPlayerSheet(playerName: $newPlayerName) {
                Task { await addPlayer() }
            }
            .presentationDetents([.height(200)])
        }
        .task {
            await loadSession()
        }
        .onReceive(pollTimer) { _ in
            Task { await pollSession() }
        }
    }

    private func isHost(detail: SessionDetailResponse) -> Bool {
        detail.session.hostUsername == session.profile?.username
    }

    private func canStartGame(detail: SessionDetailResponse) -> Bool {
        detail.rounds.count > 0 && detail.players.count > 0
    }

    private func loadSession() async {
        isLoading = true
        errorMessage = nil

        do {
            sessionDetail = try await tuneTriviaService.getSession(id: sessionId, token: session.token)

            // Check if game has started
            if sessionDetail?.session.status == .playing {
                navigateToGame = true
            }
        } catch let error as APIError {
            errorMessage = error.errorDescription
        } catch {
            errorMessage = error.localizedDescription
        }

        isLoading = false
    }

    private func pollSession() async {
        guard sessionDetail?.session.status == .lobby else { return }

        do {
            sessionDetail = try await tuneTriviaService.getSession(id: sessionId, token: session.token)

            if sessionDetail?.session.status == .playing {
                navigateToGame = true
            }
        } catch {
            // Silently fail on poll errors
        }
    }

    private func startGame() async {
        guard let token = session.token else { return }

        isStartingGame = true
        defer { isStartingGame = false }

        do {
            _ = try await tuneTriviaService.startGame(sessionId: sessionId, token: token)
            navigateToGame = true
        } catch let error as APIError {
            errorMessage = error.errorDescription
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func addPlayer() async {
        guard let token = session.token, !newPlayerName.isEmpty else { return }

        do {
            _ = try await tuneTriviaService.addManualPlayer(
                sessionId: sessionId,
                displayName: newPlayerName,
                token: token
            )
            newPlayerName = ""
            showAddPlayerSheet = false
            await loadSession()
        } catch {
            // Handle error
        }
    }
}

// MARK: - Subviews

struct GameCodeCard: View {
    let code: String
    let name: String

    var body: some View {
        TuneTriviaCard(accentColor: TuneTriviaPalette.accent) {
            VStack(spacing: 12) {
                Text(name)
                    .font(.headline)
                    .foregroundColor(TuneTriviaPalette.text)

                Text(code)
                    .font(.system(size: 48, weight: .bold, design: .monospaced))
                    .foregroundColor(TuneTriviaPalette.accent)
                    .tracking(8)

                Button {
                    UIPasteboard.general.string = code
                } label: {
                    HStack(spacing: 4) {
                        Image(systemName: "doc.on.doc")
                        Text("Copy Code")
                    }
                    .font(.caption.weight(.medium))
                    .foregroundColor(TuneTriviaPalette.secondary)
                }
            }
        }
    }
}

struct InfoPill: View {
    let icon: String
    let value: String

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: icon)
                .font(.caption)
            Text(value)
                .font(.caption.weight(.medium))
        }
        .foregroundColor(TuneTriviaPalette.text)
        .padding(.horizontal, 10)
        .padding(.vertical, 6)
        .background(
            Capsule()
                .fill(TuneTriviaPalette.background)
        )
    }
}

struct PlayerRow: View {
    let player: TuneTriviaPlayer

    var body: some View {
        HStack(spacing: 12) {
            Circle()
                .fill(TuneTriviaPalette.secondary.opacity(0.2))
                .frame(width: 40, height: 40)
                .overlay(
                    Text(String(player.displayName.prefix(1)).uppercased())
                        .font(.headline)
                        .foregroundColor(TuneTriviaPalette.secondary)
                )

            VStack(alignment: .leading, spacing: 2) {
                Text(player.displayName)
                    .font(.subheadline.weight(.medium))
                    .foregroundColor(TuneTriviaPalette.text)

                if player.isHost {
                    Text("Host")
                        .font(.caption)
                        .foregroundColor(TuneTriviaPalette.accent)
                }
            }

            Spacer()

            Text("\(player.totalScore) pts")
                .font(.caption)
                .foregroundColor(TuneTriviaPalette.muted)
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(TuneTriviaPalette.panel)
        )
    }
}

struct TrackRow: View {
    let round: TuneTriviaRound

    var body: some View {
        HStack(spacing: 12) {
            RoundedRectangle(cornerRadius: 8)
                .fill(TuneTriviaPalette.muted.opacity(0.2))
                .frame(width: 44, height: 44)
                .overlay(
                    Image(systemName: "music.note")
                        .foregroundColor(TuneTriviaPalette.muted)
                )

            VStack(alignment: .leading, spacing: 2) {
                Text(round.trackName)
                    .font(.subheadline.weight(.medium))
                    .foregroundColor(TuneTriviaPalette.text)
                    .lineLimit(1)

                Text(round.artistName)
                    .font(.caption)
                    .foregroundColor(TuneTriviaPalette.muted)
                    .lineLimit(1)
            }

            Spacer()

            Text("#\(round.roundNumber)")
                .font(.caption.weight(.medium))
                .foregroundColor(TuneTriviaPalette.muted)
        }
        .padding(12)
        .background(
            RoundedRectangle(cornerRadius: 12)
                .fill(TuneTriviaPalette.panel)
        )
    }
}

struct AddPlayerSheet: View {
    @Binding var playerName: String
    let onAdd: () -> Void

    var body: some View {
        VStack(spacing: 20) {
            Text("Add Player")
                .font(.headline)
                .foregroundColor(TuneTriviaPalette.text)

            TextField("Player Name", text: $playerName)
                .textFieldStyle(.roundedBorder)
                .padding(.horizontal)

            Button("Add Player", action: onAdd)
                .buttonStyle(TuneTriviaButtonStyle(variant: .primary))
                .disabled(playerName.isEmpty)
                .padding(.horizontal)
        }
        .padding()
        .background(TuneTriviaPalette.background)
    }
}

struct SessionLobbyView_Previews: PreviewProvider {
    static var previews: some View {
        NavigationStack {
            SessionLobbyView(sessionId: 1)
                .environmentObject(SessionStore())
        }
    }
}
