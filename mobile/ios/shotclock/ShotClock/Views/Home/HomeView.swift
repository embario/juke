import SwiftUI

struct HomeView: View {
    @EnvironmentObject var session: SessionStore
    @StateObject private var viewModel = HomeViewModel()

    var body: some View {
        NavigationStack {
            ZStack {
                SCBackground()

                VStack(spacing: 0) {
                    // Header
                    HStack {
                        VStack(alignment: .leading, spacing: 4) {
                            Text("ShotClock")
                                .font(.system(size: 24, weight: .bold))
                                .foregroundColor(SCPalette.text)
                                .neonGlow(color: SCPalette.accent)
                            Text("Hey, \(session.profile?.preferredName ?? "Player")")
                                .font(.subheadline)
                                .foregroundColor(SCPalette.muted)
                        }
                        Spacer()
                        Button {
                            session.logout()
                        } label: {
                            Image(systemName: "rectangle.portrait.and.arrow.right")
                                .foregroundColor(SCPalette.muted)
                                .font(.title3)
                        }
                    }
                    .padding(.horizontal, 24)
                    .padding(.top, 16)
                    .padding(.bottom, 20)

                    // Action Buttons
                    HStack(spacing: 12) {
                        NavigationLink {
                            CreateSessionView()
                        } label: {
                            Label("New Session", systemImage: "plus.circle.fill")
                        }
                        .buttonStyle(SCButtonStyle(variant: .primary))

                        Button {
                            viewModel.isShowingJoinSheet = true
                        } label: {
                            Label("Join", systemImage: "person.badge.plus")
                        }
                        .buttonStyle(SCButtonStyle(variant: .secondary))
                    }
                    .padding(.horizontal, 24)
                    .padding(.bottom, 20)

                    // Session List
                    if viewModel.isLoading && viewModel.sessions.isEmpty {
                        Spacer()
                        SCSpinner()
                        Spacer()
                    } else if viewModel.sessions.isEmpty {
                        Spacer()
                        VStack(spacing: 12) {
                            Image(systemName: "music.note.list")
                                .font(.system(size: 48))
                                .foregroundColor(SCPalette.muted.opacity(0.5))
                            Text("No sessions yet")
                                .font(.headline)
                                .foregroundColor(SCPalette.muted)
                            Text("Create a new Power Hour or join with an invite code.")
                                .font(.subheadline)
                                .foregroundColor(SCPalette.muted.opacity(0.7))
                                .multilineTextAlignment(.center)
                        }
                        .padding(.horizontal, 40)
                        Spacer()
                    } else {
                        ScrollView {
                            LazyVStack(spacing: 12) {
                                ForEach(viewModel.sessions) { gameSession in
                                    NavigationLink {
                                        SessionLobbyView(gameSession: gameSession)
                                    } label: {
                                        SessionRow(gameSession: gameSession)
                                    }
                                }
                            }
                            .padding(.horizontal, 24)
                            .padding(.bottom, 32)
                        }
                        .refreshable {
                            await viewModel.loadSessions(token: session.token)
                        }
                    }

                    if let error = viewModel.errorMessage {
                        SCStatusBanner(message: error, variant: .error)
                            .padding(.horizontal, 24)
                            .padding(.bottom, 16)
                    }
                }
            }
            .sheet(isPresented: $viewModel.isShowingJoinSheet) {
                JoinSessionSheet(viewModel: viewModel, token: session.token)
            }
        }
        .task {
            await viewModel.loadSessions(token: session.token)
        }
    }
}

// MARK: - Session Row

struct SessionRow: View {
    let gameSession: PowerHourSession

    var body: some View {
        SCCard {
            HStack(spacing: 14) {
                // Status indicator
                Circle()
                    .fill(statusColor)
                    .frame(width: 10, height: 10)

                VStack(alignment: .leading, spacing: 4) {
                    Text(gameSession.title)
                        .font(.headline)
                        .foregroundColor(SCPalette.text)
                        .lineLimit(1)

                    HStack(spacing: 12) {
                        Label("\(gameSession.playerCount ?? 0)", systemImage: "person.2.fill")
                        Label("\(gameSession.trackCount ?? 0)", systemImage: "music.note")
                        Text(gameSession.statusLabel)
                            .fontWeight(.medium)
                    }
                    .font(.caption)
                    .foregroundColor(SCPalette.muted)
                }

                Spacer()

                Image(systemName: "chevron.right")
                    .foregroundColor(SCPalette.muted.opacity(0.5))
                    .font(.caption)
            }
        }
    }

    private var statusColor: Color {
        switch gameSession.status {
        case .lobby: return SCPalette.secondary
        case .active: return .green
        case .paused: return .yellow
        case .ended: return SCPalette.muted
        }
    }
}

// MARK: - Join Session Sheet

struct JoinSessionSheet: View {
    @ObservedObject var viewModel: HomeViewModel
    let token: String?
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ZStack {
            SCBackground()

            VStack(spacing: 24) {
                Text("Join Session")
                    .font(.title2.bold())
                    .foregroundColor(SCPalette.text)
                    .padding(.top, 32)

                SCInputField(
                    label: "Invite Code",
                    placeholder: "Enter 8-character code",
                    text: $viewModel.joinCode,
                    textContentType: .oneTimeCode
                )

                SCStatusBanner(message: viewModel.joinError, variant: .error)

                Button {
                    Task {
                        _ = await viewModel.joinSession(token: token)
                    }
                } label: {
                    if viewModel.isJoining {
                        SCSpinner()
                    } else {
                        Text("Join")
                    }
                }
                .buttonStyle(SCButtonStyle(variant: .primary))
                .disabled(viewModel.isJoining)

                Button("Cancel") {
                    dismiss()
                }
                .buttonStyle(SCButtonStyle(variant: .ghost))

                Spacer()
            }
            .padding(.horizontal, 24)
        }
        .presentationDetents([.medium])
    }
}

#Preview {
    HomeView()
        .environmentObject(SessionStore())
}
