import Foundation
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

/// One set of previous / play-pause / next controls for every screen and source.
/// Radio drives its own station; any other playback (a memory's song, Spotify
/// started elsewhere) goes through the Spotify playback API.
@MainActor
@Observable
final class PlayerTransport {
    enum Action { case previous, playPause, next }

    /// Shown when an external control could not be sent.
    var message: String?
    /// Reflects a press until the observer's next poll confirms it.
    private(set) var pressedPlaying: Bool?

    @ObservationIgnored private let radio: any TransportRadio
    @ObservationIgnored private let spotify: any TransportSpotify
    @ObservationIgnored private let token: @MainActor () -> String?
    @ObservationIgnored private let externalIsPlaying: @MainActor () -> Bool

    init(radio: any TransportRadio, spotify: any TransportSpotify = PlaybackClient(),
         token: @escaping @MainActor () -> String?, externalIsPlaying: @escaping @MainActor () -> Bool) {
        self.radio = radio; self.spotify = spotify; self.token = token; self.externalIsPlaying = externalIsPlaying
    }

    var drivesRadio: Bool { radio.isOnAir }

    var isPlaying: Bool { radio.isOnAir ? radio.isPlaying : (pressedPlaying ?? externalIsPlaying()) }

    /// Called when the observer reports fresh state, so a stale press does not stick.
    func observed() { pressedPlaying = nil }

    func press(_ action: Action) async {
        message = nil
        if radio.isOnAir {
            switch action {
            case .previous: await radio.previous()
            case .playPause: await radio.togglePlayPause()
            case .next: await radio.skip()
            }
            return
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
                if isPlaying { _ = try await spotify.pause(token: token, deviceID: nil); pressedPlaying = false }
                else { _ = try await spotify.resume(token: token, deviceID: nil); pressedPlaying = true }
            }
        } catch {
            message = "Couldn't reach Spotify: \(error.localizedDescription)"
        }
    }
}
