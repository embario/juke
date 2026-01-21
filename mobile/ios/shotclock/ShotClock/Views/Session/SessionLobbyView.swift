import SwiftUI

struct SessionLobbyView: View {
    @EnvironmentObject var session: SessionStore
    @EnvironmentObject var spotify: SpotifyManager
    @StateObject private var viewModel: SessionLobbyViewModel
    @State private var copiedInvite = false

    init(gameSession: PowerHourSession) {
        _viewModel = StateObject(wrappedValue: SessionLobbyViewModel(session: gameSession))
    }

    var body: some View {
        ZStack {
            SCBackground()

            ScrollView {
                VStack(spacing: 20) {
                    // Invite Code Card
                    SCCard {
                        VStack(spacing: 12) {
                            Text("Invite Code")
                                .font(.caption)
                                .foregroundColor(SCPalette.muted)

                            Text(viewModel.session.inviteCode)
                                .font(.system(size: 32, weight: .bold, design: .monospaced))
                                .foregroundColor(SCPalette.accent)
                                .neonGlow(color: SCPalette.accent)

                            Button {
                                UIPasteboard.general.string = viewModel.session.inviteCode
                                copiedInvite = true
                                DispatchQueue.main.asyncAfter(deadline: .now() + 2) {
                                    copiedInvite = false
                                }
                            } label: {
                                Label(
                                    copiedInvite ? "Copied!" : "Copy Code",
                                    systemImage: copiedInvite ? "checkmark" : "doc.on.doc"
                                )
                                .font(.caption.bold())
                            }
                            .buttonStyle(SCButtonStyle(variant: .ghost))
                        }
                    }

                    // Session Config Summary
                    SCCard {
                        HStack(spacing: 16) {
                            ConfigBadge(icon: "music.note", value: "\(viewModel.session.secondsPerTrack)s")
                            ConfigBadge(icon: "person.2", value: "\(viewModel.session.tracksPerPlayer)/player")
                            ConfigBadge(icon: "list.number", value: "max \(viewModel.session.maxTracks)")
                        }
                    }

                    // Players Section
                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            Text("Players")
                                .font(.headline)
                                .foregroundColor(SCPalette.text)
                            Spacer()
                            Text("\(viewModel.players.count)")
                                .font(.subheadline.bold())
                                .foregroundColor(SCPalette.muted)
                        }

                        if viewModel.players.isEmpty {
                            Text("No players yet")
                                .font(.subheadline)
                                .foregroundColor(SCPalette.muted)
                        } else {
                            ForEach(viewModel.players) { player in
                                HStack(spacing: 10) {
                                    Image(systemName: player.isAdmin ? "crown.fill" : "person.fill")
                                        .foregroundColor(player.isAdmin ? SCPalette.accent : SCPalette.muted)
                                        .font(.caption)
                                    Text(player.user.preferredName)
                                        .font(.subheadline)
                                        .foregroundColor(SCPalette.text)
                                    if player.isAdmin {
                                        Text("Admin")
                                            .font(.caption2)
                                            .foregroundColor(SCPalette.accent)
                                            .padding(.horizontal, 6)
                                            .padding(.vertical, 2)
                                            .background(SCPalette.accent.opacity(0.15))
                                            .cornerRadius(4)
                                    }
                                    Spacer()
                                }
                                .padding(.vertical, 4)
                            }
                        }
                    }
                    .padding(.horizontal, 4)

                    // Tracks Section
                    VStack(alignment: .leading, spacing: 10) {
                        HStack {
                            Text("Tracks")
                                .font(.headline)
                                .foregroundColor(SCPalette.text)
                            Spacer()
                            Text("\(viewModel.tracks.count)/\(viewModel.session.maxTracks)")
                                .font(.subheadline.bold())
                                .foregroundColor(SCPalette.muted)
                        }

                        if viewModel.tracks.isEmpty {
                            SCCard {
                                VStack(spacing: 8) {
                                    Image(systemName: "music.note.list")
                                        .font(.title2)
                                        .foregroundColor(SCPalette.muted.opacity(0.5))
                                    Text("No tracks added yet")
                                        .font(.subheadline)
                                        .foregroundColor(SCPalette.muted)
                                }
                                .frame(maxWidth: .infinity)
                                .padding(.vertical, 8)
                            }
                        } else {
                            ForEach(viewModel.tracks) { track in
                                TrackRow(track: track)
                            }
                        }

                        NavigationLink {
                            AddTracksView(sessionId: viewModel.session.id)
                        } label: {
                            Label("Add Tracks", systemImage: "plus")
                        }
                        .buttonStyle(SCButtonStyle(variant: .secondary))
                    }
                    .padding(.horizontal, 4)

                    SCStatusBanner(message: viewModel.errorMessage, variant: .error)

                    // Spotify Connection
                    if viewModel.session.status == .lobby {
                        SCCard {
                            HStack(spacing: 12) {
                                Image(systemName: spotify.isConnected ? "checkmark.circle.fill" : "music.note.tv")
                                    .foregroundColor(spotify.isConnected ? SCPalette.success : SCPalette.muted)
                                    .font(.title3)
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(spotify.isConnected ? (spotify.isPreviewMode ? "Preview Mode" : "Spotify Connected") : "Spotify")
                                        .font(.subheadline.bold())
                                        .foregroundColor(SCPalette.text)
                                    Text(spotify.isConnected ? (spotify.isPreviewMode ? "Playing 30s preview clips" : "Ready to play") : "Connect to play music")
                                        .font(.caption)
                                        .foregroundColor(SCPalette.muted)
                                }
                                Spacer()
                                if !spotify.isConnected {
                                    Button {
                                        spotify.authorize()
                                    } label: {
                                        if spotify.isConnecting {
                                            ProgressView()
                                                .scaleEffect(0.8)
                                                .tint(SCPalette.success)
                                        } else {
                                            Text("Connect")
                                                .font(.caption.bold())
                                        }
                                    }
                                    .buttonStyle(SCButtonStyle(variant: .secondary))
                                    .frame(width: 100)
                                    .disabled(spotify.isConnecting)
                                }
                            }
                        }

                        if let spotifyError = spotify.errorMessage {
                            SCStatusBanner(message: spotifyError, variant: .error)
                        }
                    }

                    // Start button (admin only, lobby state)
                    if viewModel.session.status == .lobby {
                        let canStart = !viewModel.tracks.isEmpty && spotify.isConnected

                        Button {
                            Task {
                                await viewModel.startSession(token: session.token)
                            }
                        } label: {
                            Label("Start Power Hour", systemImage: "play.fill")
                        }
                        .buttonStyle(SCButtonStyle(variant: .primary))
                        .disabled(!canStart)
                        .opacity(canStart ? 1.0 : 0.5)
                        .padding(.top, 8)

                        if !canStart {
                            VStack(spacing: 4) {
                                if viewModel.tracks.isEmpty {
                                    Label("Add at least one track", systemImage: "music.note")
                                }
                                if !spotify.isConnected {
                                    Label("Connect Spotify to play music", systemImage: "music.note.tv")
                                }
                            }
                            .font(.caption)
                            .foregroundColor(SCPalette.muted)
                        }
                    }
                }
                .padding(.horizontal, 24)
                .padding(.vertical, 20)
            }
            .refreshable {
                await viewModel.refresh(token: session.token)
            }

            if viewModel.isLoading && viewModel.players.isEmpty {
                SCSpinner()
            }
        }
        .navigationTitle(viewModel.session.title)
        .navigationBarTitleDisplayMode(.inline)
        .toolbarColorScheme(.dark, for: .navigationBar)
        .navigationDestination(isPresented: $viewModel.didStartSession) {
            PlaybackView(gameSession: viewModel.session, tracks: viewModel.tracks)
        }
        .task {
            await viewModel.loadDetails(token: session.token)
        }
    }
}

// MARK: - Config Badge

struct ConfigBadge: View {
    let icon: String
    let value: String

    var body: some View {
        VStack(spacing: 4) {
            Image(systemName: icon)
                .font(.caption)
                .foregroundColor(SCPalette.secondary)
            Text(value)
                .font(.caption2.bold())
                .foregroundColor(SCPalette.text)
        }
        .frame(maxWidth: .infinity)
    }
}

// MARK: - Track Row

struct TrackRow: View {
    let track: SessionTrackItem

    var body: some View {
        HStack(spacing: 12) {
            Text("\(track.order + 1)")
                .font(.caption.bold())
                .foregroundColor(SCPalette.muted)
                .frame(width: 20)

            VStack(alignment: .leading, spacing: 2) {
                Text(track.trackName)
                    .font(.subheadline)
                    .foregroundColor(SCPalette.text)
                    .lineLimit(1)
                Text(track.trackArtist)
                    .font(.caption)
                    .foregroundColor(SCPalette.muted)
                    .lineLimit(1)
            }

            Spacer()

            Text(track.addedByUsername)
                .font(.caption2)
                .foregroundColor(SCPalette.muted)
        }
        .padding(.vertical, 6)
    }
}

#Preview {
    NavigationStack {
        SessionLobbyView(gameSession: PowerHourSession(
            id: "test-id",
            admin: 1,
            title: "Test Session",
            inviteCode: "ABC12345",
            tracksPerPlayer: 3,
            maxTracks: 30,
            secondsPerTrack: 60,
            transitionClip: "airhorn",
            hideTrackOwners: false,
            status: .lobby,
            currentTrackIndex: -1,
            createdAt: "",
            startedAt: nil,
            endedAt: nil,
            playerCount: 1,
            trackCount: 0
        ))
        .environmentObject(SessionStore())
    }
}
