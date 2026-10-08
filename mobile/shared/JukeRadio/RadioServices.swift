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
    /// `spotify:track:…`, or an episode/other URI. `nil` when unknown.
    var uri: String?
    /// Spotify's `currently_playing_type` when the backend reports it.
    var contentType: String?
    /// The backend's state, passed on to the recognition helper so the app
    /// polls Spotify only once while radio is on. Not part of equality.
    var raw: JukePlaybackState?

    static func == (lhs: Self, rhs: Self) -> Bool {
        lhs.trackID == rhs.trackID && lhs.title == rhs.title && lhs.artist == rhs.artist && lhs.artistID == rhs.artistID
            && lhs.album == rhs.album && lhs.albumID == rhs.albumID && lhs.artworkURL == rhs.artworkURL
            && lhs.durationMs == rhs.durationMs && lhs.progressMs == rhs.progressMs && lhs.isPlaying == rhs.isPlaying
            && lhs.deviceID == rhs.deviceID && lhs.deviceName == rhs.deviceName && lhs.uri == rhs.uri
    }

    /// A podcast episode is playing (never a station song).
    var isEpisode: Bool {
        contentType == "episode" || (uri?.hasPrefix("spotify:episode:") ?? false)
    }

    /// A song (not a podcast episode or ad).
    var isTrack: Bool {
        guard let trackID, !trackID.isEmpty else { return false }
        return uri.map { $0.hasPrefix("spotify:track:") } ?? true
    }

    init(trackID: String?, title: String? = nil, artist: String? = nil, artistID: String? = nil, album: String? = nil,
         albumID: String? = nil, artworkURL: URL? = nil, durationMs: Int, progressMs: Int, isPlaying: Bool,
         deviceID: String? = nil, deviceName: String? = nil, uri: String? = nil) {
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
        self.uri = uri
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
            deviceName: state.device?.name,
            uri: track?.uri
        )
        contentType = state.currentlyPlayingType
        raw = state
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
        guard isTrack, let trackID else { return nil }
        return Radio.Track(
            spotifyId: trackID, uri: "spotify:track:\(trackID)", title: title ?? "Unknown song",
            artist: artist ?? "", artistId: artistID, album: album, albumId: albumID,
            artworkUrl: artworkURL?.absoluteString, durationMs: durationMs
        )
    }
}

/// Spotify transport controls through the Juke backend.
protocol RadioPlaybackControlling: Sendable {
    /// `nil` when Spotify reports no player. That is normal for a player that has been paused
    /// for a while, so it does not by itself mean the device is gone.
    func state() async throws -> RadioPlaybackSnapshot?
    func pause(deviceID: String?) async throws
    /// Continues what Spotify had paused. Returns Spotify's state after the command, or `nil`
    /// when it reported none (no player took the command).
    @discardableResult
    func resume(deviceID: String?) async throws -> RadioPlaybackSnapshot?
    /// Starts one song at `position`. Unlike `resume` this does not depend on what Spotify
    /// remembers, so it also works after the Spotify app was reopened.
    @discardableResult
    func play(trackID: String, at position: TimeInterval, deviceID: String?) async throws -> RadioPlaybackSnapshot?
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
    func resume(deviceID: String?) async throws -> RadioPlaybackSnapshot? {
        try await client.resume(token: authorized(), deviceID: deviceID).map(RadioPlaybackSnapshot.init)
    }
    func play(trackID: String, at position: TimeInterval, deviceID: String?) async throws -> RadioPlaybackSnapshot? {
        try await client.play(token: authorized(), spotifyID: trackID, kind: "tracks", deviceID: deviceID, startSeconds: max(0, position))
            .map(RadioPlaybackSnapshot.init)
    }
    func next(deviceID: String?) async throws { _ = try await client.next(token: authorized(), deviceID: deviceID) }
    func seek(to position: TimeInterval, deviceID: String?) async throws {
        _ = try await client.seek(token: authorized(), deviceID: deviceID, position: position)
    }
}

// MARK: - Preferences

/// Small radio preferences kept in `UserDefaults`.
struct RadioPreferences {
    private let defaults: UserDefaults
    /// Per-account keys: radio state belongs to the signed-in listener.
    let accountID: String?

    init(defaults: UserDefaults = .standard, accountID: String? = nil) {
        self.defaults = defaults
        self.accountID = accountID
    }

    /// The same store, scoped to another account.
    func scoped(to accountID: String?) -> RadioPreferences { RadioPreferences(defaults: defaults, accountID: accountID) }

    private func key(_ name: String) -> String {
        "juke.radio.\(name)" + (accountID.map { ".\($0)" } ?? "")
    }

    /// Set after the first successful "Tune in"; afterwards the card skips the first-run screen.
    var hasTunedIn: Bool {
        get { defaults.bool(forKey: key("hasTunedIn")) }
        nonmutating set { defaults.set(newValue, forKey: key("hasTunedIn")) }
    }

    /// Whether radio was on the air when the app last ran (resume on launch).
    var wasPlaying: Bool {
        get { defaults.bool(forKey: key("wasPlaying")) }
        nonmutating set { defaults.set(newValue, forKey: key("wasPlaying")) }
    }

    var lastStationID: Radio.ID? {
        get { defaults.string(forKey: key("lastStationID")).map { Radio.ID($0) } }
        nonmutating set { defaults.set(newValue?.rawValue, forKey: key("lastStationID")) }
    }

    /// The last few songs radio picked, so a relaunch can tell a radio song
    /// still playing in Spotify from anything else.
    var recentRadioTrackIDs: [String] {
        get { defaults.stringArray(forKey: key("recentTrackIDs")) ?? [] }
        nonmutating set { defaults.set(Array(newValue.suffix(10)), forKey: key("recentTrackIDs")) }
    }

    /// The Spotify device radio last played on. Used only to recover playback when Spotify
    /// reports no active device; a normal start never targets it.
    var lastDeviceID: String? {
        get { defaults.string(forKey: key("lastDeviceID")) }
        nonmutating set { defaults.set(newValue, forKey: key("lastDeviceID")) }
    }

    /// The song radio was paused on, kept so a relaunch shows it paused and can resume it.
    var pausedSession: RadioPausedSession? {
        get { defaults.data(forKey: key("pausedSession")).flatMap { try? JSONDecoder().decode(RadioPausedSession.self, from: $0) } }
        nonmutating set {
            if let newValue, let data = try? JSONEncoder().encode(newValue) {
                defaults.set(data, forKey: key("pausedSession"))
            } else {
                defaults.removeObject(forKey: key("pausedSession"))
            }
        }
    }

    /// The listener's own emoji and words, offered again on later songs.
    var customReactions: [String] {
        get { defaults.stringArray(forKey: key("customReactions")) ?? [] }
        nonmutating set { defaults.set(Array(newValue.suffix(24)), forKey: key("customReactions")) }
    }
}

/// A paused radio song: enough to show it again and resume it at the same place.
struct RadioPausedSession: Codable, Equatable, Sendable {
    var track: Radio.Track
    var position: TimeInterval
    var stationID: Radio.ID?
}

/// What the radio's transport is doing, for the player controls and their status line.
enum RadioPlaybackStatus: Equatable, Sendable {
    /// Radio is not in charge of playback.
    case offAir
    case playing
    /// Paused, by the listener or in Spotify. Play resumes it.
    case paused
    /// Play was pressed and Spotify has not confirmed yet.
    case resuming
    /// Spotify did not respond: its app has to be opened before radio can play.
    case deviceUnavailable

    /// A short line for the compact player; `nil` while a song plays normally.
    var caption: String? {
        switch self {
        case .offAir, .playing: nil
        case .paused: "Paused"
        case .resuming: "Waiting for Spotify…"
        case .deviceUnavailable: "Open Spotify to keep playing"
        }
    }
}

// MARK: - Problems

/// Problems the radio explains on the card, each with a calm next step.
enum RadioIssue: Equatable, Sendable {
    /// 400 `playback_provider_not_linked`: show "Connect Spotify".
    case spotifyNotLinked
    /// Spotify stopped reporting a song that should be playing, or did not start one when
    /// asked. A paused player that Spotify no longer reports is not this problem.
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
        case .noActiveDevice: "Juke can’t reach Spotify. Open Spotify, then press play."
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
