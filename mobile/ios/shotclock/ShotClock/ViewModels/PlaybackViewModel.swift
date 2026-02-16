import SwiftUI
import Combine
import JukeKit

@MainActor
final class PlaybackViewModel: ObservableObject {
    @Published var session: PowerHourSession
    @Published var tracks: [SessionTrackItem]
    @Published var currentTrackIndex: Int
    @Published var timeRemaining: Int
    @Published var isPaused = false
    @Published var isEnded = false
    @Published var errorMessage: String?

    private var timer: AnyCancellable?
    private let sessionService: SessionService
    private let playbackService: JukePlaybackService

    init(
        session: PowerHourSession,
        tracks: [SessionTrackItem],
        sessionService: SessionService = SessionService(),
        playbackService: JukePlaybackService = JukePlaybackService()
    ) {
        self.session = session
        self.tracks = tracks.sorted { $0.order < $1.order }
        self.currentTrackIndex = max(session.currentTrackIndex, 0)
        self.timeRemaining = session.secondsPerTrack
        self.sessionService = sessionService
        self.playbackService = playbackService

        if session.status == .paused {
            self.isPaused = true
        } else if session.status == .ended {
            self.isEnded = true
        }
    }

    var currentTrack: SessionTrackItem? {
        guard currentTrackIndex >= 0 && currentTrackIndex < tracks.count else { return nil }
        return tracks[currentTrackIndex]
    }

    var progress: Double {
        guard session.secondsPerTrack > 0 else { return 0 }
        return Double(session.secondsPerTrack - timeRemaining) / Double(session.secondsPerTrack)
    }

    var trackLabel: String {
        "\(currentTrackIndex + 1) of \(tracks.count)"
    }

    var formattedTime: String {
        let mins = timeRemaining / 60
        let secs = timeRemaining % 60
        return String(format: "%d:%02d", mins, secs)
    }

    // MARK: - Timer Control

    func startTimer() {
        guard !isPaused && !isEnded else { return }
        timer?.cancel()
        timer = Timer.publish(every: 1, on: .main, in: .common)
            .autoconnect()
            .sink { [weak self] _ in
                self?.tick()
            }

        Task {
            await playCurrentTrack()
        }
    }

    func stopTimer() {
        timer?.cancel()
        timer = nil
    }

    private func tick() {
        guard timeRemaining > 0 else { return }
        timeRemaining -= 1

        if timeRemaining == 0 {
            handleTrackEnd()
        }
    }

    private func handleTrackEnd() {
        stopTimer()

        Task {
            await pauseCurrentTrack()
            SoundPlayer.shared.play(session.transitionClip)
            try? await Task.sleep(nanoseconds: 1_500_000_000)
            await advanceTrack()
        }
    }

    // MARK: - Backend Playback

    private func playCurrentTrack() async {
        guard let token = storedToken, let uri = currentTrackURI else { return }

        do {
            _ = try await playbackService.play(
                token: token,
                provider: "spotify",
                trackURI: uri,
                positionMs: currentTrack?.startOffsetMs
            )
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func pauseCurrentTrack() async {
        guard let token = storedToken else { return }
        do {
            _ = try await playbackService.pause(token: token, provider: "spotify")
            errorMessage = nil
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private var currentTrackURI: String? {
        guard let spotifyID = currentTrack?.spotifyId, !spotifyID.isEmpty else {
            return nil
        }
        return "spotify:track:\(spotifyID)"
    }

    // MARK: - Session Controls

    private func advanceTrack() async {
        guard let token = storedToken else { return }
        do {
            let state = try await sessionService.nextTrack(id: session.id, token: token)
            applyState(state)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func skipTrack(token: String?) async {
        guard let token else { return }
        stopTimer()
        await pauseCurrentTrack()
        do {
            let state = try await sessionService.nextTrack(id: session.id, token: token)
            applyState(state)
        } catch {
            errorMessage = error.localizedDescription
            startTimer()
        }
    }

    func togglePause(token: String?) async {
        guard let token else { return }
        errorMessage = nil
        do {
            if isPaused {
                let state = try await sessionService.resumeSession(id: session.id, token: token)
                applyState(state)
            } else {
                let state = try await sessionService.pauseSession(id: session.id, token: token)
                applyState(state)
            }
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func endSession(token: String?) async {
        guard let token else { return }
        stopTimer()
        await pauseCurrentTrack()
        do {
            let state = try await sessionService.endSession(id: session.id, token: token)
            applyState(state)
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    // MARK: - State Management

    private func applyState(_ state: SessionState) {
        currentTrackIndex = state.currentTrackIndex

        switch state.status {
        case .active:
            isPaused = false
            isEnded = false
            timeRemaining = session.secondsPerTrack
            startTimer()
        case .paused:
            isPaused = true
            stopTimer()
            Task {
                await pauseCurrentTrack()
            }
        case .ended:
            isEnded = true
            stopTimer()
            Task {
                await pauseCurrentTrack()
            }
        case .lobby:
            break
        }
    }

    private var storedToken: String?

    func setToken(_ token: String?) {
        storedToken = token
    }
}
