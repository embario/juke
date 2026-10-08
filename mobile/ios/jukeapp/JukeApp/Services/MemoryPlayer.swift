import Foundation
import MediaPlayer
import Observation
import UIKit

/// What `MemoryPlayer` needs from Spotify; `PlaybackClient` is the real one.
protocol MemorySpotifyPlaying: Sendable {
    func play(token: String, spotifyID: String, startSeconds: Double) async throws -> JukePlaybackState?
    func state(token: String) async throws -> JukePlaybackState?
    func pause(token: String, deviceID: String?) async throws -> JukePlaybackState?
}

extension PlaybackClient: MemorySpotifyPlaying {
    func play(token: String, spotifyID: String, startSeconds: Double) async throws -> JukePlaybackState? {
        try await play(token: token, spotifyID: spotifyID, kind: "tracks", deviceID: nil, startSeconds: startSeconds)
    }
    func state(token: String) async throws -> JukePlaybackState? { try await fetchSpotifyState(token: token) }
}

/// Plays the song saved with a memory, from the saved moment, and stops at its end.
/// Spotify goes through Juke's playback API (needs an active device, like radio);
/// Apple Music uses the system player for library songs. Anything else, or any
/// failure, hands the song to the provider's app instead of guessing.
@MainActor
@Observable
final class MemoryPlayer {
    private(set) var isBusy = false
    var message: String?

    @ObservationIgnored private let spotify: any MemorySpotifyPlaying
    @ObservationIgnored private let token: @MainActor () -> String?
    @ObservationIgnored private let open: @MainActor (URL) -> Void
    @ObservationIgnored private let playApple: @MainActor (_ id: String, _ start: Double) async throws -> Void
    @ObservationIgnored private let appleTime: @MainActor () -> Double?
    @ObservationIgnored private let pauseApple: @MainActor () -> Void
    @ObservationIgnored private let sleep: @MainActor (Double) async throws -> Void
    /// Told when a memory song starts, so recognition can ignore it.
    @ObservationIgnored var marked: @MainActor (MemoryPlaybackMark) -> Void
    @ObservationIgnored private var operation: UUID?
    @ObservationIgnored private var watcher: Task<Void, Never>?

    init(
        spotify: any MemorySpotifyPlaying = PlaybackClient(),
        token: @escaping @MainActor () -> String?,
        marked: @escaping @MainActor (MemoryPlaybackMark) -> Void = { _ in },
        open: @escaping @MainActor (URL) -> Void = { UIApplication.shared.open($0) },
        playApple: @escaping @MainActor (String, Double) async throws -> Void = MemoryPlayer.systemPlayApple,
        appleTime: @escaping @MainActor () -> Double? = { MPMusicPlayerController.systemMusicPlayer.currentPlaybackTime },
        pauseApple: @escaping @MainActor () -> Void = { MPMusicPlayerController.systemMusicPlayer.pause() },
        sleep: @escaping @MainActor (Double) async throws -> Void = { try await Task.sleep(for: .seconds($0)) }
    ) {
        self.spotify = spotify; self.token = token; self.marked = marked; self.open = open
        self.playApple = playApple; self.appleTime = appleTime; self.pauseApple = pauseApple; self.sleep = sleep
    }

    func play(_ song: MemorySong) async {
        cancel()
        guard !isBusy else { return }
        message = nil
        marked(MemoryPlaybackMark(providerID: song.providerID, title: song.title, artist: song.artist, startedAt: .now))
        let id = UUID()
        operation = id
        isBusy = true
        defer { isBusy = false }
        do {
            let request = try MemoryPlaybackRequest(
                provider: song.provider, providerID: song.providerID, playbackURL: song.playbackURL,
                startSeconds: song.startSeconds, endSeconds: song.endSeconds
            )
            switch request.provider {
            case .spotify: await playSpotify(request, id: id)
            case .appleMusic: await playAppleMusic(request, id: id)
            }
        } catch { message = error.localizedDescription }
    }

    func cancel() {
        operation = nil
        watcher?.cancel()
        watcher = nil
    }

    private func playSpotify(_ request: MemoryPlaybackRequest, id: UUID) async {
        guard let token = token(), let trackID = request.providerID else {
            handOff(request, "Sign in to Juke with Spotify linked to control this song. Continue in Spotify.")
            return
        }
        do {
            _ = try await spotify.play(token: token, spotifyID: trackID, startSeconds: request.startSeconds)
            guard operation == id else { return }
            let verified = try await spotify.state(token: token)
            guard operation == id, let end = request.endSeconds else { return }
            guard let verified, verified.track?.id == trackID, verified.isPlaying, let device = verified.device?.id else {
                message = "Spotify opened the song, but could not confirm its active device. The moment will not stop automatically."
                return
            }
            watchSpotify(MemorySegmentGuard(trackID: trackID, deviceID: device, endSeconds: end), token: token, id: id)
        } catch {
            guard operation == id else { return }
            handOff(request, "\(error.localizedDescription) Continue in Spotify; the saved moment can't be timed there.")
        }
    }

    private func watchSpotify(_ segment: MemorySegmentGuard, token: String, id: UUID) {
        watcher = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                do { try await self?.sleep(1) } catch { return }
                guard let self, self.operation == id else { return }
                do {
                    guard let state = try await self.spotify.state(token: token), self.operation == id else { self.cancel(); return }
                    switch segment.decision(trackID: state.track?.id, deviceID: state.device?.id,
                                            isPlaying: state.isPlaying, position: Double(state.progressMs) / 1_000) {
                    case .keepWaiting: continue
                    case .cancel: self.cancel(); return
                    case .pause:
                        _ = try await self.spotify.pause(token: token, deviceID: segment.deviceID)
                        self.cancel(); return
                    }
                } catch {
                    guard self.operation == id else { return }
                    self.message = "Moment timing stopped: \(error.localizedDescription) Playback may continue in Spotify."
                    self.cancel(); return
                }
            }
        }
    }

    private func playAppleMusic(_ request: MemoryPlaybackRequest, id: UUID) async {
        guard let song = request.providerID else {
            handOff(request, "Continue in Apple Music.")
            return
        }
        do {
            try await playApple(song, request.startSeconds)
            guard operation == id, let end = request.endSeconds else { return }
            watcher = Task { @MainActor [weak self] in
                while !Task.isCancelled {
                    do { try await self?.sleep(0.5) } catch { return }
                    guard let self, self.operation == id else { return }
                    guard let time = self.appleTime() else { self.cancel(); return }
                    if time >= end { self.pauseApple(); self.cancel(); return }
                }
            }
        } catch {
            guard operation == id else { return }
            handOff(request, "\(error.localizedDescription) Continue in Apple Music.")
        }
    }

    private func handOff(_ request: MemoryPlaybackRequest, _ explanation: String) {
        cancel()
        message = explanation
        if let url = request.playbackURL { open(url) }
    }

    /// Library songs (16-hex persistent IDs) play through the media library;
    /// catalog IDs need an Apple Music subscription and play by store ID.
    private static func systemPlayApple(_ id: String, _ start: Double) async throws {
        let player = MPMusicPlayerController.systemMusicPlayer
        if MemoryPlaybackRequest.isAppleLibraryID(id), let value = UInt64(id, radix: 16) {
            let query = MPMediaQuery.songs()
            query.addFilterPredicate(MPMediaPropertyPredicate(value: NSNumber(value: value), forProperty: MPMediaItemPropertyPersistentID))
            guard let item = query.items?.first else { throw PlaybackClientError.invalidMemorySong }
            player.setQueue(with: MPMediaItemCollection(items: [item]))
        } else {
            player.setQueue(with: [id])
        }
        try await player.prepareToPlay()
        player.play()
        if start > 0 { player.currentPlaybackTime = start }
    }
}
