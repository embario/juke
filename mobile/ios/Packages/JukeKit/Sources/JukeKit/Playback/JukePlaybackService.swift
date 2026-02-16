import Foundation

/// A playback artist returned by the backend playback API.
public struct JukePlaybackArtist: Decodable, Sendable {
    public let id: String?
    public let name: String?

    public init(id: String? = nil, name: String? = nil) {
        self.id = id
        self.name = name
    }
}

/// A playback track returned by the backend playback API.
public struct JukePlaybackTrack: Decodable, Sendable {
    public let id: String?
    public let uri: String?
    public let name: String?
    public let durationMs: Int?
    public let artworkURL: String?
    public let artists: [JukePlaybackArtist]?

    enum CodingKeys: String, CodingKey {
        case id, uri, name, artists
        case durationMs
        // convertFromSnakeCase maps artwork_url -> artworkUrl (not artworkURL)
        case artworkURL = "artworkUrl"
    }

    public init(
        id: String? = nil,
        uri: String? = nil,
        name: String? = nil,
        durationMs: Int? = nil,
        artworkURL: String? = nil,
        artists: [JukePlaybackArtist]? = nil
    ) {
        self.id = id
        self.uri = uri
        self.name = name
        self.durationMs = durationMs
        self.artworkURL = artworkURL
        self.artists = artists
    }
}

/// A playback device returned by the backend playback API.
public struct JukePlaybackDevice: Decodable, Sendable {
    public let id: String?
    public let name: String?
    public let type: String?

    public init(id: String? = nil, name: String? = nil, type: String? = nil) {
        self.id = id
        self.name = name
        self.type = type
    }
}

/// Current playback state returned by the backend playback API.
public struct JukePlaybackState: Decodable, Sendable {
    public let provider: String
    public let isPlaying: Bool
    public let progressMs: Int
    public let track: JukePlaybackTrack?
    public let device: JukePlaybackDevice?

    enum CodingKeys: String, CodingKey {
        case provider, track, device
        case isPlaying
        case progressMs
    }

    public init(
        provider: String,
        isPlaying: Bool,
        progressMs: Int,
        track: JukePlaybackTrack? = nil,
        device: JukePlaybackDevice? = nil
    ) {
        self.provider = provider
        self.isPlaying = isPlaying
        self.progressMs = progressMs
        self.track = track
        self.device = device
    }
}

/// Service wrapper for backend playback endpoints.
public final class JukePlaybackService: Sendable {
    private let client: JukeAPIClient

    public init(client: JukeAPIClient = .shared) {
        self.client = client
    }

    /// Fetches playback state. Returns `nil` when no active playback is available.
    public func fetchState(token: String, provider: String? = nil) async throws -> JukePlaybackState? {
        var queryItems: [URLQueryItem] = []
        if let provider {
            queryItems.append(URLQueryItem(name: "provider", value: provider))
        }

        let response: StateWrapper = try await client.send(
            "/api/v1/playback/state/",
            method: .get,
            token: token,
            queryItems: queryItems.isEmpty ? nil : queryItems
        )

        return response.asState
    }

    /// Sends pause command.
    public func pause(token: String, provider: String? = nil, deviceID: String? = nil) async throws -> JukePlaybackState? {
        try await sendControl(
            "/api/v1/playback/pause/",
            token: token,
            payload: ControlPayload(provider: provider, deviceID: deviceID)
        )
    }

    /// Sends resume command.
    public func resume(token: String, provider: String? = nil, deviceID: String? = nil) async throws -> JukePlaybackState? {
        try await sendControl(
            "/api/v1/playback/play/",
            token: token,
            payload: ControlPayload(provider: provider, deviceID: deviceID)
        )
    }

    /// Sends next track command.
    public func next(token: String, provider: String? = nil, deviceID: String? = nil) async throws -> JukePlaybackState? {
        try await sendControl(
            "/api/v1/playback/next/",
            token: token,
            payload: ControlPayload(provider: provider, deviceID: deviceID)
        )
    }

    /// Sends previous track command.
    public func previous(token: String, provider: String? = nil, deviceID: String? = nil) async throws -> JukePlaybackState? {
        try await sendControl(
            "/api/v1/playback/previous/",
            token: token,
            payload: ControlPayload(provider: provider, deviceID: deviceID)
        )
    }

    /// Starts playback, optionally with a specific track URI and position.
    public func play(
        token: String,
        provider: String? = nil,
        deviceID: String? = nil,
        trackURI: String? = nil,
        positionMs: Int? = nil
    ) async throws -> JukePlaybackState? {
        try await sendControl(
            "/api/v1/playback/play/",
            token: token,
            payload: ControlPayload(
                provider: provider,
                deviceID: deviceID,
                trackURI: trackURI,
                positionMs: positionMs
            )
        )
    }

    /// Seeks current playback to the provided position in milliseconds.
    public func seek(
        token: String,
        positionMs: Int,
        provider: String? = nil,
        deviceID: String? = nil
    ) async throws -> JukePlaybackState? {
        try await sendControl(
            "/api/v1/playback/seek/",
            token: token,
            payload: ControlPayload(provider: provider, deviceID: deviceID, positionMs: positionMs)
        )
    }

    private func sendControl(
        _ path: String,
        token: String,
        payload: ControlPayload
    ) async throws -> JukePlaybackState? {
        let response: StateWrapper = try await client.post(path, body: payload, token: token)
        return response.asState
    }
}

private struct StateWrapper: Decodable {
    let provider: String?
    let isPlaying: Bool?
    let progressMs: Int?
    let track: JukePlaybackTrack?
    let device: JukePlaybackDevice?

    enum CodingKeys: String, CodingKey {
        case provider, track, device
        case isPlaying
        case progressMs
    }

    var asState: JukePlaybackState? {
        guard let provider, let isPlaying, let progressMs else {
            return nil
        }
        return JukePlaybackState(
            provider: provider,
            isPlaying: isPlaying,
            progressMs: progressMs,
            track: track,
            device: device
        )
    }
}

private struct ControlPayload: Encodable {
    let provider: String?
    let deviceID: String?
    let trackURI: String?
    let positionMs: Int?

    init(
        provider: String? = nil,
        deviceID: String? = nil,
        trackURI: String? = nil,
        positionMs: Int? = nil
    ) {
        self.provider = provider
        self.deviceID = deviceID
        self.trackURI = trackURI
        self.positionMs = positionMs
    }

    enum CodingKeys: String, CodingKey {
        case provider
        case deviceID = "device_id"
        case trackURI = "track_uri"
        case positionMs = "position_ms"
    }
}
