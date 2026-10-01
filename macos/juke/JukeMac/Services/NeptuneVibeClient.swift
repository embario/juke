import Foundation

enum NeptuneVibeError: LocalizedError {
    case invalidResponse, cloudAIUnavailable
    var errorDescription: String? {
        switch self {
        case .invalidResponse: "Juke is temporarily unavailable. Your private local history is unchanged."
        case .cloudAIUnavailable: "Cloud chat is disabled for this Juke account."
        }
    }
}

actor NeptuneVibeClient {
    struct EncryptedEnvelope: Codable, Sendable {
        let recordID: UUID
        let accountID: String
        let kind: String
        let ciphertext: Data
        let modifiedAt: Date
        let encryptionVersion: Int
    }

    private struct ChangeSet: Codable { let envelopes: [EncryptedEnvelope]; let cursor: String? }
    private var baseURL: URL { JukeServer.apiURL() }
    private let session: URLSession

    init() {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 20
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        session = URLSession(configuration: configuration)
    }

    func openingQuestion(token: String, currentTrack: String?, signals: [String]) async throws -> String {
        struct Body: Encodable { let recentlyHeardMusic: [String]; let currentTrack: String?; let conversationSignals: [String] }
        struct Response: Decodable { let question: String }
        let body = Body(recentlyHeardMusic: [], currentTrack: currentTrack, conversationSignals: Array(signals.prefix(12)))
        return try await request("vibe/opening-question", token: token, body: body, as: Response.self).question
    }

    func chat(message: String, currentTrack: String?, token: String) async throws -> String {
        struct Body: Encodable { let message: String; let currentTrack: String? }
        struct Response: Decodable { let reply: String }
        let body = Body(message: message, currentTrack: currentTrack)
        return try await request("vibe/chat", token: token, body: body, as: Response.self).reply
    }

    func upload(_ envelope: EncryptedEnvelope, token: String) async throws {
        var request = URLRequest(url: baseURL.appending(path: "vibe/encrypted-chat-records/\(envelope.recordID.uuidString)"))
        request.httpMethod = "PUT"; request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization"); request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try Self.envelopeEncoder().encode(envelope)
        let (_, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, (200..<300).contains(http.statusCode) else { throw NeptuneVibeError.invalidResponse }
    }

    func encryptedChanges(token: String) async throws -> [EncryptedEnvelope] {
        var request = URLRequest(url: baseURL.appending(path: "vibe/encrypted-chat-records")); request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse, http.statusCode == 200 else { throw NeptuneVibeError.invalidResponse }
        return try Self.envelopeDecoder().decode(ChangeSet.self, from: data).envelopes
    }

    private func request<Body: Encodable, T: Decodable>(_ path: String, token: String, body: Body, as: T.Type) async throws -> T {
        var request = URLRequest(url: baseURL.appending(path: path))
        request.httpMethod = "POST"
        request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization")
        request.setValue("application/json", forHTTPHeaderField: "Content-Type")
        request.httpBody = try JSONEncoder().encode(body)
        let (data, response) = try await session.data(for: request)
        guard data.count <= 1_048_576, let http = response as? HTTPURLResponse else { throw NeptuneVibeError.invalidResponse }
        if http.statusCode == 403 { throw NeptuneVibeError.cloudAIUnavailable }
        guard http.statusCode == 200 else { throw NeptuneVibeError.invalidResponse }
        return try JSONDecoder().decode(T.self, from: data)
    }

    nonisolated static func envelopeEncoder() -> JSONEncoder {
        // The Vibe API deliberately uses Swift's reference-date seconds so the
        // encrypted envelope round-trips without server-side timestamp rewriting.
        JSONEncoder()
    }

    nonisolated static func envelopeDecoder() -> JSONDecoder {
        JSONDecoder()
    }
}
