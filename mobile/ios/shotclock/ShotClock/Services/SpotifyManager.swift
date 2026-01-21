import SwiftUI
import AVFoundation
import SpotifyiOS

@MainActor
final class SpotifyManager: NSObject, ObservableObject {
    static let shared = SpotifyManager()

    // MARK: - Configuration
    // Replace with your Spotify Developer Dashboard credentials
    static let clientID = "0bf7db39475a4c05a1a621216dcdcba6"
    static let redirectURI = URL(string: "shotclock://spotify-callback")!

    // MARK: - Published State
    @Published var isConnected = false
    @Published var isConnecting = false
    @Published var isPreviewMode = false
    @Published var currentTrackURI: String?
    @Published var errorMessage: String?

    // MARK: - SDK Objects
    private var appRemote: SPTAppRemote?
    private var accessToken: String?

    // MARK: - Preview Fallback (AVPlayer)
    private var previewPlayer: AVPlayer?

    private override init() {
        super.init()
        setupAppRemote()
    }

    private func setupAppRemote() {
        let configuration = SPTConfiguration(
            clientID: Self.clientID,
            redirectURL: Self.redirectURI
        )
        appRemote = SPTAppRemote(configuration: configuration, logLevel: .debug)
        appRemote?.delegate = self
    }

    // MARK: - Authentication

    /// Initiates Spotify authentication by opening the Spotify app
    func authorize() {
        guard let appRemote else { return }

        guard UIApplication.shared.canOpenURL(URL(string: "spotify:")!) else {
            // Fall back to preview mode using AVPlayer
            isPreviewMode = true
            isConnected = true
            errorMessage = nil
            return
        }

        isConnecting = true
        errorMessage = nil
        appRemote.authorizeAndPlayURI("")
    }

    /// Called from the app's URL handler when Spotify redirects back
    func handleRedirectURL(_ url: URL) {
        guard let appRemote else { return }
        let parameters = appRemote.authorizationParameters(from: url)

        if let token = parameters?[SPTAppRemoteAccessTokenKey] {
            accessToken = token
            appRemote.connectionParameters.accessToken = token
            connect()
        } else if let errorDescription = parameters?[SPTAppRemoteErrorDescriptionKey] {
            errorMessage = errorDescription
            isConnecting = false
        } else {
            errorMessage = "Spotify authorization failed. Please try again."
            isConnecting = false
        }
    }

    // MARK: - Connection

    func connect() {
        guard let appRemote, accessToken != nil else { return }
        isConnecting = true
        appRemote.connect()
    }

    func disconnect() {
        appRemote?.disconnect()
        isConnected = false
    }

    // MARK: - Playback Control

    func play(spotifyURI: String) {
        appRemote?.playerAPI?.play(spotifyURI, callback: { [weak self] _, error in
            if let error {
                Task { @MainActor in
                    self?.errorMessage = error.localizedDescription
                }
            } else {
                Task { @MainActor in
                    self?.currentTrackURI = spotifyURI
                }
            }
        })
    }

    func pause() {
        if isPreviewMode {
            pausePreview()
            return
        }
        appRemote?.playerAPI?.pause({ [weak self] _, error in
            if let error {
                Task { @MainActor in
                    self?.errorMessage = error.localizedDescription
                }
            }
        })
    }

    func resume() {
        if isPreviewMode {
            resumePreview()
            return
        }
        appRemote?.playerAPI?.resume({ [weak self] _, error in
            if let error {
                Task { @MainActor in
                    self?.errorMessage = error.localizedDescription
                }
            }
        })
    }

    func seek(toPosition positionMs: Int) {
        if isPreviewMode {
            let seconds = CMTime(value: CMTimeValue(positionMs), timescale: 1000)
            previewPlayer?.seek(to: seconds)
            return
        }
        appRemote?.playerAPI?.seek(toPosition: positionMs, callback: { [weak self] _, error in
            if let error {
                Task { @MainActor in
                    self?.errorMessage = error.localizedDescription
                }
            }
        })
    }

    // MARK: - Preview Fallback Playback

    func playPreview(url: String) {
        guard let audioURL = URL(string: url) else {
            errorMessage = "No preview available for this track."
            return
        }
        let item = AVPlayerItem(url: audioURL)
        previewPlayer = AVPlayer(playerItem: item)
        previewPlayer?.play()
    }

    func pausePreview() {
        previewPlayer?.pause()
    }

    func resumePreview() {
        previewPlayer?.play()
    }
}

// MARK: - SPTAppRemoteDelegate

extension SpotifyManager: SPTAppRemoteDelegate {
    nonisolated func appRemoteDidEstablishConnection(_ appRemote: SPTAppRemote) {
        Task { @MainActor in
            self.isConnected = true
            self.isConnecting = false
            self.errorMessage = nil
            appRemote.playerAPI?.delegate = self
        }
    }

    nonisolated func appRemote(_ appRemote: SPTAppRemote, didFailConnectionAttemptWithError error: Error?) {
        Task { @MainActor in
            self.isConnected = false
            self.isConnecting = false
            self.errorMessage = error?.localizedDescription ?? "Connection failed"
        }
    }

    nonisolated func appRemote(_ appRemote: SPTAppRemote, didDisconnectWithError error: Error?) {
        Task { @MainActor in
            self.isConnected = false
            self.isConnecting = false
        }
    }
}

// MARK: - SPTAppRemotePlayerStateDelegate

extension SpotifyManager: SPTAppRemotePlayerStateDelegate {
    nonisolated func playerStateDidChange(_ playerState: SPTAppRemotePlayerState) {
        Task { @MainActor in
            self.currentTrackURI = playerState.track.uri
        }
    }
}
