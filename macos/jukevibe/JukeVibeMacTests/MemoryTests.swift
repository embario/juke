import Foundation
import XCTest
@testable import Juke_Vibe

final class MemoryDraftTests: XCTestCase {
    func testRequiresWordsASongOrMediaRatherThanOnlyMetadata() {
        var draft = MemoryDraft()
        draft.title = "Summer"; draft.place = "Brooklyn"; draft.people = ["Alex"]
        draft.tags = ["nostalgia"]; draft.text = " \n "
        XCTAssertFalse(draft.canSave)
        XCTAssertNotNil(draft.validationMessage)
        draft.text = "The song we heard on the walk home."
        XCTAssertTrue(draft.canSave)
        XCTAssertNil(draft.validationMessage)
        draft.text = ""
        draft.mediaIDs = [UUID()]
        XCTAssertNil(draft.validationMessage)
        draft.mediaIDs = []
        draft.songs = [MemorySong(title: "Blue in Green", artist: "Miles Davis", provider: "spotify")]
        XCTAssertNil(draft.validationMessage)
    }

    func testSegmentsRejectNegativeNonfiniteAndReversedBoundaries() {
        var draft = MemoryDraft()
        var song = MemorySong(title: "Blue in Green", artist: "Miles Davis", provider: "spotify")
        for start in [-1.0, 604_801, Double.greatestFiniteMagnitude, Double.infinity, Double.nan] {
            song.startSeconds = start; draft.songs = [song]
            XCTAssertNotNil(draft.validationMessage)
        }
        song.startSeconds = 20
        for end in [19.0, 20.0, 604_801, Double.greatestFiniteMagnitude, Double.infinity, Double.nan] {
            song.endSeconds = end; draft.songs = [song]
            XCTAssertNotNil(draft.validationMessage)
        }
        song.endSeconds = 45; draft.songs = [song]
        XCTAssertNil(draft.validationMessage)
        XCTAssertEqual(song.segmentDescription, "0:20–0:45")
        song.startSeconds = nil; XCTAssertEqual(song.segmentDescription, "0:00–0:45")
        song.title = " \n "; draft.songs = [song]
        XCTAssertNotNil(draft.validationMessage)
    }

    func testTagsTrimDeduplicateAndPreserveUserSpelling() {
        XCTAssertEqual(MemoryDraft.normalizedTags([" Road Trip ", "road trip", "", "\n", "Family"]), ["Road Trip", "Family"])
        XCTAssertEqual(MemoryDraft.normalizedTags([String(repeating: "a", count: 80)]).first?.count, 60)
    }

    func testDraftUsesBackendBodyAndSongSegmentContract() throws {
        var draft = MemoryDraft()
        draft.text = "A rainy evening"; draft.excludedTags = ["melancholy"]
        draft.occurredAt = Date(timeIntervalSince1970: 0)
        var song = MemorySong(title: "Blue in Green", artist: "Miles Davis", provider: "spotify", providerID: "song-1", playbackURL: URL(string: "spotify:track:song-1"))
        song.startSeconds = 12; song.endSeconds = 34; draft.songs = [song]
        let json = try XCTUnwrap(JSONSerialization.jsonObject(with: MemoryClient.encoder().encode(draft)) as? [String: Any])
        XCTAssertEqual(json["body"] as? String, draft.text)
        XCTAssertNil(json["text"])
        XCTAssertEqual(json["occurredAt"] as? String, "1970-01-01T00:00:00Z")
        XCTAssertEqual(json["excludedTags"] as? [String], ["melancholy"])
        let item = try XCTUnwrap((json["songs"] as? [[String: Any]])?.first)
        XCTAssertEqual(item["providerTrackID"] as? String, "song-1")
        XCTAssertEqual(item["deepLink"] as? String, "spotify:track:song-1")
        XCTAssertEqual(item["segmentStartSeconds"] as? Double, 12)
        XCTAssertEqual(item["segmentEndSeconds"] as? Double, 34)
    }

    func testSongDecodesEmptyAndNullOptionalProviderURLsAsAbsent() throws {
        for optionalFields in [#""providerTrackID":"","deepLink":"","artworkURL":"""#, #""providerTrackID":null,"deepLink":null,"artworkURL":null"#] {
            let json = """
            {"id":"33BB84BE-A928-40CF-BB25-E1DC7C9F913B","title":"An unlinked song","artist":"A musician","provider":"appleMusic",\(optionalFields)}
            """
            let song = try MemoryClient.decoder().decode(MemorySong.self, from: Data(json.utf8))
            XCTAssertNil(song.providerID)
            XCTAssertNil(song.playbackURL)
            XCTAssertNil(song.artworkURL)
        }
    }

    func testMemoryDatesAcceptBackendFractionalAndWholeSeconds() throws {
        struct Dates: Decodable { let occurredAt: Date; let createdAt: Date }
        let data = Data(#"{"occurredAt":"2026-09-16T10:20:30Z","createdAt":"2026-09-16T10:20:30.125Z"}"#.utf8)
        let dates = try MemoryClient.decoder().decode(Dates.self, from: data)
        XCTAssertEqual(dates.createdAt.timeIntervalSince(dates.occurredAt), 0.125, accuracy: 0.001)
        XCTAssertThrowsError(try MemoryClient.decoder().decode(Dates.self, from: Data(#"{"occurredAt":"yesterday","createdAt":"2026-09-16T10:20:30Z"}"#.utf8)))
    }
}

final class MemoryClientTests: XCTestCase {
    func testListFollowsOffsetsWithoutDroppingOlderMemories() async throws {
        let first = sampleMemory()
        var second = sampleMemory(); second.title = "Older memory"
        second.occurredAt = first.occurredAt.addingTimeInterval(-3600)
        struct Page: Encodable { let memories: [MusicMemory]; let nextOffset: Int? }
        let firstPage = try MemoryClient.encoder().encode(Page(memories: [first], nextOffset: 1))
        let lastPage = try MemoryClient.encoder().encode(Page(memories: [second], nextOffset: nil))
        let client = makeClient { request in
            XCTAssertEqual(URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.path, "/api/v1/vibe/memories/")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Token test-token")
            let query = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.queryItems
            let offset = query?.first { $0.name == "offset" }?.value
            if offset == "0" { return (200, firstPage) }
            XCTAssertEqual(offset, "1")
            return (200, lastPage)
        }
        let memories = try await client.list(token: "test-token")
        XCTAssertEqual(memories.map(\.id), [first.id, second.id])
        XCTAssertEqual(memories.last?.title, "Older memory")
    }

    func testListStopsWhenServerRepeatsOffset() async throws {
        let client = makeClient { _ in
            (200, Data(#"{"memories":[],"nextOffset":0}"#.utf8))
        }
        let memories = try await client.list(token: "test-token")
        XCTAssertTrue(memories.isEmpty)
    }

    func testClassificationUsesAuthenticatedDraftAndReturnsGeneratedTags() async throws {
        let client = makeClient { request in
            XCTAssertEqual(URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.path, "/api/v1/vibe/memories/classify/")
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Token test-token")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Content-Type"), "application/json")
            let body = try XCTUnwrap(JSONSerialization.jsonObject(with: request.bodyData()) as? [String: Any])
            XCTAssertEqual(body["body"] as? String, "A summer afternoon with Alex")
            return (200, Data(#"{"tags":["summer","friendship"],"classification":{"status":"complete","model":"jev-test"}}"#.utf8))
        }
        var draft = MemoryDraft(); draft.text = "A summer afternoon with Alex"
        let result = try await client.classify(draft, token: "test-token")
        XCTAssertEqual(result.tags, ["summer", "friendship"])
        XCTAssertEqual(result.status, "complete")
        XCTAssertEqual(result.model, "jev-test")
    }

    func testCreatePersistsAnAuthenticatedMultimediaMemoryContract() async throws {
        var memory = sampleMemory()
        let mediaID = UUID()
        memory.songs = [MemorySong(title: "Blue in Green", artist: "Miles Davis", provider: "spotify", providerID: "song-1")]
        memory.media = [MemoryMedia(id: mediaID, kind: "photo", filename: "sea.jpg", contentType: "image/jpeg", url: "/api/v1/vibe/memory-media/photo/")]
        let response = try MemoryClient.encoder().encode(memory)
        let client = makeClient { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.path, "/api/v1/vibe/memories/")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Token test-token")
            let body = try XCTUnwrap(JSONSerialization.jsonObject(with: request.bodyData()) as? [String: Any])
            XCTAssertEqual(body["mediaIDs"] as? [String], [mediaID.uuidString])
            XCTAssertEqual(body["people"] as? [String], ["Alex"])
            XCTAssertEqual(body["place"] as? String, "Brooklyn")
            XCTAssertEqual((body["songs"] as? [[String: Any]])?.count, 1)
            return (201, response)
        }
        var draft = MemoryDraft()
        draft.text = memory.text; draft.place = memory.place; draft.people = memory.people
        draft.mediaIDs = [mediaID]; draft.songs = memory.songs
        let saved = try await client.create(draft, token: "test-token")
        XCTAssertEqual(saved.id, memory.id)
        XCTAssertEqual(saved.media.first?.id, mediaID)
        XCTAssertEqual(saved.songs.first?.providerID, "song-1")
    }

    func testRemovingGeneratedTagSendsExclusionWhileRetainingUserTag() async throws {
        var memory = sampleMemory(); memory.generatedTags = ["Nostalgia", "summer"]
        let response = try MemoryClient.encoder().encode(memory)
        let memoryID = memory.id.uuidString.lowercased()
        let client = makeClient { request in
            XCTAssertEqual(request.httpMethod, "PATCH")
            XCTAssertEqual(URLComponents(url: request.url!, resolvingAgainstBaseURL: false)?.path, "/api/v1/vibe/memories/\(memoryID)/")
            let body = try XCTUnwrap(JSONSerialization.jsonObject(with: request.bodyData()) as? [String: Any])
            XCTAssertEqual(body["tags"] as? [String], ["nostalgia", "our song"])
            XCTAssertEqual(body["excludedTags"] as? [String], ["summer"])
            return (200, response)
        }
        _ = try await client.updateTags(memory: memory, tags: ["nostalgia", "our song"], token: "test-token")
    }

    func testExpiredSessionSurfacesActionableError() async throws {
        let client = makeClient { _ in (401, Data(#"{"detail":"Invalid token"}"#.utf8)) }
        do {
            _ = try await client.list(token: "expired-test-token")
            XCTFail("Expired authentication should fail")
        } catch {
            XCTAssertTrue(error.localizedDescription.contains("Sign in again"))
        }
    }

    func testPrivateMediaRejectsForeignOriginWrongPortAndNonMediaPaths() async throws {
        let client = makeClient { _ in
            XCTFail("Invalid media addresses must not receive authentication")
            return (200, Data())
        }
        let base = await client.baseURL
        let host = try XCTUnwrap(base.host)
        for address in ["https://foreign.example/api/v1/vibe/memory-media/photo/", "http://\(host)/api/v1/vibe/memory-media/photo/", "https://\(host):8443/api/v1/vibe/memory-media/photo/", "https://\(host)/api/v1/auth/accounts/", "https://\(host)/api/v1/vibe/memory-media/../../auth/"] {
            let media = MemoryMedia(id: UUID(), kind: "photo", filename: "photo.jpg", contentType: "image/jpeg", url: address)
            do {
                _ = try await client.mediaData(media, token: "test-token")
                XCTFail("Address should be rejected: \(address)")
            } catch {
                XCTAssertTrue(error.localizedDescription.contains("invalid address"))
            }
        }
    }

    func testPrivateMediaAuthenticatesSameOriginAttachment() async throws {
        let bytes = Data([0xff, 0xd8, 0xff])
        let client = makeClient { request in
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Token test-token")
            XCTAssertTrue(request.url!.path.hasSuffix("/memory-media/photo"))
            return (200, bytes)
        }
        let base = await client.baseURL
        let media = MemoryMedia(id: UUID(), kind: "photo", filename: "photo.jpg", contentType: "image/jpeg", url: base.appending(path: "memory-media/photo/").absoluteString)
        let result = try await client.mediaData(media, token: "test-token")
        XCTAssertEqual(result, bytes)
    }

    func testInvalidDraftNeverReachesBackend() async {
        let client = makeClient { _ in XCTFail("Invalid drafts must not be sent"); return (500, Data()) }
        do {
            _ = try await client.create(MemoryDraft(), token: "test-token")
            XCTFail("An empty draft should fail")
        } catch {
            XCTAssertTrue(error.localizedDescription.contains("Add a song"))
        }
    }
}

@MainActor
final class MemoryStoreTests: XCTestCase {
    func testSaveSortsTimelineAndKeepsTagsAvailableForAnotherMemory() async throws {
        let store = MemoryStore(client: MemoryClient(fixtures: true))
        await store.configure(session: testSession())
        var newer = MemoryDraft(); newer.text = "Today"; newer.tags = ["Road trip"]
        var older = MemoryDraft(); older.text = "Last year"; older.tags = ["Family"]
        older.occurredAt = newer.occurredAt.addingTimeInterval(-31_536_000)
        try await store.save(newer)
        try await store.save(older)
        XCTAssertEqual(store.memories.map(\.text), ["Today", "Last year"])
        let memory = try XCTUnwrap(store.memories.first)
        try await store.updateTags(["Summer"], for: memory)
        XCTAssertEqual(store.memories.first?.tags, ["Summer"])
        XCTAssertEqual(store.reusableTags, ["Road trip", "Family", "Summer"])
    }

    func testSignOutClearsAccountDataAndPreventsSaving() async throws {
        let store = MemoryStore(client: MemoryClient(fixtures: true))
        await store.configure(session: testSession())
        var draft = MemoryDraft(); draft.text = "Private memory"; draft.tags = ["Family"]
        try await store.save(draft)
        XCTAssertEqual(store.memories.count, 1)
        await store.configure(session: nil)
        XCTAssertTrue(store.memories.isEmpty)
        XCTAssertTrue(store.reusableTags.isEmpty)
        XCTAssertTrue(store.insights.connections.isEmpty)
        XCTAssertNil(store.token)
        XCTAssertNil(store.error)
        do {
            try await store.save(draft)
            XCTFail("Signed out users cannot save")
        } catch {
            XCTAssertTrue(error.localizedDescription.contains("Sign in"))
        }
    }

    func testChangingAccountsClearsExistingTimelineAndTags() async throws {
        let client = makeClient { request in
            if URLComponents(url: request.url!, resolvingAgainstBaseURL: false)!.path.hasSuffix("memory-tags/") { return (200, Data(#"{"tags":[]}"#.utf8)) }
            if URLComponents(url: request.url!, resolvingAgainstBaseURL: false)!.path.hasSuffix("memory-insights/") { return (200, Data(#"{"prompt":"A fresh start","connections":[]}"#.utf8)) }
            return (200, Data(#"{"memories":[]}"#.utf8))
        }
        let store = MemoryStore(client: client)
        await store.configure(session: testSession())
        store.memories = [sampleMemory()]; store.reusableTags = ["Private family tag"]
        await store.configure(session: testSession(id: "other-account", token: "other-test-token"))
        XCTAssertTrue(store.memories.isEmpty)
        XCTAssertTrue(store.reusableTags.isEmpty)
        XCTAssertEqual(store.token, "other-test-token")
        XCTAssertNil(store.error)
        XCTAssertEqual(store.insights.question, "A fresh start")
    }

    func testSignOutDeletesCachedPrivateAttachment() async throws {
        let client = makeClient { request in
            if request.url!.path.contains("memory-media/") { return (200, Data("private-photo".utf8)) }
            if URLComponents(url: request.url!, resolvingAgainstBaseURL: false)!.path.hasSuffix("memory-tags/") { return (200, Data(#"{"tags":[]}"#.utf8)) }
            if URLComponents(url: request.url!, resolvingAgainstBaseURL: false)!.path.hasSuffix("memory-insights/") { return (200, Data(#"{"prompt":"A fresh start","connections":[]}"#.utf8)) }
            return (200, Data(#"{"memories":[]}"#.utf8))
        }
        let store = MemoryStore(client: client)
        await store.configure(session: testSession())
        let base = await client.baseURL
        let media = MemoryMedia(id: UUID(), kind: "photo", filename: "photo.jpg", contentType: "image/jpeg", url: base.appending(path: "memory-media/photo/").absoluteString)
        let file = try await store.localMediaURL(media)
        XCTAssertTrue(FileManager.default.fileExists(atPath: file.path))
        XCTAssertEqual(try Data(contentsOf: file), Data("private-photo".utf8))
        await store.configure(session: nil)
        XCTAssertFalse(FileManager.default.fileExists(atPath: file.path))
    }
}

private func testSession(id: String = "memory-test-account", token: String = "test-token") -> JukeSession {
    JukeSession(account: JukeAccount(id: id, displayName: "Test Listener", email: nil, cloudAIEnabled: false), accessToken: token, authenticatedAt: Date())
}

private func sampleMemory() -> MusicMemory {
    MusicMemory(id: UUID(), title: "Summer", text: "A day by the sea", occurredAt: Date(), createdAt: Date(), place: "Brooklyn", people: ["Alex"], songs: [], media: [], tags: ["nostalgia"], classification: .unavailable)
}

private func makeClient(handler: @escaping @Sendable (URLRequest) throws -> (Int, Data)) -> MemoryClient {
    let host = "\(UUID().uuidString.lowercased()).memory-tests.example"
    MemoryURLProtocol.handlers.set(handler, host: host)
    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [MemoryURLProtocol.self]
    return MemoryClient(baseURL: URL(string: "https://\(host)/api/v1/vibe/")!, session: URLSession(configuration: config))
}

private final class MemoryRequestHandlers: @unchecked Sendable {
    typealias Handler = @Sendable (URLRequest) throws -> (Int, Data)
    private let lock = NSLock()
    private var values: [String: Handler] = [:]
    func set(_ handler: @escaping Handler, host: String) { lock.lock(); defer { lock.unlock() }; values[host] = handler }
    func get(host: String) -> Handler? { lock.lock(); defer { lock.unlock() }; return values[host] }
}

private final class MemoryURLProtocol: URLProtocol, @unchecked Sendable {
    static let handlers = MemoryRequestHandlers()
    override class func canInit(with request: URLRequest) -> Bool { request.url?.host?.hasSuffix("memory-tests.example") == true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        do {
            let url = try XCTUnwrap(request.url)
            let handler = try XCTUnwrap(Self.handlers.get(host: url.host!))
            let (status, data) = try handler(request)
            let response = try XCTUnwrap(HTTPURLResponse(url: url, statusCode: status, httpVersion: nil, headerFields: nil))
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch { client?.urlProtocol(self, didFailWithError: error) }
    }
    override func stopLoading() {}
}

private extension URLRequest {
    func bodyData() throws -> Data {
        if let httpBody { return httpBody }
        guard let stream = httpBodyStream else { return Data() }
        stream.open(); defer { stream.close() }
        var result = Data(); var bytes = [UInt8](repeating: 0, count: 4096)
        while stream.hasBytesAvailable {
            let count = stream.read(&bytes, maxLength: bytes.count)
            if count < 0 { throw stream.streamError ?? URLError(.cannotDecodeRawData) }
            if count == 0 { break }
            result.append(contentsOf: bytes.prefix(count))
        }
        return result
    }
}
