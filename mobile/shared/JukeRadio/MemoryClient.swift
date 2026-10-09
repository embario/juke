import Foundation

struct MemoryServiceError: LocalizedError {
    let message: String
    var errorDescription: String? { message }
}

actor MemoryClient {
    /// The configured backend's Vibe memories root (`<api>/vibe/`).
    static var defaultBaseURL: URL { JukeServer.apiURL().appending(path: "vibe/") }
    /// A fixed root for tests and the live check; `nil` follows Settings.
    private let fixedBaseURL: URL?
    nonisolated var baseURL: URL { fixedBaseURL ?? Self.defaultBaseURL }
    private let session: URLSession
    private let fixtures: Bool
    private var fixtureMemories: [MusicMemory] = []
    private var fixtureTags: [String] = []
    private var fixtureMedia: [UUID: (MemoryMedia, Data)] = [:]
    /// UI-check sample memories (`--uitesting-memories-sample`), loaded on the first list.
    private var fixtureSamples: (@Sendable () async -> (memories: [MusicMemory], media: [(MemoryMedia, Data)]))?

    init(baseURL: URL? = nil, session: URLSession? = nil, fixtures: Bool = false,
         fixtureSamples: (@Sendable () async -> (memories: [MusicMemory], media: [(MemoryMedia, Data)]))? = nil) {
        fixedBaseURL = baseURL; self.fixtures = fixtures; self.fixtureSamples = fixtureSamples
        let config = URLSessionConfiguration.ephemeral
        config.timeoutIntervalForRequest = 45
        config.requestCachePolicy = .reloadIgnoringLocalCacheData
        self.session = session ?? URLSession(configuration: config)
    }

    nonisolated static func applicationClient() -> MemoryClient {
        #if DEBUG
        let env = ProcessInfo.processInfo.environment
        if ProcessInfo.processInfo.arguments.contains("--uitesting"),
           let value = env["VIBE_MEMORY_E2E_BASE_URL"], let url = URL(string: value),
           url.host == "127.0.0.1", env["VIBE_MEMORY_E2E_TOKEN"] != nil {
            return MemoryClient(baseURL: url)
        }
        return MemoryClient(fixtures: ProcessInfo.processInfo.arguments.contains("--uitesting"))
        #else
        return MemoryClient()
        #endif
    }

    func discardMedia(_ media: MemoryMedia, token: String) async {
        if fixtures {
            if !fixtureMemories.contains(where: { $0.media.contains(where: { $0.id == media.id }) }) { fixtureMedia[media.id] = nil }
            return
        }
        var request = URLRequest(url: baseURL.appending(path: "memory-media/\(media.id.uuidString.lowercased())/content/"))
        request.httpMethod = "DELETE"
        request.setValue("Token \(token)", forHTTPHeaderField: "Authorization")
        _ = try? await session.data(for: request)
    }

    func list(token: String) async throws -> [MusicMemory] {
        if fixtures {
            if let samples = fixtureSamples {
                fixtureSamples = nil
                let loaded = await samples()
                fixtureMemories += loaded.memories
                for (media, data) in loaded.media { fixtureMedia[media.id] = (media, data) }
            }
            return fixtureMemories.sorted { $0.occurredAt > $1.occurredAt }
        }
        struct Response: Decodable { let memories: [MusicMemory]; let nextOffset: Int? }
        var memories: [MusicMemory] = []
        var offset = 0
        while true {
            let response = try await send("memories/?offset=\(offset)", token: token, as: Response.self)
            memories.append(contentsOf: response.memories)
            guard let next = response.nextOffset, next > offset else { break }
            offset = next
        }
        return memories
    }

    func tags(token: String) async throws -> [String] {
        if fixtures { return fixtureTags }
        struct Response: Decodable { let tags: [String] }
        return try await send("memory-tags/", token: token, as: Response.self).tags
    }

    func insights(token: String) async throws -> MemoryInsights {
        if fixtures { return .empty }
        return try await send("memory-insights/", token: token, as: MemoryInsights.self)
    }

    func classify(_ draft: MemoryDraft, token: String) async throws -> MemoryClassification {
        if fixtures { return .unavailable }
        struct Response: Decodable { let tags: [String]; var classification: MemoryClassification }
        var result = try await send("memories/classify/", method: "POST", data: Self.encoder().encode(draft), token: token, as: Response.self)
        result.classification.tags = result.tags
        return result.classification
    }

    func create(_ draft: MemoryDraft, token: String) async throws -> MusicMemory {
        if let message = draft.validationMessage { throw MemoryServiceError(message: message) }
        if fixtures {
            let memory = MusicMemory(id: UUID(), title: draft.title, text: draft.text, occurredAt: draft.occurredAt, createdAt: .now, place: draft.place, people: draft.people, songs: draft.songs, media: draft.mediaIDs.compactMap { fixtureMedia[$0]?.0 }, tags: draft.tags, classification: .unavailable)
            fixtureMemories.insert(memory, at: 0)
            fixtureTags = MemoryDraft.normalizedTags(fixtureTags + draft.tags)
            return memory
        }
        return try await send("memories/", method: "POST", data: Self.encoder().encode(draft), token: token, as: MusicMemory.self)
    }

    func updateTags(memory: MusicMemory, tags: [String], token: String) async throws -> MusicMemory {
        let excluded = memory.generatedTags.filter { generated in !tags.contains { $0.caseInsensitiveCompare(generated) == .orderedSame } }
        if fixtures {
            var updated = memory; updated.tags = tags
            fixtureMemories = fixtureMemories.map { $0.id == memory.id ? updated : $0 }
            fixtureTags = MemoryDraft.normalizedTags(fixtureTags + tags)
            return updated
        }
        struct Body: Encodable { let tags: [String]; let excludedTags: [String] }
        return try await send("memories/\(memory.id.uuidString.lowercased())/", method: "PATCH", data: Self.encoder().encode(Body(tags: tags, excludedTags: excluded)), token: token, as: MusicMemory.self)
    }

    func delete(_ memory: MusicMemory, token: String) async throws {
        if fixtures {
            fixtureMemories.removeAll { $0.id == memory.id }
            return
        }
        var request = URLRequest(url: baseURL.appending(path: "memories/\(memory.id.uuidString.lowercased())/"))
        request.httpMethod = "DELETE"
        request.setValue("Token \(token)", forHTTPHeaderField: "Authorization")
        let (data, response) = try await session.data(for: request)
        try Self.validate(response, data: data)
    }

    func upload(data: Data, filename: String, contentType: String, token: String) async throws -> MemoryMedia {
        guard data.count <= 50 * 1_024 * 1_024 else { throw MemoryServiceError(message: "Choose a photo or video smaller than 50 MB.") }
        if fixtures {
            let id = UUID()
            let media = MemoryMedia(id: id, kind: contentType.hasPrefix("video/") ? "video" : "photo", filename: filename, contentType: contentType, url: "memory-media/\(id.uuidString.lowercased())/content/")
            fixtureMedia[id] = (media, data)
            return media
        }
        let boundary = "Vibe-\(UUID().uuidString)"
        let safeName = filename.replacingOccurrences(of: "\"", with: "").replacingOccurrences(of: "\r", with: "").replacingOccurrences(of: "\n", with: "")
        var body = Data("--\(boundary)\r\nContent-Disposition: form-data; name=\"file\"; filename=\"\(safeName)\"\r\nContent-Type: \(contentType)\r\n\r\n".utf8)
        body.append(data); body.append(Data("\r\n--\(boundary)--\r\n".utf8))
        return try await send("memory-media/", method: "POST", data: body, contentType: "multipart/form-data; boundary=\(boundary)", token: token, as: MemoryMedia.self)
    }

    func mediaData(_ media: MemoryMedia, token: String) async throws -> Data {
        if fixtures {
            guard let data = fixtureMedia[media.id]?.1 else { throw MemoryServiceError(message: "Test attachment unavailable.") }
            return data
        }
        guard let url = URL(string: media.url, relativeTo: baseURL)?.absoluteURL,
              url.scheme == baseURL.scheme, url.host == baseURL.host, url.port == baseURL.port,
              url.standardized.path.hasPrefix("/" + baseURL.path.trimmingCharacters(in: CharacterSet(charactersIn: "/")) + "/memory-media/") else {
            throw MemoryServiceError(message: "This attachment has an invalid address.")
        }
        var request = URLRequest(url: url)
        request.setValue("Token \(token)", forHTTPHeaderField: "Authorization")
        let (data, response) = try await session.data(for: request)
        try Self.validate(response, data: data)
        guard data.count <= 50 * 1_024 * 1_024 else { throw MemoryServiceError(message: "This attachment is too large to display.") }
        return data
    }

    private func send<T: Decodable>(_ path: String, method: String = "GET", data: Data? = nil, contentType: String = "application/json", token: String, as: T.Type) async throws -> T {
        var request = URLRequest(url: URL(string: path, relativeTo: baseURL)!.absoluteURL)
        request.httpMethod = method; request.httpBody = data
        request.setValue("Token \(token)", forHTTPHeaderField: "Authorization")
        if data != nil { request.setValue(contentType, forHTTPHeaderField: "Content-Type") }
        let (data, response) = try await session.data(for: request)
        try Self.validate(response, data: data)
        return try Self.decoder().decode(T.self, from: data)
    }

    private static func validate(_ response: URLResponse, data: Data) throws {
        guard let http = response as? HTTPURLResponse else { throw MemoryServiceError(message: "Juke returned an unexpected response.") }
        if http.statusCode == 401 { throw MemoryServiceError(message: "Your Juke session has expired. Sign in again to open your memories.") }
        guard (200..<300).contains(http.statusCode) else {
            let json = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            let detail = json?["detail"] as? String
            throw MemoryServiceError(message: detail ?? "Your memory couldn’t be synced (HTTP \(http.statusCode)). Your draft is still here. Try again.")
        }
    }

    nonisolated static func encoder() -> JSONEncoder {
        let encoder = JSONEncoder(); encoder.dateEncodingStrategy = .iso8601; return encoder
    }

    nonisolated static func decoder() -> JSONDecoder {
        let decoder = JSONDecoder()
        decoder.dateDecodingStrategy = .custom { decoder in
            let value = try decoder.singleValueContainer().decode(String.self)
            let format = ISO8601DateFormatter(); format.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
            if let date = format.date(from: value) { return date }
            format.formatOptions = [.withInternetDateTime]
            guard let date = format.date(from: value) else { throw DecodingError.dataCorrupted(.init(codingPath: decoder.codingPath, debugDescription: "Invalid memory date")) }
            return date
        }
        return decoder
    }
}
