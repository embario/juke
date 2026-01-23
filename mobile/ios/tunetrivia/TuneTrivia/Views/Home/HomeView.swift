//
//  HomeView.swift
//  TuneTrivia
//
//  Created by Juke Platform on 2026-01-22.
//

import SwiftUI

struct HomeView: View {
    @EnvironmentObject private var session: SessionStore

    @State private var mySessions: [TuneTriviaSession] = []
    @State private var isLoadingSessions = false

    private let tuneTriviaService = TuneTriviaService()

    var body: some View {
        NavigationStack {
            ZStack {
                TuneTriviaBackground()

                ScrollView {
                    VStack(spacing: 24) {
                        // Header
                        HStack {
                            VStack(alignment: .leading, spacing: 4) {
                                Text("TuneTrivia")
                                    .font(.system(size: 28, weight: .bold, design: .rounded))
                                    .foregroundColor(TuneTriviaPalette.text)

                                Text("Welcome, \(session.currentUsername)!")
                                    .font(.subheadline)
                                    .foregroundColor(TuneTriviaPalette.muted)
                            }

                            Spacer()

                            Button {
                                session.logout()
                            } label: {
                                Image(systemName: "rectangle.portrait.and.arrow.right")
                                    .font(.title3)
                                    .foregroundColor(TuneTriviaPalette.muted)
                            }
                        }
                        .padding(.horizontal, 24)
                        .padding(.top, 20)

                        // My Sessions section
                        VStack(alignment: .leading, spacing: 16) {
                            HStack {
                                Text("My Games")
                                    .font(.headline)
                                    .foregroundColor(TuneTriviaPalette.text)

                                Spacer()

                                if isLoadingSessions {
                                    ProgressView()
                                        .scaleEffect(0.8)
                                }
                            }
                            .padding(.horizontal, 24)

                            if mySessions.isEmpty && !isLoadingSessions {
                                TuneTriviaCard(accentColor: TuneTriviaPalette.secondary) {
                                    VStack(alignment: .leading, spacing: 8) {
                                        Text("No games yet")
                                            .font(.headline)
                                            .foregroundColor(TuneTriviaPalette.text)

                                        Text("Create a new game or join one with a code!")
                                            .font(.subheadline)
                                            .foregroundColor(TuneTriviaPalette.muted)
                                    }
                                }
                                .padding(.horizontal, 24)
                            } else {
                                ForEach(mySessions) { gameSession in
                                    NavigationLink {
                                        if gameSession.status == .lobby {
                                            SessionLobbyView(sessionId: gameSession.id)
                                        } else {
                                            GamePlayView(sessionId: gameSession.id)
                                        }
                                    } label: {
                                        SessionCard(session: gameSession)
                                    }
                                    .padding(.horizontal, 24)
                                }
                            }
                        }

                        // Leaderboard button
                        NavigationLink {
                            LeaderboardView()
                        } label: {
                            TuneTriviaCard {
                                HStack {
                                    Image(systemName: "trophy.fill")
                                        .foregroundColor(TuneTriviaPalette.highlight)
                                        .font(.title2)

                                    VStack(alignment: .leading, spacing: 2) {
                                        Text("Global Leaderboard")
                                            .font(.headline)
                                            .foregroundColor(TuneTriviaPalette.text)

                                        Text("See top players worldwide")
                                            .font(.caption)
                                            .foregroundColor(TuneTriviaPalette.muted)
                                    }

                                    Spacer()

                                    Image(systemName: "chevron.right")
                                        .foregroundColor(TuneTriviaPalette.muted)
                                }
                            }
                        }
                        .padding(.horizontal, 24)

                        Spacer(minLength: 100)
                    }
                }

                // Bottom action buttons
                VStack {
                    Spacer()

                    VStack(spacing: 12) {
                        NavigationLink {
                            CreateSessionView()
                        } label: {
                            Text("+ Create Game")
                        }
                        .buttonStyle(TuneTriviaButtonStyle(variant: .primary))

                        NavigationLink {
                            JoinSessionView()
                        } label: {
                            Text("Join with Code")
                        }
                        .buttonStyle(TuneTriviaButtonStyle(variant: .link))
                    }
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
            }
        }
        .task {
            await loadSessions()
        }
    }

    private func loadSessions() async {
        guard let token = session.token else { return }

        isLoadingSessions = true
        defer { isLoadingSessions = false }

        do {
            mySessions = try await tuneTriviaService.getMySessions(token: token)
        } catch {
            // Silently fail - just show empty state
            mySessions = []
        }
    }
}

struct SessionCard: View {
    let session: TuneTriviaSession

    var statusColor: Color {
        switch session.status {
        case .lobby: return TuneTriviaPalette.secondary
        case .playing: return TuneTriviaPalette.accent
        case .paused: return TuneTriviaPalette.highlight
        case .finished: return TuneTriviaPalette.muted
        }
    }

    var body: some View {
        TuneTriviaCard {
            HStack {
                VStack(alignment: .leading, spacing: 4) {
                    Text(session.name)
                        .font(.headline)
                        .foregroundColor(TuneTriviaPalette.text)

                    HStack(spacing: 8) {
                        Text(session.mode.displayName)
                            .font(.caption)
                            .foregroundColor(TuneTriviaPalette.muted)

                        Text("•")
                            .foregroundColor(TuneTriviaPalette.muted)

                        Text("\(session.maxSongs) songs")
                            .font(.caption)
                            .foregroundColor(TuneTriviaPalette.muted)
                    }
                }

                Spacer()

                VStack(alignment: .trailing, spacing: 4) {
                    TuneTriviaChip(
                        label: session.status.rawValue.capitalized,
                        color: statusColor
                    )

                    Text(session.code)
                        .font(.caption.monospaced())
                        .foregroundColor(TuneTriviaPalette.muted)
                }
            }
        }
    }
}

struct HomeView_Previews: PreviewProvider {
    static var previews: some View {
        HomeView()
            .environmentObject(SessionStore())
    }
}
