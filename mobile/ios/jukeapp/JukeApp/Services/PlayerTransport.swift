import Foundation
import MediaPlayer
import Observation

/// What the persistent player needs from the radio.
@MainActor
protocol TransportRadio: AnyObject {
    var isOnAir: Bool { get }
    var isPlaying: Bool { get }
    func previous() async
    func togglePlayPause() async
    func skip() async
}

extension RadioController: TransportRadio {}

/// What the persistent player needs from Spotify when radio is not in charge.
protocol TransportSpotify: Sendable {
    func previous(token: String, deviceID: String?) async throws -> JukePlaybackState?
    func pause(token: String, deviceID: String?) async throws -> JukePlaybackState?
    func resume(token: String, deviceID: String?) async throws -> JukePlaybackState?
    func next(token: String, deviceID: String?) async throws -> JukePlaybackState?
}

extension PlaybackClient: TransportSpotify {}

/// What the persistent player needs from the system music player (Apple Music).
@MainActor
protocol TransportApple: AnyObject {
    func previous()
    func pause()
    func play()
    func next()
}

/// Controls Apple Music through the system player.
@MainActor
final class SystemAppleTransport: TransportApple {
    private var player: MPMusicPlayerController { .systemMusicPlayer }
    func previous() { player.skipToPreviousItem() }
    func pause() { player.pause() }
    func play() { player.play() }
    func next() { player.skipToNextItem() }
}

/// The player that is actually making sound when radio is off air.
enum TransportSource: Equatable {
    case spotify, appleMusic
    /// Heard through the microphone (Around Me): Juke has nothing to control.
    case uncontrollable

    /// Derived from `NowPlayingTrack.source`, which names where the song was heard.
    init(trackSource: String?) {
        switch trackSource {
        case "Apple Music": self = .appleMusic
        case let value? where value.localizedCaseInsensitiveContains("around me") || value.localizedCaseInsensitiveContains("shazam"): self = .uncontrollable
        default: self = .spotify
        }
    }
}

/// One set of previous / play-pause / next controls for every screen and source.
/// Radio drives its own station; any other playback (a memory's song, Spotify
/// started elsewhere) goes through the Spotify playback API.
@MainActor
@Observable
final class PlayerTransport {
    enum Action { case previous, playPause, next }

    /// Shown when an external control could not be sent.
    var message: String?
    /// Reflects a press only briefly: after `pressLifetime` the observed state wins, so
    /// a command that reached nobody cannot leave the wrong icon showing.
    private(set) var pressedPlaying: Bool?
    @ObservationIgnored private var pressedAt = Date.distantPast
    static let pressLifetime: TimeInterval = 4

    @ObservationIgnored private let radio: any TransportRadio
    @ObservationIgnored private let spotify: any TransportSpotify
    @ObservationIgnored private let token: @MainActor () -> String?
    @ObservationIgnored private let apple: any TransportApple
    @ObservationIgnored private let externalIsPlaying: @MainActor () -> Bool
    @ObservationIgnored private let externalSource: @MainActor () -> TransportSource
    @ObservationIgnored private let now: @MainActor () -> Date
    @ObservationIgnored private let memory: (any TransportMemory)?

    init(radio: any TransportRadio, memory: (any TransportMemory)? = nil, spotify: any TransportSpotify = PlaybackClient(), apple: any TransportApple = SystemAppleTransport(),
         token: @escaping @MainActor () -> String?, externalIsPlaying: @escaping @MainActor () -> Bool,
         externalSource: @escaping @MainActor () -> TransportSource = { .spotify }, now: @escaping @MainActor () -> Date = { .now }) {
        self.radio = radio; self.memory = memory; self.spotify = spotify; self.apple = apple; self.token = token
        self.externalIsPlaying = externalIsPlaying; self.externalSource = externalSource; self.now = now
    }

    var drivesRadio: Bool { radio.isOnAir }

    /// The buttons stay visible but are disabled for a source Juke cannot control.
    var isControllable: Bool { radio.isOnAir || externalSource() != .uncontrollable }

    var isPlaying: Bool {
        if radio.isOnAir { return radio.isPlaying }
        if let pressedPlaying, now().timeIntervalSince(pressedAt) < Self.pressLifetime { return pressedPlaying }
        return externalIsPlaying()
    }

    /// Called when the observer reports fresh state, so a stale press does not stick.
    func observed() { pressedPlaying = nil }

    private func pressed(playing: Bool) { pressedPlaying = playing; pressedAt = now() }

    func press(_ action: Action) async {
        message = nil
        // A memory's song steps through memories in time, not through Spotify's queue or the station
        // (starting a memory replaces whatever the station was playing).
        if let memory, memory.isActive, action != .playPause {
            if !(await memory.step(action == .next ? 1 : -1)) {
                message = action == .next ? "That's the latest memory." : "That's the earliest memory."
            }
            return
        }
        if radio.isOnAir {
            switch action {
            case .previous: await radio.previous()
            case .playPause: await radio.togglePlayPause()
            case .next: await radio.skip()
            }
            return
        }
        switch externalSource() {
        case .uncontrollable: return
        case .appleMusic:
            switch action {
            case .previous: apple.previous()
            case .next: apple.next()
            case .playPause:
                if isPlaying { apple.pause(); pressed(playing: false) } else { apple.play(); pressed(playing: true) }
            }
            return
        case .spotify: break
        }
        guard let token = token(), !token.isEmpty else {
            message = "Sign in to Juke with Spotify linked to control playback."
            return
        }
        do {
            switch action {
            case .previous: _ = try await spotify.previous(token: token, deviceID: nil)
            case .next: _ = try await spotify.next(token: token, deviceID: nil)
            case .playPause:
                if isPlaying { _ = try await spotify.pause(token: token, deviceID: nil); pressed(playing: false) }
                else { _ = try await spotify.resume(token: token, deviceID: nil); pressed(playing: true) }
            }
        } catch {
            message = "Couldn't reach Spotify: \(error.localizedDescription)"
        }
    }
}
