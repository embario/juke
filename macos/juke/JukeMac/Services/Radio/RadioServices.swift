import Foundation

// MARK: - Seams

/// The radio endpoints `RadioController` uses. `JukeAPI` is the production
/// implementation; tests and UI-test fixtures provide their own.
protocol RadioBackend: Sendable {
    func stations() async throws -> [Radio.Station]
    func createStation(name: String?, seeds: [Radio.Seed], feelings: [String]) async throws -> Radio.Station
    func updateStation(_ id: Radio.ID, _ changes: Radio.UpdateStationRequest) async throws -> Radio.Station
    func addExclusion(stationID: Radio.ID, _ exclusion: Radio.CreateExclusionRequest) async throws -> Radio.Exclusion
    func deleteExclusion(_ id: Radio.ID) async throws
    func setReactions(spotifyTrackID: String, stationID: Radio.ID?, reactions: [String]) async throws -> Radio.ReactionsResponse
    func playRadio(stationID: Radio.ID, mode: Radio.PlayMode, deviceID: String?, recentTrackIDs: [String]) async throws -> Radio.PlayResponse
    func postEvent(_ event: Radio.EventRequest) async throws
    func sessionSummary() async throws -> Radio.SessionSummary
}

extension JukeAPI: RadioBackend {
    func playRadio(stationID: Radio.ID, mode: Radio.PlayMode, deviceID: String?, recentTrackIDs: [String]) async throws -> Radio.PlayResponse {
        try await play(stationID: stationID, mode: mode, deviceID: deviceID,
                       recentTrackIDs: recentTrackIDs.isEmpty ? nil : Array(recentTrackIDs.suffix(50)))
    }
}

/// What Spotify is doing right now, from `GET /api/v1/playback/state/`.
struct RadioPlaybackSnapshot: Equatable, Sendable {
    var trackID: String?
    var title: String?
    var artist: String?
    var artistID: String?
    var album: String?
    var albumID: String?
    var artworkURL: URL?
    var durationMs: Int
    var progressMs: Int
    var isPlaying: Bool
    var deviceID: String?
    var deviceName: String?

    init(trackID: String?, title: String? = nil, artist: String? = nil, artistID: String? = nil, album: String? = nil,
         albumID: String? = nil, artworkURL: URL? = nil, durationMs: Int, progressMs: Int, isPlaying: Bool,
         deviceID: String? = nil, deviceName: String? = nil) {
        self.trackID = trackID
        self.title = title
        self.artist = artist
        self.artistID = artistID
        self.album = album
        self.albumID = albumID
        self.artworkURL = artworkURL
        self.durationMs = durationMs
        self.progressMs = progressMs
        self.isPlaying = isPlaying
        self.deviceID = deviceID
        self.deviceName = deviceName
    }

    init(_ state: JukePlaybackState) {
        let track = state.track
        self.init(
            trackID: track?.id ?? track?.uri?.split(separator: ":").last.map(String.init),
            title: track?.name,
            artist: track?.artists?.compactMap(\.name).filter { !$0.isEmpty }.joined(separator: ", "),
            artistID: track?.artists?.first?.id,
            album: track?.album?.name,
            albumID: track?.album?.id,
            artworkURL: track?.artworkURL,
            durationMs: track?.durationMs ?? 0,
            progressMs: state.progressMs,
            isPlaying: state.isPlaying,
            deviceID: state.device?.id,
            deviceName: state.device?.name
        )
    }

    /// Decodes the `state` object a `POST radio/play` response carries.
    init?(json: Radio.JSONValue?) {
        guard let json, json != .null,
              let data = try? JSONEncoder().encode(json),
              let state = try? JSONDecoder().decode(JukePlaybackState.self, from: data) else { return nil }
        self.init(state)
    }

    /// The playing song as a radio `Track`, for adopting whatever Spotify
    /// is already playing when radio resumes on launch.
    var radioTrack: Radio.Track? {
        guard let trackID, !trackID.isEmpty else { return nil }
        return Radio.Track(
            spotifyId: trackID, uri: "spotify:track:\(trackID)", title: title ?? "Unknown song",
            artist: artist ?? "", artistId: artistID, album: album, albumId: albumID,
            artworkUrl: artworkURL?.absoluteString, durationMs: durationMs
        )
    }
}

/// Spotify transport controls through the Juke backend.
protocol RadioPlaybackControlling: Sendable {
    /// `nil` when Spotify has no active device.
    func state() async throws -> RadioPlaybackSnapshot?
    func pause(deviceID: String?) async throws
    func resume(deviceID: String?) async throws
    func next(deviceID: String?) async throws
    func seek(to position: TimeInterval, deviceID: String?) async throws
}

/// Production playback: the existing `PlaybackClient` with the session token.
struct SpotifyRadioPlayback: RadioPlaybackControlling {
    let client: PlaybackClient
    let token: @Sendable () async -> String?

    init(client: PlaybackClient = PlaybackClient(), token: @escaping @Sendable () async -> String?) {
        self.client = client
        self.token = token
    }

    private func authorized() async throws -> String {
        guard let token = await token(), !token.isEmpty else { throw JukeAPIError.notSignedIn }
        return token
    }

    func state() async throws -> RadioPlaybackSnapshot? {
        try await client.fetchSpotifyState(token: authorized()).map(RadioPlaybackSnapshot.init)
    }

    func pause(deviceID: String?) async throws { _ = try await client.pause(token: authorized(), deviceID: deviceID) }
    func resume(deviceID: String?) async throws { _ = try await client.resume(token: authorized(), deviceID: deviceID) }
    func next(deviceID: String?) async throws { _ = try await client.next(token: authorized(), deviceID: deviceID) }
    func seek(to position: TimeInterval, deviceID: String?) async throws {
        _ = try await client.seek(token: authorized(), deviceID: deviceID, position: position)
    }
}

// MARK: - Preferences

/// Small radio preferences kept in `UserDefaults`.
struct RadioPreferences {
    private let defaults: UserDefaults
    private enum Key {
        static let hasTunedIn = "juke.radio.hasTunedIn"
        static let wasPlaying = "juke.radio.wasPlaying"
        static let lastStation = "juke.radio.lastStationID"
        static let customReactions = "juke.radio.customReactions"
    }

    init(defaults: UserDefaults = .standard) { self.defaults = defaults }

    /// Set after the first successful "Tune in"; afterwards the card skips the first-run screen.
    var hasTunedIn: Bool {
        get { defaults.bool(forKey: Key.hasTunedIn) }
        nonmutating set { defaults.set(newValue, forKey: Key.hasTunedIn) }
    }

    /// Whether radio was on the air when the app last ran (resume on launch).
    var wasPlaying: Bool {
        get { defaults.bool(forKey: Key.wasPlaying) }
        nonmutating set { defaults.set(newValue, forKey: Key.wasPlaying) }
    }

    var lastStationID: Radio.ID? {
        get { defaults.string(forKey: Key.lastStation).map { Radio.ID($0) } }
        nonmutating set { defaults.set(newValue?.rawValue, forKey: Key.lastStation) }
    }

    /// The listener's own emoji and words, offered again on later songs.
    var customReactions: [String] {
        get { defaults.stringArray(forKey: Key.customReactions) ?? [] }
        nonmutating set { defaults.set(Array(newValue.suffix(24)), forKey: Key.customReactions) }
    }
}

// MARK: - Problems

/// Problems the radio explains on the card, each with a calm next step.
enum RadioIssue: Equatable, Sendable {
    /// 400 `playback_provider_not_linked`: show "Connect Spotify".
    case spotifyNotLinked
    /// Playback `state` is null: "Open Spotify on any device".
    case noActiveDevice
    /// 502 `playback_provider_failure`.
    case spotifyFailed
    /// 409 `radio_no_tracks` for this station.
    case noTracks(stationName: String)
    case signedOut
    /// Anything else (network, server); the message is user-facing.
    case unavailable(String)

    var message: String {
        switch self {
        case .spotifyNotLinked: "Radio plays through Spotify. Connect your account to tune in."
        case .noActiveDevice: "Open Spotify on any device, then press play."
        case .spotifyFailed: "Spotify didn’t answer. Give it a moment and try again."
        case .noTracks(let name): "\(name) has nothing new right now. Tune to another station."
        case .signedOut: "Sign in to Juke to play radio."
        case .unavailable(let message): message
        }
    }

    /// Classifies an error from `RadioBackend` or `RadioPlaybackControlling`.
    static func from(_ error: Error, stationName: String) -> RadioIssue {
        if let api = error as? JukeAPIError {
            switch api.code {
            case "playback_provider_not_linked", "playback_provider_unsupported": return .spotifyNotLinked
            case "playback_provider_failure": return .spotifyFailed
            case "radio_no_tracks": return .noTracks(stationName: stationName)
            default: break
            }
            switch api {
            case .notSignedIn, .unauthorized: return .signedOut
            default: return .unavailable(api.errorDescription ?? "Juke radio is unavailable right now.")
            }
        }
        if let playback = error as? PlaybackClientError {
            switch playback {
            case .providerNotConnected: return .spotifyNotLinked
            case .authenticationExpired: return .signedOut
            case .unavailable(let status) where status == 502: return .spotifyFailed
            default: return .unavailable(playback.errorDescription ?? "Spotify playback is unavailable right now.")
            }
        }
        return .unavailable("Juke radio is unavailable right now.")
    }
}
