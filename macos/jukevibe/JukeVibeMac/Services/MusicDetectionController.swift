import Foundation
import Observation

@MainActor
@Observable
final class MusicDetectionController {
    enum SpotifyPlaybackAccess: Equatable {
        case checking
        case available
        case spectator
    }

    enum Mode: String, CaseIterable, Identifiable {
        case playerMetadata, microphone, systemAudio
        var id: String { rawValue }
        var title: String {
            switch self {
            case .playerMetadata: "Spotify & Apple Music"
            case .microphone: "Around Me"
            case .systemAudio: "This Mac's Audio"
            }
        }
    }

    var track: RecognizedTrack?
    var providerName: String?
    var isAudioPresent = false
    var isPlaying = false
    var playbackPosition: TimeInterval = 0
    var playbackDuration: TimeInterval = 0
    var playbackDeviceName: String?
    var isPlaybackBusy = false
    var spotifyPlaybackAccess: SpotifyPlaybackAccess = .checking
    var prefersSpotifySpectatorMode = UserDefaults.standard.bool(forKey: "vibe.prefersSpotifySpectatorMode")
    var mode: Mode = .playerMetadata
    var errorMessage: String?

    private let monitor: PlayerMetadataMonitor
    @ObservationIgnored private var playbackComesFromLocalMetadata = false
    private let playbackClient = PlaybackClient()
    private let localPlaybackController = LocalPlayerPlaybackController()
    private var capture: (any AudioCaptureService)?
    private var recognizer: (any TrackRecognizing)?
    @ObservationIgnored private var playbackPollTask: Task<Void, Never>?
    @ObservationIgnored private var accessToken: String?
    @ObservationIgnored private var playbackDeviceID: String?
    @ObservationIgnored private var playbackUpdatedAt = Date()
    @ObservationIgnored private var applicationIsActive = true
    @ObservationIgnored private var spotifyServerAvailable = true
    @ObservationIgnored private var forceSpectatorModeForUITests = false
    @ObservationIgnored private var playbackNotificationTokens: [NSObjectProtocol] = []

    init(monitor: PlayerMetadataMonitor = PlayerMetadataMonitor()) {
        self.monitor = monitor
        monitor.onSnapshot = { [weak self] snapshot in
            guard let self else { return }
            guard let snapshot else {
                // A missing local player must not erase playback on a remote
                // Spotify device. Only clear state last supplied by this monitor.
                guard self.playbackComesFromLocalMetadata else { return }
                self.track = nil
                self.providerName = nil
                self.isPlaying = false
                self.isAudioPresent = false
                self.playbackPosition = 0
                self.playbackDuration = 0
                self.playbackDeviceName = nil
                self.playbackDeviceID = nil
                self.playbackComesFromLocalMetadata = false
                return
            }
            self.playbackComesFromLocalMetadata = true
            self.playbackDeviceName = nil
            self.playbackDeviceID = nil
            self.track = snapshot.track
            self.providerName = snapshot.provider.rawValue
            self.isPlaying = snapshot.isPlaying
            self.isAudioPresent = snapshot.isPlaying
            self.playbackPosition = snapshot.playbackPosition
            self.playbackDuration = snapshot.track.trackDuration ?? 0
            self.playbackUpdatedAt = .now
        }
        let notificationCenter = DistributedNotificationCenter.default()
        playbackNotificationTokens.append(notificationCenter.addObserver(
            forName: Notification.Name("com.spotify.client.PlaybackStateChanged"),
            object: nil,
            queue: .main
        ) { [weak self] _ in
            Task { @MainActor in await self?.refreshSpotifyState() }
        })
    }

    func configureUITestPlayback(token: String) {
        guard ProcessInfo.processInfo.arguments.contains("--uitesting") else { return }
        forceSpectatorModeForUITests = ProcessInfo.processInfo.arguments.contains("--uitesting-spectator")
            || ProcessInfo.processInfo.environment["JUKE_VIBE_UI_SPECTATOR"] == "1"
        prefersSpotifySpectatorMode = forceSpectatorModeForUITests
        accessToken = token
        spotifyServerAvailable = !forceSpectatorModeForUITests
        spotifyPlaybackAccess = forceSpectatorModeForUITests ? .spectator : .available
        providerName = PlayerMetadataSnapshot.Provider.spotify.rawValue
        isPlaying = true
        isAudioPresent = true
        playbackPosition = 96
        playbackDuration = 327
        playbackDeviceID = "ui-test-device"
        playbackDeviceName = "Test Mac"
        playbackUpdatedAt = .now
    }

    func setApplicationActive(_ isActive: Bool) {
        applicationIsActive = isActive
        monitor.setApplicationActive(isActive)
        if isActive, !forceSpectatorModeForUITests {
            if spotifyPlaybackAccess == .spectator, !prefersSpotifySpectatorMode {
                spotifyServerAvailable = true
            }
            Task { await refreshSpotifyState() }
        }
    }

    func start(token: String? = nil) async {
        errorMessage = nil
        spotifyServerAvailable = !forceSpectatorModeForUITests
        spotifyPlaybackAccess = forceSpectatorModeForUITests ? .spectator : .checking
        let desiredToken = token ?? accessToken
        await stopServices()
        accessToken = desiredToken
        switch mode {
        case .playerMetadata:
            monitor.start()
            startSpotifyPolling()
        case .microphone:
            await startAudio(source: .microphone)
        case .systemAudio:
            await startAudio(source: .systemAudio)
        }
    }

    func stop() async {
        await stopServices()
        accessToken = nil
        spotifyPlaybackAccess = .checking
    }

    private func stopServices() async {
        playbackPollTask?.cancel()
        playbackPollTask = nil
        monitor.stop()
        let activeCapture = capture
        capture = nil
        activeCapture?.onFrame = nil
        activeCapture?.onFailure = nil
        await activeCapture?.stop()
        recognizer?.invalidate()
        recognizer = nil
        isAudioPresent = false
        isPlaying = false
        playbackPosition = 0
        playbackDuration = 0
        playbackDeviceName = nil
        playbackDeviceID = nil
    }

    var canControlPlayback: Bool {
        return switch providerName {
        case PlayerMetadataSnapshot.Provider.spotify.rawValue:
            canStartSpotifyPlayback
        case PlayerMetadataSnapshot.Provider.appleMusic.rawValue:
            true
        default:
            false
        }
    }

    var canStartSpotifyPlayback: Bool {
        accessToken != nil && hasVerifiedSpotifyPlayback && !prefersSpotifySpectatorMode
    }

    var hasVerifiedSpotifyPlayback: Bool {
        spotifyPlaybackAccess == .available
    }

    var isSpotifySpectatorMode: Bool {
        prefersSpotifySpectatorMode || spotifyPlaybackAccess == .spectator
    }

    func useSpotifySpectatorMode() {
        prefersSpotifySpectatorMode = true
        UserDefaults.standard.set(true, forKey: "vibe.prefersSpotifySpectatorMode")
        errorMessage = nil
    }

    func useSpotifyPlaybackMode() {
        prefersSpotifySpectatorMode = false
        UserDefaults.standard.set(false, forKey: "vibe.prefersSpotifySpectatorMode")
        guard !hasVerifiedSpotifyPlayback else { return }
        spotifyServerAvailable = true
        spotifyPlaybackAccess = .checking
        Task { await refreshSpotifyState() }
    }

    func estimatedPlaybackPosition(at date: Date = .now) -> TimeInterval {
        let elapsed = isPlaying ? max(0, date.timeIntervalSince(playbackUpdatedAt)) : 0
        return min(playbackDuration, max(0, playbackPosition + elapsed))
    }

    func togglePlayback() async {
        guard canControlPlayback else { return }
        if providerName == PlayerMetadataSnapshot.Provider.appleMusic.rawValue {
            await performLocalPlaybackAction {
                try await self.localPlaybackController.toggleAppleMusicPlayback()
            }
            return
        }
        guard let token = accessToken else { return }
        await performPlaybackAction {
            if self.isPlaying {
                return try await self.playbackClient.pause(token: token, deviceID: self.playbackDeviceID)
            }
            return try await self.playbackClient.resume(token: token, deviceID: self.playbackDeviceID)
        }
    }

    func previousTrack() async {
        guard canControlPlayback else { return }
        if providerName == PlayerMetadataSnapshot.Provider.appleMusic.rawValue {
            await performLocalPlaybackAction {
                try await self.localPlaybackController.previousAppleMusicTrack()
            }
            return
        }
        guard let token = accessToken else { return }
        await performPlaybackAction { try await self.playbackClient.previous(token: token, deviceID: self.playbackDeviceID) }
    }

    func nextTrack() async {
        guard canControlPlayback else { return }
        if providerName == PlayerMetadataSnapshot.Provider.appleMusic.rawValue {
            await performLocalPlaybackAction {
                try await self.localPlaybackController.nextAppleMusicTrack()
            }
            return
        }
        guard let token = accessToken else { return }
        await performPlaybackAction { try await self.playbackClient.next(token: token, deviceID: self.playbackDeviceID) }
    }

    func seek(to position: TimeInterval) async {
        guard canControlPlayback else { return }
        playbackPosition = min(playbackDuration, max(0, position))
        playbackUpdatedAt = .now
        if providerName == PlayerMetadataSnapshot.Provider.appleMusic.rawValue {
            await performLocalPlaybackAction {
                try await self.localPlaybackController.seekAppleMusic(to: position)
            }
            return
        }
        guard let token = accessToken else { return }
        await performPlaybackAction {
            try await self.playbackClient.seek(token: token, deviceID: self.playbackDeviceID, position: position)
        }
    }

    func playSpotify(
        id: String,
        kind: String,
        optimisticTrack: RecognizedTrack?
    ) async {
        guard canStartSpotifyPlayback, let token = accessToken else {
            errorMessage = "Spotify is not connected for playback. Juke Vibe is listening in spectator mode."
            return
        }
        if let optimisticTrack {
            playbackComesFromLocalMetadata = false
            track = optimisticTrack
            providerName = PlayerMetadataSnapshot.Provider.spotify.rawValue
            playbackPosition = 0
            playbackDuration = optimisticTrack.trackDuration ?? 0
            playbackUpdatedAt = .now
            isPlaying = true
            isAudioPresent = true
        }
        await performPlaybackAction {
            try await self.playbackClient.play(
                token: token,
                spotifyID: id,
                kind: kind,
                deviceID: self.playbackDeviceID
            )
        }
    }

    private func startSpotifyPolling() {
        guard accessToken != nil, playbackPollTask == nil else { return }
        playbackPollTask = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                guard let self else { return }
                await refreshSpotifyState()
                let seconds = spotifyServerAvailable
                    ? (applicationIsActive ? (isPlaying ? 2 : 3) : (isPlaying ? 4 : 6))
                    : 300
                do { try await Task.sleep(for: .seconds(seconds)) }
                catch { return }
                // Account linking can change in the Juke web app. Retry slowly
                // without hammering Neptune while local metadata remains active.
                if !spotifyServerAvailable { spotifyServerAvailable = true }
            }
        }
    }

    private func refreshSpotifyState() async {
        guard !forceSpectatorModeForUITests else { return }
        guard mode == .playerMetadata, spotifyServerAvailable, let accessToken else { return }
        do {
            let state = try await playbackClient.fetchSpotifyState(token: accessToken)
            spotifyPlaybackAccess = .available
            if let state {
                apply(state)
                errorMessage = nil
            }
        } catch PlaybackClientError.providerNotConnected {
            spotifyServerAvailable = false
            spotifyPlaybackAccess = .spectator
        } catch {
            // Local player metadata remains available if Neptune or Spotify is transiently unavailable.
        }
    }

    private func performPlaybackAction(
        _ operation: @escaping @MainActor () async throws -> JukePlaybackState?
    ) async {
        guard !isPlaybackBusy else { return }
        isPlaybackBusy = true
        defer { isPlaybackBusy = false }
        do {
            if let state = try await operation() { apply(state) }
            try? await Task.sleep(for: .milliseconds(350))
            await refreshSpotifyState()
        } catch PlaybackClientError.providerNotConnected(let detail) {
            spotifyServerAvailable = false
            spotifyPlaybackAccess = .spectator
            errorMessage = "\(detail) Juke Vibe remains available in spectator mode."
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    private func performLocalPlaybackAction(
        _ operation: @escaping @MainActor () async throws -> Void
    ) async {
        guard !isPlaybackBusy else { return }
        isPlaybackBusy = true
        defer { isPlaybackBusy = false }
        do {
            try await operation()
            try? await Task.sleep(for: .milliseconds(200))
            monitor.refreshNow()
        } catch {
            errorMessage = error.localizedDescription
        }
    }

    func apply(_ state: JukePlaybackState) {
        guard state.provider == "spotify", let value = state.track, let title = value.name else { return }
        playbackComesFromLocalMetadata = false
        let artist = value.artists?.compactMap(\.name).filter { !$0.isEmpty }.joined(separator: ", ") ?? "Unknown artist"
        let providerID = value.id ?? value.uri?.split(separator: ":").last.map(String.init)
        track = RecognizedTrack(
            title: title,
            artist: artist,
            album: value.album?.name,
            isrc: nil,
            artworkURL: value.artworkURL,
            appleMusicURL: nil,
            shazamID: nil,
            matchOffset: TimeInterval(state.progressMs) / 1_000,
            matchConfidence: 1,
            trackDuration: TimeInterval(value.durationMs ?? 0) / 1_000,
            providerNamespace: "spotify",
            providerTrackID: providerID,
            providerPlaybackURL: value.uri.flatMap(URL.init(string:))
        )
        providerName = PlayerMetadataSnapshot.Provider.spotify.rawValue
        isPlaying = state.isPlaying
        isAudioPresent = state.isPlaying
        playbackPosition = TimeInterval(state.progressMs) / 1_000
        playbackDuration = TimeInterval(value.durationMs ?? 0) / 1_000
        playbackDeviceName = state.device?.name
        playbackDeviceID = state.device?.id
        playbackUpdatedAt = .now
    }

    private func startAudio(source: CaptureSource) async {
        let newCapture: any AudioCaptureService = source == .microphone ? MicrophoneAudioCapture() : SystemAudioCapture()
        let newRecognizer: any TrackRecognizing = ShazamRecognizer()
        newRecognizer.onMatch = { [weak self] value in
            Task { @MainActor in
                self?.track = value
                self?.providerName = source == .microphone ? "Shazam · Around Me" : "Shazam · This Mac"
            }
        }
        newRecognizer.onError = { _ in }
        newCapture.onFrame = { [weak self, weak newRecognizer] frame in
            newRecognizer?.process(frame.buffer, at: frame.time)
            Task { @MainActor in self?.isAudioPresent = frame.isAudible }
        }
        newCapture.onFailure = { [weak self] message in Task { @MainActor in self?.errorMessage = message } }
        capture = newCapture
        recognizer = newRecognizer
        do { try await newCapture.start() }
        catch { errorMessage = error.localizedDescription }
    }
}
