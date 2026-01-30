import Foundation

// MARK: - Models

struct PlaybackTrack: Decodable {
    let id: String?
    let uri: String?
    let name: String?
    let durationMs: Int?
    let artworkUrl: String?
    let artists: [PlaybackArtist]?

    enum CodingKeys: String, CodingKey {
        case id, uri, name, artists
        case durationMs = "duration_ms"
        case artworkUrl = "artwork_url"
    }
}

struct PlaybackArtist: Decodable {
    let id: String?
    let name: String?
}

struct PlaybackDevice: Decodable {
    let id: String?
    let name: String?
    let type: String?
}

struct PlaybackState: Decodable {
    let provider: String
    let isPlaying: Bool
    let progressMs: Int
    let track: PlaybackTrack?
    let device: PlaybackDevice?

    enum CodingKeys: String, CodingKey {
        case provider, track, device
        case isPlaying = "is_playing"
        case progressMs = "progress_ms"
    }
}

// MARK: - Service

final class PlaybackService {
    private let client: APIClient

    init(client: APIClient = .shared) {
        self.client = client
    }

    func fetchState(token: String, provider: String? = nil) async throws -> PlaybackState? {
        var queryItems: [URLQueryItem] = []
        if let provider {
            queryItems.append(URLQueryItem(name: "provider", value: provider))
        }

        // The API may return an empty object when no playback is active
        struct StateWrapper: Decodable {
            let provider: String?
            let isPlaying: Bool?
            let progressMs: Int?
            let track: PlaybackTrack?
            let device: PlaybackDevice?

            enum CodingKeys: String, CodingKey {
                case provider, track, device
                case isPlaying = "is_playing"
                case progressMs = "progress_ms"
            }
        }

        let response: StateWrapper = try await client.send(
            "/api/v1/playback/state/",
            token: token,
            queryItems: queryItems.isEmpty ? nil : queryItems
        )

        guard let provider = response.provider, let isPlaying = response.isPlaying, let progressMs = response.progressMs else {
            return nil
        }

        return PlaybackState(
            provider: provider,
            isPlaying: isPlaying,
            progressMs: progressMs,
            track: response.track,
            device: response.device
        )
    }

    func pause(token: String, provider: String? = nil, deviceId: String? = nil) async throws -> PlaybackState? {
        return try await sendControl("/api/v1/playback/pause/", token: token, provider: provider, deviceId: deviceId)
    }

    func resume(token: String, provider: String? = nil, deviceId: String? = nil) async throws -> PlaybackState? {
        return try await sendControl("/api/v1/playback/play/", token: token, provider: provider, deviceId: deviceId)
    }

    func next(token: String, provider: String? = nil, deviceId: String? = nil) async throws -> PlaybackState? {
        return try await sendControl("/api/v1/playback/next/", token: token, provider: provider, deviceId: deviceId)
    }

    func previous(token: String, provider: String? = nil, deviceId: String? = nil) async throws -> PlaybackState? {
        return try await sendControl("/api/v1/playback/previous/", token: token, provider: provider, deviceId: deviceId)
    }

    private func sendControl(_ path: String, token: String, provider: String?, deviceId: String?) async throws -> PlaybackState? {
        struct ControlPayload: Encodable {
            let provider: String?
            let deviceId: String?

            enum CodingKeys: String, CodingKey {
                case provider
                case deviceId = "device_id"
            }
        }

        let payload = ControlPayload(provider: provider, deviceId: deviceId)
        let body = try JSONEncoder().encode(payload)

        struct StateWrapper: Decodable {
            let provider: String?
            let isPlaying: Bool?
            let progressMs: Int?
            let track: PlaybackTrack?
            let device: PlaybackDevice?

            enum CodingKeys: String, CodingKey {
                case provider, track, device
                case isPlaying = "is_playing"
                case progressMs = "progress_ms"
            }
        }

        let response: StateWrapper = try await client.send(
            path,
            method: .post,
            token: token,
            body: body
        )

        guard let provider = response.provider, let isPlaying = response.isPlaying, let progressMs = response.progressMs else {
            return nil
        }

        return PlaybackState(
            provider: provider,
            isPlaying: isPlaying,
            progressMs: progressMs,
            track: response.track,
            device: response.device
        )
    }
}
