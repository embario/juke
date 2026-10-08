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
    /// Whether something is audibly playing right now (Apple Music, linked
    /// Spotify, or a recent Around Me match). `track` keeps the last song.
    private(set) var isPlaying = false
    /// Position in the song of the latest Around Me match; differs per match.
    private(set) var shazamOffset: TimeInterval?

    private let player = MPMusicPlayerController.systemMusicPlayer
    private let api = VibeAPI()
    private var pollTask: Task<Void, Never>?
    private let audioEngine = AVAudioEngine()
    private let shazam = SHSession()
    private var spotifyPlaying = false
    private var aroundMeHeardAt: Date?

    override init() { super.init(); shazam.delegate = self }

    func start(token: String) {
        stopPolling()
        player.beginGeneratingPlaybackNotifications()
        NotificationCenter.default.addObserver(self, selector: #selector(playerChanged), name: .MPMusicPlayerControllerNowPlayingItemDidChange, object: player)
        readAppleMusic()
        pollTask = Task { [weak self] in
            while !Task.isCancelled {
                if self?.player.playbackState != .playing, let api = self?.api, let spotify = try? await api.spotifyPlayback(token: token) {
                    self?.spotifyPlaying = true
                    self?.track = spotify
                } else if self?.player.playbackState != .playing {
                    self?.spotifyPlaying = false
                }
                self?.refreshPlaying()
                try? await Task.sleep(for: .seconds(5))
                self?.readAppleMusic()
            }
        }
    }

    func stopPolling() {
        pollTask?.cancel(); pollTask = nil; player.endGeneratingPlaybackNotifications(); NotificationCenter.default.removeObserver(self)
        spotifyPlaying = false; aroundMeHeardAt = nil; isPlaying = false
    }

    private func refreshPlaying() {
        let heard = aroundMeHeardAt.map { Date().timeIntervalSince($0) < 45 } ?? false
        let value = player.playbackState == .playing || spotifyPlaying || heard
        if value != isPlaying { isPlaying = value }
    }

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
        refreshPlaying()
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
        let offset = item.matchOffset
        Task { @MainActor in
            aroundMeHeardAt = Date(); shazamOffset = offset; refreshPlaying()
            track = NowPlayingTrack(id: id, title: title, artist: artist, album: nil, artworkURL: artwork, localArtwork: nil, source: "Shazam · Around Me") }
    }
}
