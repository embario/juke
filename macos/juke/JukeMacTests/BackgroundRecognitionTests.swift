import XCTest
@testable import Juke

final class RecognitionEventPolicyTests: XCTestCase {
    func testSameTrackIsPostedOncePerRepeatWindow() {
        var policy = RecognitionEventPolicy(repeatWindow: 600)
        let start = Date(timeIntervalSince1970: 1_000)
        XCTAssertTrue(policy.shouldPost(spotifyID: "a", at: start))
        policy.record(spotifyID: "a", at: start)
        XCTAssertFalse(policy.shouldPost(spotifyID: "a", at: start.addingTimeInterval(599)))
        XCTAssertTrue(policy.shouldPost(spotifyID: "b", at: start.addingTimeInterval(1)))
        XCTAssertTrue(policy.shouldPost(spotifyID: "a", at: start.addingTimeInterval(600)))
    }

    func testHourlyCapThrottlesAndRecovers() {
        var policy = RecognitionEventPolicy(repeatWindow: 60, maxPerHour: 3)
        let start = Date(timeIntervalSince1970: 0)
        for index in 0..<3 { policy.record(spotifyID: "t\(index)", at: start.addingTimeInterval(Double(index))) }
        XCTAssertFalse(policy.shouldPost(spotifyID: "new", at: start.addingTimeInterval(10)))
        XCTAssertTrue(policy.shouldPost(spotifyID: "new", at: start.addingTimeInterval(3_601)))
    }
}

final class SpotifyTrackMatcherTests: XCTestCase {
    func testSpotifyMetadataCarriesItsOwnID() {
        XCTAssertEqual(SpotifyTrackMatcher.spotifyID(for: track(namespace: "spotify", id: "sp1")), "sp1")
        XCTAssertNil(SpotifyTrackMatcher.spotifyID(for: track(namespace: "apple_music", id: "AM1")))
    }

    func testCatalogMatchNeedsTitleAndArtist() {
        let wanted = track(title: "Blue in Green (Remastered 1997)", artist: "Miles Davis & Bill Evans")
        let results = [
            result(1, "Blue in Green", artists: "Tony Bennett", id: "wrong-artist"),
            result(2, "Blue in Greenery", artists: "Miles Davis", id: "wrong-title"),
            result(3, "Blue In Green - Live", artists: "Miles Davis", id: "right"),
        ]
        XCTAssertEqual(SpotifyTrackMatcher.bestMatch(for: wanted, in: results), "right")
        XCTAssertNil(SpotifyTrackMatcher.bestMatch(for: wanted, in: Array(results.prefix(2))))
        XCTAssertEqual(SpotifyTrackMatcher.normalizedTitle("Café  del Mar [Edit]"), "cafe del mar")
    }

    func testSourceFollowsShazam() {
        XCTAssertEqual(RecognitionSource(track: track()), .metadata)
        XCTAssertEqual(RecognitionSource(track: track(shazamID: "123")), .shazam)
    }
}

@MainActor
final class BackgroundRecognizerTests: XCTestCase {
    private final class Box {
        var events: [Radio.EventRequest] = []
        var searches = 0
        var enabled = true
        var radio = false
        var resolved: String? = "resolved-id"
        var now = Date(timeIntervalSince1970: 0)
    }

    private func makeRecognizer(_ box: Box) -> BackgroundRecognizer {
        let recognizer = BackgroundRecognizer(
            isEnabled: { box.enabled },
            resolveCatalog: { _ in box.searches += 1; return box.resolved },
            post: { box.events.append($0) },
            now: { box.now },
            sleep: { _ in }
        )
        recognizer.isRadioPlaying = { box.radio }
        return recognizer
    }

    func testSpotifyMetadataPostsOneRecognizedEventAfterDwell() async {
        let box = Box()
        let recognizer = makeRecognizer(box)
        let song = track(namespace: "spotify", id: "sp1")
        recognizer.observe(song, isAudible: true)
        recognizer.observe(song, isAudible: true) // same song: no second candidate
        await recognizer.pending?.value
        XCTAssertEqual(box.events, [Radio.EventRequest(stationId: nil, spotifyTrackId: "sp1", event: .recognized, positionMs: nil, source: "metadata")])
        XCTAssertEqual(box.searches, 0)

        // Paused and resumed within the repeat window: still one event.
        recognizer.observe(song, isAudible: false)
        recognizer.observe(song, isAudible: true)
        await recognizer.pending?.value
        XCTAssertEqual(box.events.count, 1)
    }

    func testShazamMatchesResolveThroughTheCatalogOnce() async {
        let box = Box()
        let recognizer = makeRecognizer(box)
        let heard = track(title: "Pink Moon", artist: "Nick Drake", shazamID: "99")
        let r1 = await recognizer.commit(heard)
        XCTAssertTrue(r1)
        box.now = box.now.addingTimeInterval(3_600)
        let r2 = await recognizer.commit(heard)
        XCTAssertTrue(r2)
        XCTAssertEqual(box.searches, 1, "resolutions are cached")
        XCTAssertEqual(box.events.map(\.source), ["shazam", "shazam"])
        XCTAssertEqual(box.events.first?.spotifyTrackId, "resolved-id")
    }

    func testUnresolvableSongsAreSkipped() async {
        let box = Box()
        box.resolved = nil
        let recognizer = makeRecognizer(box)
        let r3 = await recognizer.commit(track(namespace: "apple_music", id: "AM1"))
        XCTAssertFalse(r3)
        XCTAssertTrue(box.events.isEmpty)
    }

    func testNothingIsPostedWhenDisabledOrWhileRadioPlays() async {
        let box = Box()
        let recognizer = makeRecognizer(box)
        let song = track(namespace: "spotify", id: "sp1")
        box.enabled = false
        recognizer.observe(song, isAudible: true)
        XCTAssertNil(recognizer.pending)
        let r4 = await recognizer.commit(song)
        XCTAssertFalse(r4)
        box.enabled = true
        box.radio = true
        let r5 = await recognizer.commit(song)
        XCTAssertFalse(r5)
        XCTAssertTrue(box.events.isEmpty)
    }

    func testChangingSongBeforeDwellCancelsTheFirst() async {
        let box = Box()
        let recognizer = BackgroundRecognizer(
            isEnabled: { true }, resolveCatalog: { _ in nil },
            post: { box.events.append($0) },
            sleep: { _ in try await Task.sleep(for: .milliseconds(50)) }
        )
        recognizer.observe(track(namespace: "spotify", id: "first"), isAudible: true)
        let first = recognizer.pending
        recognizer.observe(track(namespace: "spotify", id: "second"), isAudible: true)
        await first?.value
        await recognizer.pending?.value
        XCTAssertEqual(box.events.map(\.spotifyTrackId), ["second"])
    }

    func testShazamNeedsASecondFreshMatchWithinTheDwell() async {
        let box = Box()
        let gate = Gate()
        let recognizer = BackgroundRecognizer(
            isEnabled: { true }, resolveCatalog: { _ in "pink-moon" },
            post: { box.events.append($0) }, now: { box.now }, sleep: { _ in try await gate.wait() }
        )
        // One stale match (the song stopped long ago, the track never cleared): nothing.
        recognizer.observe(shazam(offset: 10), isAudible: true)
        await gate.openAll()
        await recognizer.pending?.value
        XCTAssertTrue(box.events.isEmpty)

        // A second match within the dwell: posted once.
        recognizer.cancelPending()
        recognizer.observe(shazam(offset: 40), isAudible: true)
        box.now = box.now.addingTimeInterval(12)
        recognizer.observe(shazam(offset: 52), isAudible: true)
        await gate.openAll()
        await recognizer.pending?.value
        XCTAssertEqual(box.events.map(\.source), ["shazam"])
    }

    func testShazamMatchMustBeRecent() async {
        let box = Box()
        let gate = Gate()
        let recognizer = BackgroundRecognizer(
            isEnabled: { true }, resolveCatalog: { _ in "pink-moon" },
            post: { box.events.append($0) }, now: { box.now }, sleep: { _ in try await gate.wait() }
        )
        recognizer.observe(shazam(offset: 1), isAudible: true)
        recognizer.observe(shazam(offset: 5), isAudible: true)
        box.now = box.now.addingTimeInterval(recognizer.shazamFreshness + 1)
        await gate.openAll()
        await recognizer.pending?.value
        XCTAssertTrue(box.events.isEmpty)
    }

    func testShortSilenceKeepsTheDwellRunning() async {
        let box = Box()
        let gate = Gate()
        let recognizer = BackgroundRecognizer(
            isEnabled: { true }, resolveCatalog: { _ in nil },
            post: { box.events.append($0) }, now: { box.now }, sleep: { _ in try await gate.wait() }
        )
        let song = track(namespace: "spotify", id: "sp1")
        recognizer.observe(song, isAudible: true)
        let dwell = recognizer.pending
        recognizer.observe(song, isAudible: false)   // quiet passage: grace timer, dwell kept
        recognizer.observe(song, isAudible: true)    // back before the grace ends
        XCTAssertEqual(recognizer.pending, dwell, "the dwell keeps running; no new one starts")
        await gate.openAll()
        await dwell?.value
        XCTAssertEqual(box.events.map(\.spotifyTrackId), ["sp1"])
    }

    func testRadioSongsAndMemoryReplaysAreNotRecognized() async {
        let box = Box()
        let recognizer = makeRecognizer(box)
        recognizer.noteRadioTrack("radio-song")
        let played = await recognizer.commit(track(namespace: "spotify", id: "radio-song"))
        XCTAssertFalse(played)

        recognizer.isRadioTrack = { $0 == "queued-song" }
        let queued = await recognizer.commit(track(namespace: "spotify", id: "queued-song"))
        XCTAssertFalse(queued)

        let mark = MemoryPlaybackMark(providerID: nil, title: "Blue in Green", artist: "Miles Davis", startedAt: box.now)
        recognizer.memoryPlayback = { mark }
        let memory = await recognizer.commit(track(namespace: "spotify", id: "memory-song"))
        XCTAssertFalse(memory)
        // Long after the memory was played, the same song counts again.
        box.now = box.now.addingTimeInterval(MemoryPlaybackMark.window + 1)
        let later = await recognizer.commit(track(namespace: "spotify", id: "memory-song"))
        XCTAssertTrue(later)
        XCTAssertEqual(box.events.map(\.spotifyTrackId), ["memory-song"])
    }

    func testCatalogFailuresAreRetriedButNoMatchIsCached() async {
        let box = Box()
        var attempts = 0
        let recognizer = BackgroundRecognizer(
            isEnabled: { true },
            resolveCatalog: { _ in
                attempts += 1
                if attempts == 1 { throw URLError(.timedOut) }
                return attempts == 2 ? nil : "late"
            },
            post: { box.events.append($0) }, now: { box.now }, sleep: { _ in }
        )
        let song = track(namespace: "apple_music", id: "AM1")
        let failed = await recognizer.commit(song)
        let noMatch = await recognizer.commit(song)
        let cached = await recognizer.commit(song)
        XCTAssertFalse(failed); XCTAssertFalse(noMatch); XCTAssertFalse(cached)
        XCTAssertEqual(attempts, 2, "a failure is retried; a real no-match is remembered")
    }

    func testResetForgetsAccountState() async {
        let box = Box()
        let recognizer = makeRecognizer(box)
        let song = track(namespace: "spotify", id: "sp1")
        let first = await recognizer.commit(song)
        XCTAssertTrue(first)
        recognizer.noteRadioTrack("radio-song")
        recognizer.reset()
        XCTAssertNil(recognizer.lastPosted)
        let again = await recognizer.commit(song)
        XCTAssertTrue(again, "a new account starts with a fresh repeat window")
        let radioSong = await recognizer.commit(track(namespace: "spotify", id: "radio-song"))
        XCTAssertTrue(radioSong)
    }

    func testTurningTheSettingOnLooksAtTheCurrentSong() async {
        let box = Box()
        box.enabled = false
        let recognizer = makeRecognizer(box)
        recognizer.observe(track(namespace: "spotify", id: "sp1"), isAudible: true)
        XCTAssertNil(recognizer.pending)
        box.enabled = true
        recognizer.reevaluate()
        await recognizer.pending?.value
        XCTAssertEqual(box.events.map(\.spotifyTrackId), ["sp1"])
    }

    func testPostsThroughTheRadioEventsEndpoint() async throws {
        let api = JukeAPI(baseURL: URL(string: "https://recognition-tests.example/")!, session: RecognitionURLProtocol.session(), token: { "tkn" })
        RecognitionURLProtocol.reset()
        let recognizer = BackgroundRecognizer(isEnabled: { true }, resolveCatalog: { _ in nil }, post: { try await api.postEvent($0) }, sleep: { _ in })
        let posted = await recognizer.commit(track(namespace: "spotify", id: "0aWMVrwxPNYkKmFthzmpRi"))
        XCTAssertTrue(posted)
        let request = try XCTUnwrap(RecognitionURLProtocol.last)
        XCTAssertEqual(request.method, "POST")
        XCTAssertEqual(request.path, "/api/v1/radio/events/")
        XCTAssertEqual(request.authorization, "Token tkn")
        XCTAssertEqual(request.body, #"{"event":"recognized","source":"metadata","spotifyTrackId":"0aWMVrwxPNYkKmFthzmpRi"}"#)
    }
}

@MainActor
private final class Gate {
    private var waiters: [CheckedContinuation<Void, Never>] = []
    func wait() async throws {
        await withCheckedContinuation { waiters.append($0) }
        try Task.checkCancellation()
    }
    func openAll() async {
        for _ in 0..<20 where waiters.isEmpty { await Task.yield() }
        let current = waiters
        waiters = []
        current.forEach { $0.resume() }
        await Task.yield()
    }
}

private func shazam(offset: TimeInterval) -> RecognizedTrack {
    RecognizedTrack(title: "Pink Moon", artist: "Nick Drake", album: nil, isrc: nil, artworkURL: nil, appleMusicURL: nil, shazamID: "99", matchOffset: offset)
}

private func track(title: String = "Blue in Green", artist: String = "Miles Davis", namespace: String? = nil, id: String? = nil, shazamID: String? = nil) -> RecognizedTrack {
    RecognizedTrack(title: title, artist: artist, album: nil, isrc: nil, artworkURL: nil, appleMusicURL: nil, shazamID: shazamID, providerNamespace: namespace, providerTrackID: id)
}

private func result(_ pk: Int, _ name: String, artists: String, id: String) -> CatalogSearchResult {
    CatalogSearchResult(pk: pk, name: name, spotifyID: id, albumName: nil, artistNames: artists, durationMs: nil, albumLink: nil, artworkURL: nil, spotifyData: nil)
}

private final class RecognitionURLProtocol: URLProtocol, @unchecked Sendable {
    struct Recorded: Sendable { let method: String; let path: String; let authorization: String?; let body: String? }
    private static let lock = NSLock()
    nonisolated(unsafe) private static var recorded: Recorded?
    static var last: Recorded? { lock.lock(); defer { lock.unlock() }; return recorded }
    static func reset() { lock.lock(); recorded = nil; lock.unlock() }
    static func session() -> URLSession {
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [RecognitionURLProtocol.self]
        return URLSession(configuration: config)
    }

    override class func canInit(with request: URLRequest) -> Bool { request.url?.host == "recognition-tests.example" }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        var body = request.httpBody
        if body == nil, let stream = request.httpBodyStream {
            stream.open(); defer { stream.close() }
            var data = Data(); var buffer = [UInt8](repeating: 0, count: 4096)
            while stream.hasBytesAvailable { let count = stream.read(&buffer, maxLength: buffer.count); if count <= 0 { break }; data.append(buffer, count: count) }
            body = data
        }
        Self.lock.lock()
        Self.recorded = Recorded(method: request.httpMethod ?? "", path: request.url?.path(percentEncoded: true) ?? "", authorization: request.value(forHTTPHeaderField: "Authorization"), body: body.map { String(decoding: $0, as: UTF8.self) })
        Self.lock.unlock()
        let response = HTTPURLResponse(url: request.url!, statusCode: 204, httpVersion: nil, headerFields: nil)!
        client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}
