import AppKit
import Foundation

struct PlayerMetadataSnapshot: Sendable {
    enum Provider: String, Sendable {
        case appleMusic = "Apple Music"
        case spotify = "Spotify"
    }

    let provider: Provider
    let track: RecognizedTrack
    let stableProviderID: String?
    let playbackPosition: TimeInterval
}

@MainActor
final class PlayerMetadataMonitor {
    var onSnapshot: ((PlayerMetadataSnapshot?) -> Void)?

    private var pollTask: Task<Void, Never>?

    func start() {
        guard pollTask == nil else { return }
        pollTask = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                self?.onSnapshot?(self?.readCurrentPlayback())
                try? await Task.sleep(for: .seconds(2))
            }
        }
    }

    func stop() {
        pollTask?.cancel()
        pollTask = nil
        onSnapshot?(nil)
    }

    private func readCurrentPlayback() -> PlayerMetadataSnapshot? {
        if NSRunningApplication.runningApplications(withBundleIdentifier: "com.spotify.client").isEmpty == false,
           let values = executeList(spotifyScript), values.count >= 8 {
            return snapshot(provider: .spotify, values: values, durationIsMilliseconds: true)
        }
        if NSRunningApplication.runningApplications(withBundleIdentifier: "com.apple.Music").isEmpty == false,
           let values = executeList(musicScript), values.count >= 8 {
            return snapshot(provider: .appleMusic, values: values, durationIsMilliseconds: false)
        }
        return nil
    }

    private func snapshot(
        provider: PlayerMetadataSnapshot.Provider,
        values: [String],
        durationIsMilliseconds: Bool
    ) -> PlayerMetadataSnapshot? {
        guard !values[0].isEmpty, !values[1].isEmpty else { return nil }
        var duration = TimeInterval(values[6])
        if durationIsMilliseconds, let value = duration { duration = value / 1_000 }
        let position = TimeInterval(values[7]) ?? 0
        let externalURL = URL(string: values[5])
        let providerID = values[3].nilIfEmpty
        let namespace = provider == .spotify ? "spotify" : "apple_music"
        let track = RecognizedTrack(
            title: values[0],
            artist: values[1],
            album: values[2].nilIfEmpty,
            isrc: nil,
            artworkURL: URL(string: values[4]),
            appleMusicURL: provider == .appleMusic ? externalURL : nil,
            shazamID: nil,
            matchOffset: position,
            matchConfidence: 1,
            trackDuration: duration,
            providerNamespace: namespace,
            providerTrackID: providerID,
            providerPlaybackURL: externalURL
        )
        return PlayerMetadataSnapshot(
            provider: provider,
            track: track,
            stableProviderID: providerID,
            playbackPosition: position
        )
    }

    private func executeList(_ source: String) -> [String]? {
        var error: NSDictionary?
        guard let result = NSAppleScript(source: source)?.executeAndReturnError(&error),
              error == nil,
              result.numberOfItems > 0 else { return nil }
        return (1...result.numberOfItems).map { result.atIndex($0)?.stringValue ?? "" }
    }

    private var spotifyScript: String {
        """
        tell application id "com.spotify.client"
            if player state is playing then
                set t to current track
                return {name of t, artist of t, album of t, id of t, artwork url of t, spotify url of t, (duration of t as string), (player position as string)}
            end if
        end tell
        return {}
        """
    }

    private var musicScript: String {
        """
        tell application id "com.apple.Music"
            if player state is playing then
                set t to current track
                set stableID to ""
                try
                    set stableID to persistent ID of t
                end try
                return {name of t, artist of t, album of t, stableID, "", "", (duration of t as string), (player position as string)}
            end if
        end tell
        return {}
        """
    }
}

private extension String {
    var nilIfEmpty: String? { isEmpty ? nil : self }
}
