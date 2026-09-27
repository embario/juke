import Foundation

struct JukePlaybackState: Decodable, Sendable {
    struct Artist: Decodable, Sendable {
        let id: String?
        let uri: String?
        let name: String?
    }

    struct Album: Decodable, Sendable {
        let id: String?
        let uri: String?
        let name: String?
    }

    struct Track: Decodable, Sendable {
        let id: String?
        let uri: String?
        let name: String?
        let durationMs: Int?
        let artworkURL: URL?
        let album: Album?
        let artists: [Artist]?

        enum CodingKeys: String, CodingKey {
            case id, uri, name, album, artists
            case durationMs = "duration_ms"
            case artworkURL = "artwork_url"
        }
    }

    struct Device: Decodable, Sendable {
        let id: String?
        let name: String?
        let type: String?
    }

    let provider: String
    let isPlaying: Bool
    let progressMs: Int
    let track: Track?
    let device: Device?

    enum CodingKeys: String, CodingKey {
        case provider, track, device
        case isPlaying = "is_playing"
        case progressMs = "progress_ms"
    }
}

enum PlaybackClientError: LocalizedError {
    case authenticationExpired
    case providerNotConnected(String)
    case unavailable(Int)
    case invalidResponse
    case invalidMemorySong
    case invalidSegment

    var errorDescription: String? {
        switch self {
        case .authenticationExpired:
            "Your Juke session has expired. Sign in again to control playback."
        case .providerNotConnected(let detail):
            detail
        case .unavailable(let status):
            "Playback control is temporarily unavailable (HTTP \(status))."
        case .invalidMemorySong:
            "This memory does not contain a valid Spotify or Apple Music song link."
        case .invalidSegment:
            "Choose a segment with a finite, nonnegative start and an end after the start."
        case .invalidResponse:
            "Juke returned an unexpected playback response."
        }
    }
}

actor PlaybackClient {
    private struct ControlBody: Encodable {
        let provider: String
        let deviceID: String?
        let trackURI: String?
        let contextURI: String?
        let positionMs: Int?

        enum CodingKeys: String, CodingKey {
            case provider
            case deviceID = "device_id"
            case trackURI = "track_uri"
            case contextURI = "context_uri"
            case positionMs = "position_ms"
        }
    }

    private struct ErrorBody: Decodable { let detail: String? }

    private let baseURL = URL(string: "https://neptune.tail647b75.ts.net/api/v1/playback/")!
    private let session: URLSession
    private let usesFixtures = ProcessInfo.processInfo.arguments.contains("--uitesting")
    private var fixtureIsPlaying = true
    private var fixtureProgressMs = 96_000

    init() {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        configuration.timeoutIntervalForRequest = 8
        session = URLSession(configuration: configuration)
    }

    func fetchSpotifyState(token: String) async throws -> JukePlaybackState? {
        if usesFixtures { return fixtureState() }
        var components = URLComponents(url: baseURL.appending(path: "state/"), resolvingAgainstBaseURL: false)!
        components.queryItems = [URLQueryItem(name: "provider", value: "spotify")]
        return try await send(url: components.url!, method: "GET", body: nil, token: token)
    }

    func pause(token: String, deviceID: String?) async throws -> JukePlaybackState? {
        if usesFixtures { fixtureIsPlaying = false; return fixtureState() }
        return try await control("pause/", token: token, deviceID: deviceID)
    }

    func resume(token: String, deviceID: String?) async throws -> JukePlaybackState? {
        if usesFixtures { fixtureIsPlaying = true; return fixtureState() }
        return try await control("play/", token: token, deviceID: deviceID)
    }

    func next(token: String, deviceID: String?) async throws -> JukePlaybackState? {
        if usesFixtures { fixtureProgressMs = 0; return fixtureState() }
        return try await control("next/", token: token, deviceID: deviceID)
    }

    func previous(token: String, deviceID: String?) async throws -> JukePlaybackState? {
        if usesFixtures { fixtureProgressMs = 0; return fixtureState() }
        return try await control("previous/", token: token, deviceID: deviceID)
    }

    func seek(token: String, deviceID: String?, position: TimeInterval) async throws -> JukePlaybackState? {
        if usesFixtures { fixtureProgressMs = Int(max(0, position) * 1_000); return fixtureState() }
        return try await control("seek/", token: token, deviceID: deviceID, positionMs: Int(max(0, position) * 1_000))
    }

    func play(
        token: String,
        spotifyID: String,
        kind: String,
        deviceID: String?,
        startSeconds: TimeInterval = 0
    ) async throws -> JukePlaybackState? {
        guard startSeconds.isFinite, (0...604_800).contains(startSeconds) else { throw PlaybackClientError.invalidSegment }
        if usesFixtures { fixtureIsPlaying = true; fixtureProgressMs = Int(startSeconds * 1_000); return fixtureState() }
        let resourceType = kind == "artists" ? "artist" : kind == "albums" ? "album" : "track"
        let uri = "spotify:\(resourceType):\(spotifyID)"
        return try await control(
            "play/",
            token: token,
            deviceID: deviceID,
            trackURI: resourceType == "track" ? uri : nil,
            contextURI: resourceType == "track" ? nil : uri,
            positionMs: Int(startSeconds * 1_000)
        )
    }

    private func control(
        _ path: String,
        token: String,
        deviceID: String?,
        trackURI: String? = nil,
        contextURI: String? = nil,
        positionMs: Int? = nil
    ) async throws -> JukePlaybackState? {
        let body = ControlBody(
            provider: "spotify",
            deviceID: deviceID,
            trackURI: trackURI,
            contextURI: contextURI,
            positionMs: positionMs
        )
        return try await send(
            url: baseURL.appending(path: path),
            method: "POST",
            body: try JSONEncoder().encode(body),
            token: token
        )
    }

    private func send(url: URL, method: String, body: Data?, token: String) async throws -> JukePlaybackState? {
        var request = Self.authorizedRequest(url: url, token: token)
        request.httpMethod = method
        request.httpBody = body
        if body != nil { request.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        let (data, response) = try await session.data(for: request)
        guard data.count <= 1_048_576, let http = response as? HTTPURLResponse else {
            throw PlaybackClientError.invalidResponse
        }
        if http.statusCode == 204 { return nil }
        if http.statusCode == 401 { throw PlaybackClientError.authenticationExpired }
        guard (200..<300).contains(http.statusCode) else {
            if let detail = try? JSONDecoder().decode(ErrorBody.self, from: data).detail, !detail.isEmpty {
                throw PlaybackClientError.providerNotConnected(detail)
            }
            throw PlaybackClientError.unavailable(http.statusCode)
        }
        guard !data.isEmpty else { return nil }
        do { return try JSONDecoder().decode(JukePlaybackState.self, from: data) }
        catch { throw PlaybackClientError.invalidResponse }
    }

    nonisolated static func authorizedRequest(url: URL, token: String) -> URLRequest {
        var request = URLRequest(url: url)
        request.setValue("Token \(token)", forHTTPHeaderField: "Authorization")
        request.timeoutInterval = 8
        return request
    }

    private func fixtureState() -> JukePlaybackState {
        JukePlaybackState(
            provider: "spotify",
            isPlaying: fixtureIsPlaying,
            progressMs: fixtureProgressMs,
            track: .init(
                id: "0aWMVrwxPNYkKmFthzmpRi",
                uri: "spotify:track:0aWMVrwxPNYkKmFthzmpRi",
                name: "Blue in Green",
                durationMs: 327_000,
                artworkURL: nil,
                album: .init(id: nil, uri: nil, name: "Kind of Blue"),
                artists: [.init(id: nil, uri: nil, name: "Miles Davis")]
            ),
            device: .init(id: "ui-test-device", name: "Test Mac", type: "Computer")
        )
    }
}


/// Validated provider references are the only values allowed into URL handoff or scripting.
struct MemoryPlaybackRequest: Sendable {
    enum Provider: Sendable { case spotify, appleMusic }
    let provider: Provider
    let providerID: String?
    let playbackURL: URL?
    let startSeconds: Double
    let endSeconds: Double?

    init(provider: String, providerID: String?, playbackURL: URL?, startSeconds: Double?, endSeconds: Double?) throws {
        switch provider.lowercased().replacingOccurrences(of: " ", with: "_") {
        case "spotify": self.provider = .spotify
        case "apple_music", "applemusic": self.provider = .appleMusic
        default: throw PlaybackClientError.invalidMemorySong
        }
        let start = startSeconds ?? 0
        guard start.isFinite, (0...604_800).contains(start),
              endSeconds.map({ $0.isFinite && $0 > start && $0 <= 604_800 }) ?? true else {
            throw PlaybackClientError.invalidSegment
        }
        self.startSeconds = start
        self.endSeconds = endSeconds
        var identifier = providerID.flatMap { $0.isEmpty ? nil : $0 }
        var safeURL: URL?
        if let playbackURL {
            guard let components = URLComponents(url: playbackURL, resolvingAgainstBaseURL: false),
                  components.user == nil, components.password == nil, components.port == nil else {
                throw PlaybackClientError.invalidMemorySong
            }
            switch self.provider {
            case .spotify:
                let parts: [String]
                if components.scheme == "spotify" {
                    parts = playbackURL.absoluteString.split(separator: ":").map(String.init)
                    guard parts.count == 3, parts[1] == "track" else { throw PlaybackClientError.invalidMemorySong }
                } else {
                    let path = components.path.split(separator: "/").map(String.init)
                    guard components.scheme == "https", components.host == "open.spotify.com",
                          path.count == 2, path[0] == "track" else { throw PlaybackClientError.invalidMemorySong }
                    parts = ["spotify", "track", path[1]]
                }
                guard Self.isSpotifyID(parts[2]), identifier == nil || identifier == parts[2] else {
                    throw PlaybackClientError.invalidMemorySong
                }
                identifier = parts[2]
            case .appleMusic:
                guard components.scheme == "https", components.host == "music.apple.com",
                      !components.path.isEmpty else { throw PlaybackClientError.invalidMemorySong }
                safeURL = playbackURL
            }
        }
        switch self.provider {
        case .spotify:
            guard let identifier, Self.isSpotifyID(identifier) else { throw PlaybackClientError.invalidMemorySong }
            safeURL = URL(string: "spotify:track:\(identifier)")
        case .appleMusic:
            if let identifier {
                guard Self.isAppleLibraryID(identifier) || Self.isAppleCatalogID(identifier) else {
                    throw PlaybackClientError.invalidMemorySong
                }
                if !Self.isAppleLibraryID(identifier), safeURL == nil {
                    safeURL = URL(string: "https://music.apple.com/song/\(identifier)")
                }
            }
            guard identifier != nil || safeURL != nil else { throw PlaybackClientError.invalidMemorySong }
        }
        self.providerID = identifier
        self.playbackURL = safeURL
    }

    static func isSpotifyID(_ value: String) -> Bool {
        value.count == 22 && value.utf8.allSatisfy { (48...57).contains($0) || (65...90).contains($0) || (97...122).contains($0) }
    }

    static func isAppleLibraryID(_ value: String) -> Bool {
        value.count == 16 && value.utf8.allSatisfy { (48...57).contains($0) || (65...70).contains($0) || (97...102).contains($0) }
    }

    static func isAppleCatalogID(_ value: String) -> Bool {
        !value.isEmpty && value.count < 16 && value.utf8.allSatisfy { (48...57).contains($0) }
    }
}

/// A fresh provider snapshot must still match the exact song and playback device.
struct MemorySegmentGuard: Sendable {
    enum Decision: Equatable { case keepWaiting, pause, cancel }
    let trackID: String
    let deviceID: String?
    let endSeconds: Double

    func decision(trackID: String?, deviceID: String?, isPlaying: Bool, position: Double) -> Decision {
        guard trackID == self.trackID, deviceID == self.deviceID, isPlaying, position.isFinite else { return .cancel }
        return position >= endSeconds ? .pause : .keepWaiting
    }
}
