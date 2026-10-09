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

    @MainActor private final class FakeApple: TransportApple {
        var calls: [String] = []
        func previous() { calls.append("previous") }
        func pause() { calls.append("pause") }
        func play() { calls.append("play") }
        func next() { calls.append("next") }
    }

    @MainActor private final class Clock { var now = Date(timeIntervalSince1970: 1_800_000_000) }

    private func make(onAir: Bool, token: String? = "t", playing: Bool = true, source: TransportSource = .spotify,
                      apple: FakeApple = FakeApple(), clock: Clock = Clock()) -> (PlayerTransport, FakeRadio, FakeSpotify) {
        let radio = FakeRadio(onAir: onAir), spotify = FakeSpotify()
        return (PlayerTransport(radio: radio, spotify: spotify, apple: apple, token: { token }, externalIsPlaying: { playing },
                                externalSource: { source }, now: { clock.now }), radio, spotify)
    }

    @Test func mapsTrackSourcesToTheRightPlayer() {
        #expect(TransportSource(trackSource: "Apple Music") == .appleMusic)
        #expect(TransportSource(trackSource: "Spotify") == .spotify)
        #expect(TransportSource(trackSource: "Shazam · Around Me") == .uncontrollable)
        #expect(TransportSource(trackSource: nil) == .spotify)
    }

    @Test func appleMusicIsControlledThroughTheSystemPlayerNotSpotify() async {
        let apple = FakeApple()
        let (transport, _, spotify) = make(onAir: false, playing: true, source: .appleMusic, apple: apple)
        await transport.press(.previous); await transport.press(.next); await transport.press(.playPause)
        #expect(apple.calls == ["previous", "next", "pause"])
        #expect(spotify.calls.isEmpty, "Spotify must not be started on top of Apple Music")
        await transport.press(.playPause)
        #expect(apple.calls.last == "play")
        #expect(spotify.calls.isEmpty)
    }

    @Test func aroundMeMatchesHaveNothingToControl() async {
        let apple = FakeApple()
        let (transport, radio, spotify) = make(onAir: false, source: .uncontrollable, apple: apple)
        #expect(!transport.isControllable)
        await transport.press(.playPause); await transport.press(.next)
        #expect(apple.calls.isEmpty && spotify.calls.isEmpty && radio.calls.isEmpty)
        #expect(transport.message == nil)
        let (onAir, _, _) = make(onAir: true, source: .uncontrollable)
        #expect(onAir.isControllable, "radio on air is always controllable")
    }

    @Test func aPressedStateExpiresSoALostCommandCannotLeaveTheWrongIcon() async {
        let clock = Clock()
        let (transport, _, _) = make(onAir: false, playing: true, clock: clock)
        await transport.press(.playPause)
        #expect(!transport.isPlaying)
        clock.now = clock.now.addingTimeInterval(PlayerTransport.pressLifetime + 1)
        #expect(transport.isPlaying, "the observed state wins again")
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
