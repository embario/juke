import Foundation
import Testing
@testable import JukeApp

@MainActor @Suite struct PlayerTransportTests {
    @MainActor private final class FakeRadio: TransportRadio {
        var isOnAir: Bool
        var isPlaying = true
        var calls: [String] = []
        init(onAir: Bool) { isOnAir = onAir }
        func previous() async { calls.append("previous") }
        func togglePlayPause() async { calls.append("toggle") }
        func skip() async { calls.append("skip") }
    }

    private final class FakeSpotify: TransportSpotify, @unchecked Sendable {
        var calls: [String] = []
        var fail = false
        private func record(_ name: String) throws -> JukePlaybackState? {
            if fail { throw PlaybackClientError.unavailable(404) }
            calls.append(name); return nil
        }
        func previous(token: String, deviceID: String?) async throws -> JukePlaybackState? { try record("previous") }
        func pause(token: String, deviceID: String?) async throws -> JukePlaybackState? { try record("pause") }
        func resume(token: String, deviceID: String?) async throws -> JukePlaybackState? { try record("resume") }
        func next(token: String, deviceID: String?) async throws -> JukePlaybackState? { try record("next") }
    }

    private func make(onAir: Bool, token: String? = "t", playing: Bool = true) -> (PlayerTransport, FakeRadio, FakeSpotify) {
        let radio = FakeRadio(onAir: onAir), spotify = FakeSpotify()
        return (PlayerTransport(radio: radio, spotify: spotify, token: { token }, externalIsPlaying: { playing }), radio, spotify)
    }

    @Test func radioOnAirDrivesTheStation() async {
        let (transport, radio, spotify) = make(onAir: true)
        await transport.press(.previous); await transport.press(.playPause); await transport.press(.next)
        #expect(radio.calls == ["previous", "toggle", "skip"])
        #expect(spotify.calls.isEmpty)
    }

    @Test func otherPlaybackUsesSpotifyControls() async {
        let (transport, radio, spotify) = make(onAir: false, playing: true)
        await transport.press(.previous); await transport.press(.next); await transport.press(.playPause)
        #expect(spotify.calls == ["previous", "next", "pause"])
        #expect(radio.calls.isEmpty)
        #expect(!transport.isPlaying, "a press shows its result before the next poll")
        await transport.press(.playPause)
        #expect(spotify.calls.last == "resume")
        transport.observed()
        #expect(transport.isPlaying == true)
    }

    @Test func explainsWhenControlsCannotBeSent() async {
        let (signedOut, _, _) = make(onAir: false, token: nil)
        await signedOut.press(.next)
        #expect(signedOut.message?.contains("Sign in") == true)
        let (failing, _, spotify) = make(onAir: false)
        spotify.fail = true
        await failing.press(.next)
        #expect(failing.message?.hasPrefix("Couldn't reach Spotify") == true)
    }

    @Test func islandIsClearlySeparatedFromContent() {
        #expect(MiniPlayerStyle.borderOpacity >= 0.2)
        #expect(MiniPlayerStyle.borderWidth >= 1)
        #expect(MiniPlayerStyle.shadowOpacity > 0 && MiniPlayerStyle.shadowRadius > 0)
    }
}
