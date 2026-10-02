import AVFoundation
import MediaPlayer
import Observation
import ShazamKit

@MainActor
@Observable
final class NowPlayingObserver: NSObject, SHSessionDelegate {
    enum Mode: String, CaseIterable, Identifiable { case automatic, aroundMe; var id: String { rawValue } }
    var track: NowPlayingTrack?
    var mode: Mode = .automatic
    var isListeningAroundMe = false
    var status: String = "Checking Apple Music and Spotify"

    private let player = MPMusicPlayerController.systemMusicPlayer
    private let api = VibeAPI()
    private var pollTask: Task<Void, Never>?
    private let audioEngine = AVAudioEngine()
    private let shazam = SHSession()

    override init() { super.init(); shazam.delegate = self }

    func start(token: String) {
        stopPolling()
        player.beginGeneratingPlaybackNotifications()
        NotificationCenter.default.addObserver(self, selector: #selector(playerChanged), name: .MPMusicPlayerControllerNowPlayingItemDidChange, object: player)
        readAppleMusic()
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                if self?.track?.source != "Apple Music", let spotify = try? await self?.api.spotifyPlayback(token: token) { self?.track = spotify }
                try? await Task.sleep(for: .seconds(5))
                self?.readAppleMusic()
            }
        }
    }

    func stopPolling() { pollTask?.cancel(); pollTask = nil; player.endGeneratingPlaybackNotifications(); NotificationCenter.default.removeObserver(self) }

    func setAroundMe(_ enabled: Bool) async {
        if enabled {
            let granted = await AVAudioApplication.requestRecordPermission()
            guard granted else { status = "Microphone permission is required for Around Me"; return }
            let input = audioEngine.inputNode; let format = input.outputFormat(forBus: 0)
            input.installTap(onBus: 0, bufferSize: 4096, format: format) { [weak self] buffer, time in self?.shazam.matchStreamingBuffer(buffer, at: time) }
            do { try audioEngine.start(); isListeningAroundMe = true; status = "Listening around you" }
            catch { status = error.localizedDescription }
        } else {
            audioEngine.stop(); audioEngine.inputNode.removeTap(onBus: 0); isListeningAroundMe = false; status = "Checking Apple Music and Spotify"
        }
    }

    @objc private func playerChanged() { readAppleMusic() }
    private func readAppleMusic() {
        guard player.playbackState == .playing, let item = player.nowPlayingItem else { return }
        let artwork = item.artwork?.image(at: CGSize(width: 512, height: 512))
        track = NowPlayingTrack(id: item.persistentID.description, title: item.title ?? "Unknown song", artist: item.artist ?? "Unknown artist", album: item.albumTitle, artworkURL: nil, localArtwork: artwork, source: "Apple Music")
    }

    nonisolated func session(_ session: SHSession, didFind match: SHMatch) {
        guard let item = match.mediaItems.first else { return }
        let title = item[SHMediaItemProperty.title] as? String ?? "Unknown song"
        let artist = item[SHMediaItemProperty.artist] as? String ?? "Unknown artist"
        let artwork = item[SHMediaItemProperty.artworkURL] as? URL
        let id = (item[SHMediaItemProperty.shazamID] as? String) ?? "\(artist)-\(title)"
        Task { @MainActor in track = NowPlayingTrack(id: id, title: title, artist: artist, album: nil, artworkURL: artwork, localArtwork: nil, source: "Shazam · Around Me") }
    }
}
