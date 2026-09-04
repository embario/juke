import AppKit
import Darwin
import Foundation
import ScriptingBridge

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

    private let reader = ScriptingBridgePlayerMetadataReader()
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
        if isActive, safetyRefreshTask != nil { requestRefresh() }
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

/// Reads scriptable-player metadata in the signed app process so the automation
/// permission belongs to Juke Vibe. Launching `/usr/bin/osascript` from a
/// sandboxed app loses that entitlement and can silently return no metadata.
/// All synchronous Apple events remain isolated from the main thread.
private final class ScriptingBridgePlayerMetadataReader: @unchecked Sendable {
    private let queue = DispatchQueue(label: "com.juke.vibe.player-metadata", qos: .utility)

    func readCurrentPlayback() async -> PlayerMetadataSnapshot? {
        await withCheckedContinuation { continuation in
            queue.async { [self] in
                continuation.resume(returning: readCurrentPlaybackSynchronously())
            }
        }
    }

    private func readCurrentPlaybackSynchronously() -> PlayerMetadataSnapshot? {
        if let snapshot = snapshot(
            provider: .spotify,
            bundleIdentifier: "com.spotify.client",
            durationIsMilliseconds: true
        ) {
            return snapshot
        }
        if let snapshot = snapshot(
            provider: .appleMusic,
            bundleIdentifier: "com.apple.Music",
            durationIsMilliseconds: false
        ) {
            return snapshot
        }
        return nil
    }

    private func snapshot(
        provider: PlayerMetadataSnapshot.Provider,
        bundleIdentifier: String,
        durationIsMilliseconds: Bool
    ) -> PlayerMetadataSnapshot? {
        guard NSRunningApplication.runningApplications(withBundleIdentifier: bundleIdentifier).isEmpty == false,
              let application = SBApplication(bundleIdentifier: bundleIdentifier),
              application.isRunning,
              let state = application.value(forKey: "playerState") as? NSNumber,
              state.uint32Value != Self.stoppedState,
              let currentTrack = application.value(forKey: "currentTrack") as? SBObject,
              let title = currentTrack.value(forKey: "name") as? String,
              let artist = currentTrack.value(forKey: "artist") as? String,
              !title.isEmpty,
              !artist.isEmpty else { return nil }

        let isPlaying = state.uint32Value == Self.playingState
        var duration = (currentTrack.value(forKey: "duration") as? NSNumber)?.doubleValue
        if durationIsMilliseconds, let value = duration { duration = value / 1_000 }
        let position = (application.value(forKey: "playerPosition") as? NSNumber)?.doubleValue ?? 0
        let rawProviderID = stringValue(
            currentTrack,
            keys: provider == .spotify ? ["id"] : ["persistentID"]
        )
        let providerID = provider == .spotify
            ? rawProviderID?.split(separator: ":").last.map(String.init)
            : rawProviderID
        let playbackURLString = provider == .spotify
            ? stringValue(currentTrack, keys: ["spotifyUrl"])
            : nil
        let externalURL = playbackURLString.flatMap(URL.init(string:))
        let artworkURLString = provider == .spotify
            ? stringValue(currentTrack, keys: ["artworkUrl"])
            : nil
        let namespace = provider == .spotify ? "spotify" : "apple_music"
        let track = RecognizedTrack(
            title: title,
            artist: artist,
            album: (currentTrack.value(forKey: "album") as? String)?.nilIfEmpty,
            isrc: nil,
            artworkURL: artworkURLString.flatMap(URL.init(string:)),
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

    private func stringValue(_ object: SBObject, keys: [String]) -> String? {
        for key in keys {
            if let value = object.value(forKey: key) as? String, !value.isEmpty { return value }
        }
        return nil
    }

    private static let stoppedState: UInt32 = 0x6B50_5353 // 'kPSS'
    private static let playingState: UInt32 = 0x6B50_5350 // 'kPSP'
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
