import Foundation
import Observation

@MainActor @Observable
final class MemoryStore {
    var memories: [MusicMemory] = []
    var reusableTags: [String] = []
    var insights: MemoryInsights = .empty
    var error: String?
    var isLoading = false
    var isSaving = false
    private(set) var token: String?
    private var accountID: String?
    let client: MemoryClient
    private var generation = UUID()
    private var mutationVersion = 0
    private var cachedMedia: [UUID: URL] = [:]
    nonisolated static let mediaCacheDirectory = FileManager.default.temporaryDirectory.appending(path: "VibeMemoryMedia", directoryHint: .isDirectory)

    nonisolated static func removeStaleMedia() {
        try? FileManager.default.removeItem(at: mediaCacheDirectory)
    }

    init(client: MemoryClient = MemoryClient.applicationClient()) { self.client = client }

    func configure(session: JukeSession?) async {
        guard session?.account.id != accountID || session?.accessToken != token else { return }
        reset()
        accountID = session?.account.id; token = session?.accessToken
        if token != nil { await refresh() }
    }

    func reset() {
        generation = UUID(); accountID = nil; token = nil
        memories = []; reusableTags = []; insights = .empty; error = nil
        isLoading = false; isSaving = false
        for url in cachedMedia.values { try? FileManager.default.removeItem(at: url) }
        cachedMedia = [:]
    }

    func refresh() async {
        guard let token else { return }
        let requestGeneration = generation
        let startingVersion = mutationVersion
        isLoading = true; error = nil
        defer { if generation == requestGeneration { isLoading = false } }
        do {
            async let fetchedMemories = client.list(token: token)
            async let fetchedTags = client.tags(token: token)
            async let fetchedInsights = client.insights(token: token)
            let result = try await (fetchedMemories, fetchedTags, fetchedInsights)
            guard generation == requestGeneration, mutationVersion == startingVersion else { return }
            memories = result.0; reusableTags = result.1; insights = result.2
        } catch { if generation == requestGeneration { self.error = error.localizedDescription } }
    }

    func classify(_ draft: MemoryDraft) async throws -> MemoryClassification {
        guard let token else { throw MemoryServiceError(message: "Sign in to prepare your memory.") }
        return try await client.classify(draft, token: token)
    }

    @discardableResult
    func save(_ draft: MemoryDraft) async throws -> MusicMemory {
        guard let token, !isSaving else { throw MemoryServiceError(message: "Sign in before saving a memory.") }
        let requestGeneration = generation
        isSaving = true
        defer { if generation == requestGeneration { isSaving = false } }
        let memory = try await client.create(draft, token: token)
        guard requestGeneration == generation else { throw CancellationError() }
        mutationVersion += 1
        memories.insert(memory, at: 0); memories.sort { $0.occurredAt > $1.occurredAt }
        reusableTags = MemoryDraft.normalizedTags(reusableTags + memory.tags)
        do {
            let updatedInsights = try await client.insights(token: token)
            if requestGeneration == generation { insights = updatedInsights }
        } catch { /* Saved memory remains visible during an insights outage. */ }
        return memory
    }

    func updateTags(_ tags: [String], for memory: MusicMemory) async throws {
        guard let token else { return }
        let requestGeneration = generation
        let updated = try await client.updateTags(memory: memory, tags: MemoryDraft.normalizedTags(tags), token: token)
        guard generation == requestGeneration else { return }
        mutationVersion += 1
        memories = memories.map { $0.id == memory.id ? updated : $0 }
        reusableTags = MemoryDraft.normalizedTags(reusableTags + updated.tags)
    }

    func upload(_ data: Data, filename: String, contentType: String) async throws -> MemoryMedia {
        guard let token else { throw MemoryServiceError(message: "Sign in to attach media.") }
        let requestGeneration = generation
        let media = try await client.upload(data: data, filename: filename, contentType: contentType, token: token)
        guard generation == requestGeneration else {
            await client.discardMedia(media, token: token)
            throw CancellationError()
        }
        return media
    }

    func discardMedia(_ media: [MemoryMedia]) async {
        guard let token else { return }
        for item in media { await client.discardMedia(item, token: token) }
    }

    func localMediaURL(_ media: MemoryMedia) async throws -> URL {
        if let cached = cachedMedia[media.id] { return cached }
        guard let token else { throw MemoryServiceError(message: "Sign in to view this attachment.") }
        let requestGeneration = generation
        let data = try await client.mediaData(media, token: token)
        guard requestGeneration == generation else { throw CancellationError() }
        let directory = Self.mediaCacheDirectory
        try FileManager.default.createDirectory(at: directory, withIntermediateDirectories: true, attributes: [.posixPermissions: 0o700])
        let ext = URL(fileURLWithPath: media.filename).pathExtension
        let url = directory.appending(path: "\(generation.uuidString)-\(media.id.uuidString)").appendingPathExtension(ext)
        try data.write(to: url, options: .atomic)
        try FileManager.default.setAttributes([.posixPermissions: 0o600], ofItemAtPath: url.path)
        cachedMedia[media.id] = url
        return url
    }
}
