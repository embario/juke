import Foundation

actor VibeAPI {
    struct EncryptedEnvelope: Codable, Sendable {
        let recordID: UUID
        let accountID: String
        let kind: String
        let ciphertext: Data
        let modifiedAt: Date
        let encryptionVersion: Int
    }
    private struct ChangeSet: Decodable { let envelopes: [EncryptedEnvelope]; let cursor: String? }
    private var baseURL: URL { AppConfiguration.currentAPIBaseURL }
    /// Injectable so tests can intercept requests deterministically.
    private let session: URLSession

    init(session: URLSession = .shared) { self.session = session }

    func chat(_ message: String, currentTrack: String?, token: String) async throws -> String {
        struct Body: Encodable { let message: String; let currentTrack: String? }
        struct Reply: Decodable { let reply: String }
        return try await post("vibe/chat", body: Body(message: message, currentTrack: currentTrack), token: token, response: Reply.self).reply
    }

    func spotifyPlayback(token: String) async throws -> NowPlayingTrack? {
        struct Artist: Decodable { let name: String? }
        struct Track: Decodable { let id: String?; let name: String?; let artwork_url: URL?; let artists: [Artist]?; let album: Album? }
        struct Album: Decodable { let name: String? }
        struct State: Decodable { let is_playing: Bool; let track: Track? }
        var components = URLComponents(url: baseURL.appending(path: "playback/state/"), resolvingAgainstBaseURL: false)!
        components.queryItems = [.init(name: "provider", value: "spotify")]
        var request = URLRequest(url: components.url!)
        // /playback/state/ uses DRF TokenAuthentication, which only reads "Token" (the Vibe endpoints accept both).
        request.setValue("Token \(token)", forHTTPHeaderField: "Authorization")
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { return nil }
        if http.statusCode == 204 { return nil }
        guard http.statusCode == 200 else { throw CocoaError(.fileReadUnknown) }
        let state = try JSONDecoder().decode(State.self, from: data)
        guard state.is_playing, let track = state.track, let title = track.name else { return nil }
        return NowPlayingTrack(id: track.id ?? title, title: title, artist: track.artists?.compactMap(\.name).joined(separator: ", ") ?? "Unknown artist", album: track.album?.name, artworkURL: track.artwork_url, localArtwork: nil, source: "Spotify")
    }

    func search(_ query: String, kind: String, token: String) async throws -> [CatalogItem] {
        struct Page: Decodable { let results: [CatalogItem] }
        var components = URLComponents(url: baseURL.appending(path: "\(kind)/"), resolvingAgainstBaseURL: false)!
        components.queryItems = [.init(name: "external", value: "true"), .init(name: "q", value: query)]
        var request = URLRequest(url: components.url!); request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else { throw CocoaError(.fileReadUnknown) }
        if let page = try? JSONDecoder().decode(Page.self, from: data) { return page.results }
        return try JSONDecoder().decode([CatalogItem].self, from: data)
    }

    func upload(_ envelope: EncryptedEnvelope, token: String) async throws {
        var request = URLRequest(url: baseURL.appending(path: "vibe/encrypted-chat-records/\(envelope.recordID.uuidString)")); request.httpMethod = "PUT"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization"); request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(envelope)
        let (_, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else { throw CocoaError(.fileWriteUnknown) }
    }

    func encryptedChanges(token: String) async throws -> [EncryptedEnvelope] {
        var request = URLRequest(url: baseURL.appending(path: "vibe/encrypted-chat-records")); request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else { throw CocoaError(.fileReadUnknown) }
        return try JSONDecoder().decode(ChangeSet.self, from: data).envelopes
    }

    private func post<Body: Encodable, Reply: Decodable>(_ path: String, body: Body, token: String, response: Reply.Type) async throws -> Reply {
        var request = URLRequest(url: baseURL.appending(path: path)); request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization"); request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(body)
        let (data, value) = try await session.data(for: request)
        guard let http = value as? HTTPURLResponse, http.statusCode == 200 else { throw CocoaError(.fileReadUnknown) }
        return try JSONDecoder().decode(Reply.self, from: data)
    }
}
