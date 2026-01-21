import SwiftUI

struct PlaybackView: View {
    @EnvironmentObject var session: SessionStore
    @Environment(\.dismiss) private var dismiss
    @StateObject private var viewModel: PlaybackViewModel

    init(gameSession: PowerHourSession, tracks: [SessionTrackItem]) {
        _viewModel = StateObject(wrappedValue: PlaybackViewModel(session: gameSession, tracks: tracks))
    }

    var body: some View {
        ZStack {
            SCBackground()

            if viewModel.isEnded {
                endedContent
            } else {
                playbackContent
            }
        }
        .navigationBarBackButtonHidden(true)
        .onAppear {
            viewModel.setToken(session.token)
            viewModel.startTimer()
        }
        .onDisappear {
            viewModel.stopTimer()
        }
    }

    // MARK: - Playback Content

    private var playbackContent: some View {
        VStack(spacing: 0) {
            // Track progress
            Text("Track \(viewModel.trackLabel)")
                .font(.subheadline.bold())
                .foregroundColor(SCPalette.muted)
                .padding(.top, 32)

            Spacer()

            // Countdown ring
            ZStack {
                SCCountdownRing(
                    progress: viewModel.progress,
                    lineWidth: 16,
                    size: 220
                )

                VStack(spacing: 4) {
                    Text(viewModel.formattedTime)
                        .font(.system(size: 48, weight: .bold, design: .monospaced))
                        .foregroundColor(SCPalette.text)
                    if viewModel.isPaused {
                        Text("PAUSED")
                            .font(.caption.bold())
                            .foregroundColor(SCPalette.warning)
                    }
                }
            }

            Spacer()

            // Current track info
            if let track = viewModel.currentTrack {
                VStack(spacing: 6) {
                    Text(track.trackName)
                        .font(.title3.bold())
                        .foregroundColor(SCPalette.text)
                        .lineLimit(2)
                        .multilineTextAlignment(.center)
                    Text(track.trackArtist)
                        .font(.subheadline)
                        .foregroundColor(SCPalette.muted)
                        .lineLimit(1)
                }
                .padding(.horizontal, 32)
            }

            Spacer()

            // Controls
            HStack(spacing: 24) {
                // Pause / Resume
                Button {
                    Task {
                        await viewModel.togglePause(token: session.token)
                    }
                } label: {
                    Image(systemName: viewModel.isPaused ? "play.fill" : "pause.fill")
                        .font(.title)
                        .frame(width: 64, height: 64)
                        .background(SCPalette.panelAlt)
                        .clipShape(Circle())
                        .overlay(Circle().stroke(SCPalette.border, lineWidth: 1))
                        .foregroundColor(SCPalette.text)
                }

                // Skip
                Button {
                    Task {
                        await viewModel.skipTrack(token: session.token)
                    }
                } label: {
                    Image(systemName: "forward.fill")
                        .font(.title2)
                        .frame(width: 56, height: 56)
                        .background(SCPalette.panelAlt)
                        .clipShape(Circle())
                        .overlay(Circle().stroke(SCPalette.border, lineWidth: 1))
                        .foregroundColor(SCPalette.text)
                }

                // End
                Button {
                    Task {
                        await viewModel.endSession(token: session.token)
                    }
                } label: {
                    Image(systemName: "stop.fill")
                        .font(.title2)
                        .frame(width: 56, height: 56)
                        .background(SCPalette.error.opacity(0.2))
                        .clipShape(Circle())
                        .overlay(Circle().stroke(SCPalette.error.opacity(0.4), lineWidth: 1))
                        .foregroundColor(SCPalette.error)
                }
            }
            .padding(.bottom, 16)

            if let error = viewModel.errorMessage {
                SCStatusBanner(message: error, variant: .error)
                    .padding(.horizontal, 24)
            }

            Spacer().frame(height: 32)
        }
    }

    // MARK: - Ended Content

    private var endedContent: some View {
        VStack(spacing: 24) {
            Spacer()

            Image(systemName: "checkmark.circle.fill")
                .font(.system(size: 72))
                .foregroundColor(SCPalette.success)
                .neonGlow(color: SCPalette.success)

            Text("Power Hour Complete!")
                .font(.title.bold())
                .foregroundColor(SCPalette.text)

            Text("\(viewModel.tracks.count) tracks played")
                .font(.subheadline)
                .foregroundColor(SCPalette.muted)

            Button {
                dismiss()
            } label: {
                Label("Done", systemImage: "checkmark")
            }
            .buttonStyle(SCButtonStyle(variant: .primary))
            .padding(.horizontal, 24)

            Spacer()
        }
    }
}

#Preview {
    NavigationStack {
        PlaybackView(
            gameSession: PowerHourSession(
                id: "test",
                admin: 1,
                title: "Test Power Hour",
                inviteCode: "ABC12345",
                tracksPerPlayer: 3,
                maxTracks: 30,
                secondsPerTrack: 60,
                transitionClip: "airhorn",
                hideTrackOwners: false,
                status: .active,
                currentTrackIndex: 0,
                createdAt: "",
                startedAt: nil,
                endedAt: nil,
                playerCount: 2,
                trackCount: 5
            ),
            tracks: [
                SessionTrackItem(
                    id: "1", trackId: 1, order: 0, startOffsetMs: 0,
                    addedAt: "", trackName: "Bohemian Rhapsody",
                    trackArtist: "Queen", trackAlbum: "A Night at the Opera",
                    durationMs: 354000, spotifyId: "abc", previewUrl: nil,
                    addedBy: 1, addedByUsername: "player1"
                )
            ]
        )
        .environmentObject(SessionStore())
    }
}
