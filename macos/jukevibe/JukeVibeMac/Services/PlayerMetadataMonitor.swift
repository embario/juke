import AppKit
import Darwin
import Foundation

struct PlayerMetadataSnapshot: Sendable {
    enum Provider: String, Sendable {
        case appleMusic = "Apple Music"
        case spotify = "Spotify"
    }

    let provider: Provider
    let track: RecognizedTrack
    let stableProviderID: String?
    let isPlaying: Bool
    let playbackPosition: TimeInterval
}

@MainActor
final class PlayerMetadataMonitor {
    var onSnapshot: ((PlayerMetadataSnapshot?) -> Void)?

    private enum PublishedState: Equatable {
        case unset
        case stopped
        case playing(String)
    }

    private let reader = AppleScriptPlayerMetadataReader()
    private var safetyRefreshTask: Task<Void, Never>?
    private var refreshTask: Task<Void, Never>?
    private var notificationTokens: [NSObjectProtocol] = []
    private var publishedState = PublishedState.unset
    private var applicationIsActive = true

    func start() {
        guard safetyRefreshTask == nil else { return }
        observePlayerChanges()
        requestRefresh()
        safetyRefreshTask = Task { @MainActor [weak self] in
            while !Task.isCancelled {
                guard let self else { return }
                let interval = Self.pollInterval(
                    applicationIsActive: applicationIsActive,
                    hasActivePlayback: publishedState != .stopped
                )
                do { try await Task.sleep(for: interval) }
                catch { return }
                requestRefresh()
            }
        }
    }

    func setApplicationActive(_ isActive: Bool) {
        applicationIsActive = isActive
        if isActive { requestRefresh() }
    }

    func refreshNow() {
        requestRefresh()
    }

    static func pollInterval(applicationIsActive: Bool, hasActivePlayback: Bool) -> Duration {
        switch (applicationIsActive, hasActivePlayback) {
        case (true, true): .seconds(20)
        case (true, false): .seconds(30)
        case (false, true): .seconds(60)
        case (false, false): .seconds(120)
        }
    }

    func stop() {
        safetyRefreshTask?.cancel()
        safetyRefreshTask = nil
        refreshTask?.cancel()
        refreshTask = nil
        let center = DistributedNotificationCenter.default()
        notificationTokens.forEach(center.removeObserver)
        notificationTokens.removeAll()
        publishedState = .unset
        onSnapshot?(nil)
    }

    private func observePlayerChanges() {
        guard notificationTokens.isEmpty else { return }
        let center = DistributedNotificationCenter.default()
        for name in ["com.spotify.client.PlaybackStateChanged", "com.apple.Music.playerInfo"] {
            notificationTokens.append(center.addObserver(
                forName: Notification.Name(name),
                object: nil,
                queue: .main
            ) { [weak self] _ in
                Task { @MainActor in self?.requestRefresh() }
            })
        }
    }

    private func requestRefresh() {
        guard refreshTask == nil else { return }
        let reader = reader
        refreshTask = Task { @MainActor [weak self, reader] in
            let snapshot = await reader.readCurrentPlayback()
            guard !Task.isCancelled, let self else { return }
            publishIfChanged(snapshot)
            refreshTask = nil
        }
    }

    private func publishIfChanged(_ snapshot: PlayerMetadataSnapshot?) {
        let nextState = snapshot.map { PublishedState.playing("\($0.contentIdentity)|\($0.isPlaying)") } ?? .stopped
        guard nextState != publishedState else { return }
        publishedState = nextState
        onSnapshot?(snapshot)
    }
}

extension PlayerMetadataSnapshot {
    var contentIdentity: String {
        "\(provider.rawValue)|\(track.identityKey)|\(track.album ?? "")"
    }
}

/// Runs player queries serially on a utility queue. The scripts execute in an
/// out-of-process AppleScript runner because `NSAppleScript` is main-thread-only.
/// Keeping one serial queue also guarantees that slow queries never overlap.
private final class AppleScriptPlayerMetadataReader: @unchecked Sendable {
    private let queue = DispatchQueue(label: "com.juke.vibe.player-metadata", qos: .utility)
    private let scriptRunner = AppleScriptProcessRunner()

    func readCurrentPlayback() async -> PlayerMetadataSnapshot? {
        await withCheckedContinuation { continuation in
            queue.async { [self] in
                continuation.resume(returning: readCurrentPlaybackSynchronously())
            }
        }
    }

    private func readCurrentPlaybackSynchronously() -> PlayerMetadataSnapshot? {
        if NSRunningApplication.runningApplications(withBundleIdentifier: "com.spotify.client").isEmpty == false,
           let values = scriptRunner.executeList(source: Self.spotifySource), values.count >= 9 {
            return snapshot(provider: .spotify, values: values, durationIsMilliseconds: true)
        }
        if NSRunningApplication.runningApplications(withBundleIdentifier: "com.apple.Music").isEmpty == false,
           let values = scriptRunner.executeList(source: Self.musicSource), values.count >= 9 {
            return snapshot(provider: .appleMusic, values: values, durationIsMilliseconds: false)
        }
        return nil
    }

    private func snapshot(
        provider: PlayerMetadataSnapshot.Provider,
        values: [String],
        durationIsMilliseconds: Bool
    ) -> PlayerMetadataSnapshot? {
        guard !values[1].isEmpty, !values[2].isEmpty else { return nil }
        let isPlaying = values[0].caseInsensitiveCompare("playing") == .orderedSame
        var duration = TimeInterval(values[7])
        if durationIsMilliseconds, let value = duration { duration = value / 1_000 }
        let position = TimeInterval(values[8]) ?? 0
        let externalURL = URL(string: values[6])
        let providerID = values[4].nilIfEmpty
        let namespace = provider == .spotify ? "spotify" : "apple_music"
        let track = RecognizedTrack(
            title: values[1],
            artist: values[2],
            album: values[3].nilIfEmpty,
            isrc: nil,
            artworkURL: URL(string: values[5]),
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
            isPlaying: isPlaying,
            playbackPosition: position
        )
    }

    private static let spotifySource =
        """
        with timeout of 2 seconds
            tell application id "com.spotify.client"
                set playbackState to player state as string
                if playbackState is not "stopped" then
                    set t to current track
                    set outputValues to {playbackState, name of t, artist of t, album of t, id of t, artwork url of t, spotify url of t, (duration of t as string), (player position as string)}
                    set AppleScript's text item delimiters to ASCII character 31
                    return outputValues as text
                end if
            end tell
        end timeout
        return {}
        """

    private static let musicSource =
        """
        with timeout of 2 seconds
            tell application id "com.apple.Music"
                set playbackState to player state as string
                if playbackState is not "stopped" then
                    set t to current track
                    set stableID to ""
                    try
                        set stableID to persistent ID of t
                    end try
                    set outputValues to {playbackState, name of t, artist of t, album of t, stableID, "", "", (duration of t as string), (player position as string)}
                    set AppleScript's text item delimiters to ASCII character 31
                    return outputValues as text
                end if
            end tell
        end timeout
        return {}
        """
}

struct AppleScriptProcessRunner: Sendable {
    func executeList(source: String) -> [String]? {
        let process = Process()
        let output = Pipe()
        process.executableURL = URL(fileURLWithPath: "/usr/bin/osascript")
        process.arguments = ["-e", source]
        process.standardOutput = output
        process.standardError = FileHandle.nullDevice

        let finished = DispatchSemaphore(value: 0)
        process.terminationHandler = { _ in finished.signal() }
        do { try process.run() }
        catch { return nil }
        if finished.wait(timeout: .now() + 3) == .timedOut {
            process.terminate()
            if finished.wait(timeout: .now() + 0.5) == .timedOut {
                Darwin.kill(process.processIdentifier, SIGKILL)
            }
            return nil
        }
        guard process.terminationStatus == 0 else { return nil }

        let data = output.fileHandleForReading.readDataToEndOfFile()
        guard var value = String(data: data, encoding: .utf8) else { return nil }
        value = value.trimmingCharacters(in: .newlines)
        guard !value.isEmpty else { return nil }
        return value.split(separator: "\u{1F}", omittingEmptySubsequences: false).map(String.init)
    }
}

enum LocalPlaybackControlError: LocalizedError {
    case unavailable

    var errorDescription: String? {
        "Apple Music did not accept the playback command."
    }
}

actor LocalPlayerPlaybackController {
    private let runner = AppleScriptProcessRunner()

    func toggleAppleMusicPlayback() throws {
        try execute("tell application id \"com.apple.Music\" to playpause")
    }

    func previousAppleMusicTrack() throws {
        try execute("tell application id \"com.apple.Music\" to previous track")
    }

    func nextAppleMusicTrack() throws {
        try execute("tell application id \"com.apple.Music\" to next track")
    }

    func seekAppleMusic(to position: TimeInterval) throws {
        let safePosition = max(0, position)
        try execute("tell application id \"com.apple.Music\" to set player position to \(safePosition)")
    }

    private func execute(_ command: String) throws {
        let source = "with timeout of 2 seconds\n\(command)\nreturn \"ok\"\nend timeout"
        guard runner.executeList(source: source) == ["ok"] else {
            throw LocalPlaybackControlError.unavailable
        }
    }
}

private extension String {
    var nilIfEmpty: String? { isEmpty ? nil : self }
}
