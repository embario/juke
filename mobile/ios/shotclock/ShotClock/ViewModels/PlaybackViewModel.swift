import SwiftUI
import Combine

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
    private let spotify: SpotifyManager

    init(session: PowerHourSession, tracks: [SessionTrackItem], sessionService: SessionService = SessionService(), spotify: SpotifyManager = .shared) {
        self.session = session
        self.tracks = tracks.sorted { $0.order < $1.order }
        self.currentTrackIndex = max(session.currentTrackIndex, 0)
        self.timeRemaining = session.secondsPerTrack
        self.sessionService = sessionService
        self.spotify = spotify

        // Resume into correct state for active/paused sessions
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
        // Play the current track on Spotify
        playCurrentTrack()
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
        // Pause Spotify during transition
        spotify.pause()
        // Play transition sound
        SoundPlayer.shared.play(session.transitionClip)

        // Advance after a short delay to let the sound play
        Task {
            try? await Task.sleep(nanoseconds: 1_500_000_000)
            await advanceTrack()
        }
    }

    // MARK: - Spotify Playback

    private func playCurrentTrack() {
        guard let track = currentTrack, spotify.isConnected else { return }

        if spotify.isPreviewMode {
            // Use AVPlayer fallback with preview URL
            if let previewUrl = track.previewUrl, !previewUrl.isEmpty {
                spotify.playPreview(url: previewUrl)
            }
            return
        }

        let uri = "spotify:track:\(track.spotifyId)"
        spotify.play(spotifyURI: uri)
        if track.startOffsetMs > 0 {
            spotify.seek(toPosition: track.startOffsetMs)
        }
    }

    // MARK: - Session Controls

    private func advanceTrack() async {
        guard let token = await getToken() else { return }
        do {
            let state = try await sessionService.nextTrack(id: session.id, token: token)
            applyState(state)
        } catch let error as APIError {
            errorMessage = error.errorDescription
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func skipTrack(token: String?) async {
        guard let token else { return }
        stopTimer()
        spotify.pause()
        do {
            let state = try await sessionService.nextTrack(id: session.id, token: token)
            applyState(state)
        } catch let error as APIError {
            errorMessage = error.errorDescription
            startTimer()
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
        } catch let error as APIError {
            errorMessage = error.errorDescription
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func endSession(token: String?) async {
        guard let token else { return }
        stopTimer()
        spotify.pause()
        do {
            let state = try await sessionService.endSession(id: session.id, token: token)
            applyState(state)
        } catch let error as APIError {
            errorMessage = error.errorDescription
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
            spotify.pause()
        case .ended:
            isEnded = true
            stopTimer()
            spotify.pause()
        case .lobby:
            break
        }
    }

    // Helper to get token from a non-isolated context
    private var storedToken: String?

    func setToken(_ token: String?) {
        storedToken = token
    }

    private func getToken() async -> String? {
        storedToken
    }
}
