import Foundation
import XCTest
@testable import Juke

/// Decoding and request-shape tests for the Radio API contract. Fixtures in
/// `Fixtures/Radio` are written from `tasks/juke-app-implementation.md`.
final class RadioModelDecodingTests: XCTestCase {
    func testStationListDecodesPersonalAndCustomStations() throws {
        let list = try decodeFixture("stations", as: Radio.StationList.self)
        XCTAssertEqual(list.stations.count, 2)

        let mine = list.stations[0]
        XCTAssertEqual(mine.id.rawValue, "0d6c8a1e-5b1f-4c7e-9a52-6f0f6c2b8a01")
        XCTAssertEqual(mine.name, "My Station")
        XCTAssertEqual(mine.kind, .personal)
        XCTAssertTrue(mine.isPersonal)
        XCTAssertEqual(mine.frequency, 88.7, accuracy: 0.0001)
        XCTAssertEqual(mine.frequencyLabel, "88.7")
        XCTAssertEqual(mine.seeds.map(\.kind), [.track, .artist])
        XCTAssertNil(mine.seeds[1].artworkUrl)
        XCTAssertEqual(mine.thumbnailURLs.count, 3)
        XCTAssertEqual(mine.feelings, ["😌", "☀️", "✨"])
        XCTAssertTrue(mine.learning)
        XCTAssertEqual(mine.exclusions.first?.scope, .everywhere)
        XCTAssertEqual(mine.exclusions.first?.kind, .genre)
        XCTAssertEqual(mine.createdAt, ISO8601DateFormatter().date(from: "2026-10-01T12:00:00Z"))

        let night = list.stations[1]
        XCTAssertEqual(night.id.rawValue, "6c7d7f8e-2f0b-4d38-9d5e-2a0e7d1c9b11")
        XCTAssertEqual(night.kind, .custom)
        XCTAssertEqual(night.createdAt.timeIntervalSince1970, 1_790_857_815.123, accuracy: 0.001)
    }

    func testTracksDecodeOptionalFieldsAndDerivedValues() throws {
        let next = try decodeFixture("next", as: Radio.NextTracksResponse.self)
        XCTAssertEqual(next.source, .mlcore)
        XCTAssertEqual(next.tracks.count, 2)
        XCTAssertEqual(next.tracks[0].uri, "spotify:track:0aWMVrwxPNYkKmFthzmpRi")
        XCTAssertEqual(next.tracks[0].artworkURL?.host, "i.scdn.co")
        XCTAssertEqual(next.tracks[0].duration, 337, accuracy: 0.001)
        XCTAssertNil(next.tracks[1].album)
        XCTAssertNil(next.tracks[1].artworkURL)
    }

    func testReactionsWithAndWithoutSuggestion() throws {
        let suggested = try decodeFixture("reactions", as: Radio.ReactionsResponse.self)
        XCTAssertEqual(suggested.reactions, ["😌", "slow sunday"])
        XCTAssertEqual(suggested.suggestion?.stationId.rawValue, "c4d6e8f0-1a3b-4c5d-8e7f-9a0b1c2d3e05")
        XCTAssertEqual(suggested.suggestion?.matched, ["😌", "☕"])

        let plain = try decodeFixture("reactions-no-suggestion", as: Radio.ReactionsResponse.self)
        XCTAssertNil(plain.suggestion)
    }

    func testPlayKeepsOpaquePlaybackState() throws {
        let play = try decodeFixture("play", as: Radio.PlayResponse.self)
        XCTAssertEqual(play.track.title, "Blue in Green")
        XCTAssertEqual(play.source, .mlcore)
        XCTAssertEqual(play.state?["is_playing"], .bool(true))
        XCTAssertEqual(play.state?["device"]?["name"], .string("Mac"))
    }

    func testCrateItemsAcceptSingularOrPluralKindsAndMakeSeeds() throws {
        let crate = try decodeFixture("crate", as: Radio.CrateResponse.self)
        XCTAssertEqual(crate.items.map(\.kind), [.track, .artist])
        XCTAssertEqual(crate.items[0].track?.album, "Kind of Blue")
        XCTAssertEqual(crate.items[1].id, 44)
        XCTAssertNil(crate.items[1].track)
        XCTAssertEqual(crate.items[1].seed, Radio.Seed(kind: .artist, spotifyId: "0kbYTNQb4Pb1rPbbaF0pT4", title: "Miles Davis", subtitle: "Artist", artworkUrl: nil))
    }

    func testSessionSummaryAndExclusion() throws {
        let summary = try decodeFixture("session-summary", as: Radio.SessionSummary.self)
        XCTAssertEqual(summary.songCount, 2)
        XCTAssertEqual(summary.reactions, ["🌙", "late drive"])
        XCTAssertEqual(summary.startedAt, ISO8601DateFormatter().date(from: "2026-10-01T18:04:05Z"))

        let empty = try decodeFixture("session-summary-empty", as: Radio.SessionSummary.self)
        XCTAssertNil(empty.startedAt, "no radio session yet")
        XCTAssertEqual(empty.songCount, 0)
        XCTAssertTrue(empty.tracks.isEmpty)

        let exclusion = try decodeFixture("exclusion", as: Radio.Exclusion.self)
        XCTAssertEqual(exclusion, Radio.Exclusion(id: "b7e2a9d4-6c1f-4e3b-a5d8-0f2c4e6a8b31", scope: .station, kind: .artist, value: "4tZwfgrHOc3mvqYlEYSvVi", label: "Daft Punk"))
    }

    func testUnknownEnumValuesDoNotBreakDecoding() throws {
        let json = Data(#"{"tracks": [], "source": "a-future-ranker"}"#.utf8)
        XCTAssertEqual(try JukeAPI.decoder.decode(Radio.NextTracksResponse.self, from: json).source, .unknown)
        let kind = try JukeAPI.decoder.decode([Radio.StationKind].self, from: Data(#"["shared"]"#.utf8))
        XCTAssertEqual(kind, [.unknown])
    }

    func testEventsEncodeSnakeCaseNamesAndOmitNilFields() throws {
        let request = Radio.EventRequest(stationId: nil, spotifyTrackId: "abc", event: .notOnStation, positionMs: nil, source: nil)
        XCTAssertEqual(try jsonString(request), #"{"event":"not_on_station","spotifyTrackId":"abc"}"#)
        XCTAssertEqual(Radio.Event.neverArtist.rawValue, "never_artist")
        XCTAssertEqual(Set(Radio.Event.allCases.map(\.rawValue)).subtracting(["unknown"]), [
            "play", "complete", "skip", "less", "not_on_station", "never_artist", "seek", "save", "recognized",
        ])
    }

    func testIDsEncodeAsNumbersWhenNumeric() throws {
        XCTAssertEqual(try jsonString(Radio.PlayRequest(stationId: 12, mode: .queue)), #"{"mode":"queue","stationId":12}"#)
        XCTAssertEqual(
            try jsonString(Radio.PlayRequest(stationId: "6c7d", mode: .now, deviceId: "dev")),
            #"{"deviceId":"dev","mode":"now","stationId":"6c7d"}"#
        )
    }

    func testPartialStationUpdateSendsOnlyChangedFields() throws {
        XCTAssertEqual(try jsonString(Radio.UpdateStationRequest(frequency: 92.3)), #"{"frequency":92.3}"#)
        XCTAssertEqual(try jsonString(Radio.UpdateStationRequest(name: "Late", learning: false)), #"{"learning":false,"name":"Late"}"#)
    }

    func testStationRoundTripsThroughTheAPICoders() throws {
        let station = try decodeFixture("station", as: Radio.Station.self)
        let again = try JukeAPI.decoder.decode(Radio.Station.self, from: JukeAPI.encoder.encode(station))
        XCTAssertEqual(again.id, station.id)
        XCTAssertEqual(again.seeds, station.seeds)
        XCTAssertEqual(again.createdAt.timeIntervalSince1970, station.createdAt.timeIntervalSince1970, accuracy: 1)
    }

    func testFrequencySnapsToOddTenthsInRange() {
        XCTAssertEqual(Radio.snappedFrequency(88.7), 88.7, accuracy: 0.0001)
        XCTAssertEqual(Radio.snappedFrequency(88.2), 88.3, accuracy: 0.0001)
        XCTAssertEqual(Radio.snappedFrequency(92.38), 92.3, accuracy: 0.0001)
        XCTAssertEqual(Radio.snappedFrequency(80), 88.1, accuracy: 0.0001)
        XCTAssertEqual(Radio.snappedFrequency(120), 107.9, accuracy: 0.0001)
    }
}

final class JukeAPIRequestTests: XCTestCase {
    func testEveryRadioEndpointUsesTheContractPathMethodAndBody() async throws {
        let recorder = RecordedRequests()
        let api = makeAPI(recorder: recorder) { request in
            let path = request.url!.path(percentEncoded: true)
            switch (request.httpMethod!, path) {
            case ("GET", "/api/v1/radio/stations/"): return (200, try fixture("stations"))
            case ("POST", "/api/v1/radio/stations/"): return (201, try fixture("station"))
            case ("PATCH", "/api/v1/radio/stations/3f2b9c44-7a1d-4e8b-b3c5-12a9e7d0c412/"): return (200, try fixture("station"))
            case ("DELETE", "/api/v1/radio/stations/3f2b9c44-7a1d-4e8b-b3c5-12a9e7d0c412/"), ("DELETE", "/api/v1/radio/exclusions/b7e2a9d4-6c1f-4e3b-a5d8-0f2c4e6a8b31/"): return (204, Data())
            case ("POST", "/api/v1/radio/stations/3f2b9c44-7a1d-4e8b-b3c5-12a9e7d0c412/exclusions/"): return (201, try fixture("exclusion"))
            case ("PUT", "/api/v1/radio/reactions/"): return (200, try fixture("reactions"))
            case ("POST", "/api/v1/radio/stations/3f2b9c44-7a1d-4e8b-b3c5-12a9e7d0c412/next"): return (200, try fixture("next"))
            case ("POST", "/api/v1/radio/play"): return (200, try fixture("play"))
            case ("POST", "/api/v1/radio/events/"): return (204, Data())
            case ("GET", "/api/v1/radio/crate/"): return (200, try fixture("crate"))
            case ("GET", "/api/v1/radio/session/summary"): return (200, try fixture("session-summary"))
            default: return (404, Data())
            }
        }

        let stations = try await api.stations()
        XCTAssertEqual(stations.count, 2)
        let seed = Radio.Seed(kind: .track, spotifyId: "3xKsf9qdS1CyvXSMEid6g8", title: "Pink + White", subtitle: "Frank Ocean", artworkUrl: nil)
        _ = try await api.createStation(seeds: [seed], feelings: ["🥹"])
        _ = try await api.updateStation("3f2b9c44-7a1d-4e8b-b3c5-12a9e7d0c412", Radio.UpdateStationRequest(frequency: 101.4))
        try await api.deleteStation("3f2b9c44-7a1d-4e8b-b3c5-12a9e7d0c412")
        _ = try await api.addExclusion(stationID: "3f2b9c44-7a1d-4e8b-b3c5-12a9e7d0c412", Radio.CreateExclusionRequest(scope: .station, kind: .artist, value: "4tZw", label: "Daft Punk"))
        try await api.deleteExclusion("b7e2a9d4-6c1f-4e3b-a5d8-0f2c4e6a8b31")
        _ = try await api.setReactions(spotifyTrackID: "0aWM", stationID: "3f2b9c44-7a1d-4e8b-b3c5-12a9e7d0c412", reactions: ["😌"])
        _ = try await api.nextTracks(stationID: "3f2b9c44-7a1d-4e8b-b3c5-12a9e7d0c412", count: 40, recentTrackIDs: ["a", "b"])
        _ = try await api.play(stationID: "3f2b9c44-7a1d-4e8b-b3c5-12a9e7d0c412", mode: .queue, recentTrackIDs: ["a"])
        try await api.postEvent(Radio.EventRequest(stationId: "3f2b9c44-7a1d-4e8b-b3c5-12a9e7d0c412", spotifyTrackId: "0aWM", event: .skip, positionMs: 4_000, source: "radio", artistId: "art1"))
        let crate = try await api.crate(kind: .album, query: "  kind of blue ")
        XCTAssertEqual(crate.count, 2)
        _ = try await api.sessionSummary()

        let requests = recorder.all
        XCTAssertEqual(requests.map { "\($0.method) \($0.path)" }, [
            "GET /api/v1/radio/stations/",
            "POST /api/v1/radio/stations/",
            "PATCH /api/v1/radio/stations/3f2b9c44-7a1d-4e8b-b3c5-12a9e7d0c412/",
            "DELETE /api/v1/radio/stations/3f2b9c44-7a1d-4e8b-b3c5-12a9e7d0c412/",
            "POST /api/v1/radio/stations/3f2b9c44-7a1d-4e8b-b3c5-12a9e7d0c412/exclusions/",
            "DELETE /api/v1/radio/exclusions/b7e2a9d4-6c1f-4e3b-a5d8-0f2c4e6a8b31/",
            "PUT /api/v1/radio/reactions/",
            "POST /api/v1/radio/stations/3f2b9c44-7a1d-4e8b-b3c5-12a9e7d0c412/next",
            "POST /api/v1/radio/play",
            "POST /api/v1/radio/events/",
            "GET /api/v1/radio/crate/",
            "GET /api/v1/radio/session/summary",
        ])
        XCTAssertTrue(requests.allSatisfy { $0.authorization == "Token secret-token" })
        XCTAssertEqual(requests[1].body, #"{"feelings":["🥹"],"seeds":[{"kind":"track","spotifyId":"3xKsf9qdS1CyvXSMEid6g8","subtitle":"Frank Ocean","title":"Pink + White"}]}"#)
        XCTAssertEqual(requests[2].body, #"{"frequency":101.4}"#)
        XCTAssertEqual(requests[4].body, #"{"kind":"artist","label":"Daft Punk","scope":"station","value":"4tZw"}"#)
        XCTAssertEqual(requests[6].body, #"{"reactions":["😌"],"spotifyTrackId":"0aWM","stationId":"3f2b9c44-7a1d-4e8b-b3c5-12a9e7d0c412"}"#)
        XCTAssertEqual(requests[7].body, #"{"count":10,"recentTrackIds":["a","b"]}"#, "count is clamped to the contract's 1-10")
        XCTAssertEqual(requests[8].body, #"{"mode":"queue","recentTrackIds":["a"],"stationId":"3f2b9c44-7a1d-4e8b-b3c5-12a9e7d0c412"}"#)
        XCTAssertEqual(requests[9].body, #"{"artistId":"art1","event":"skip","positionMs":4000,"source":"radio","spotifyTrackId":"0aWM","stationId":"3f2b9c44-7a1d-4e8b-b3c5-12a9e7d0c412"}"#)
        XCTAssertEqual(requests[10].query, "kind=albums&q=kind%20of%20blue")
        XCTAssertNil(requests[0].body)
    }

    func testErrorsCarryTheServerCodeAndDetail() async throws {
        let api = makeAPI { request in
            switch request.url!.path(percentEncoded: true) {
            case "/api/v1/radio/stations/": return (401, Data(#"{"detail":"Invalid token."}"#.utf8))
            case "/api/v1/radio/stations/1/": return (400, Data(#"{"seeds":["Add at least one seed or feeling."]}"#.utf8))
            case "/api/v1/radio/play": return (400, Data(#"{"code":"playback_provider_not_linked","detail":"Connect Spotify first."}"#.utf8))
            case "/api/v1/radio/stations/1/next": return (409, Data(#"{"code":"radio_no_tracks","detail":"Nothing left to play."}"#.utf8))
            case "/api/v1/radio/events/": return (502, Data(#"{"code":"playback_provider_failure","detail":"no active device"}"#.utf8))
            case "/api/v1/radio/crate/": return (403, Data())
            default: return (503, Data())
            }
        }
        await assertThrows(JukeAPIError.unauthorized(code: nil, detail: "Invalid token.")) { _ = try await api.stations() }
        await assertThrows(JukeAPIError.rejected(status: 400, code: nil, detail: "Add at least one seed or feeling.")) {
            _ = try await api.updateStation(1, Radio.UpdateStationRequest(seeds: []))
        }
        await assertThrows(JukeAPIError.rejected(status: 400, code: "playback_provider_not_linked", detail: "Connect Spotify first.")) {
            _ = try await api.play(stationID: 1, mode: .now)
        }
        await assertThrows(JukeAPIError.rejected(status: 409, code: "radio_no_tracks", detail: "Nothing left to play.")) {
            _ = try await api.nextTracks(stationID: 1)
        }
        do {
            try await api.postEvent(Radio.EventRequest(spotifyTrackId: "x", event: .play))
            XCTFail("Expected a provider failure")
        } catch let error as JukeAPIError {
            XCTAssertEqual(error.code, "playback_provider_failure")
            XCTAssertEqual(error.detail, "no active device")
            XCTAssertEqual(error.status, 502)
            XCTAssertEqual(error.errorDescription, "no active device")
        }
        await assertThrows(JukeAPIError.forbidden(code: nil, detail: nil)) { _ = try await api.crate(kind: .track) }
        await assertThrows(JukeAPIError.server(status: 503, code: nil, detail: nil)) { _ = try await api.sessionSummary() }
        XCTAssertNil(JukeAPIError.notSignedIn.code)
    }

    func testMissingTokenFailsWithoutANetworkRequest() async {
        let recorder = RecordedRequests()
        let api = makeAPI(recorder: recorder, token: nil) { _ in (200, Data()) }
        await assertThrows(JukeAPIError.notSignedIn) { _ = try await api.stations() }
        XCTAssertTrue(recorder.all.isEmpty)
    }

    func testMalformedResponsesBecomeDecodingErrors() async {
        let api = makeAPI { _ in (200, Data(#"{"stations": [{"id": 1}]}"#.utf8)) }
        do {
            _ = try await api.stations()
            XCTFail("Expected a decoding error")
        } catch let error as JukeAPIError {
            guard case .decoding = error else { return XCTFail("Unexpected \(error)") }
        } catch { XCTFail("Unexpected \(error)") }
    }

    func testDefaultBaseURLFollowsTheBackendSetting() {
        let api = JukeAPI(token: { "t" })
        XCTAssertEqual(api.apiURL, JukeServer.apiURL())
        let fixed = JukeAPI(baseURL: URL(string: "https://example.test/")!, token: { "t" })
        let request = fixed.request(.get, "radio/stations/", token: "t")
        XCTAssertEqual(request.url?.absoluteString, "https://example.test/api/v1/radio/stations/")
        XCTAssertEqual(request.value(forHTTPHeaderField: "Accept"), "application/json")
        XCTAssertNil(request.value(forHTTPHeaderField: "Content-Type"))
    }
}

// MARK: - Helpers

private func fixture(_ name: String) throws -> Data {
    let bundle = Bundle(for: RadioModelDecodingTests.self)
    let url = try XCTUnwrap(bundle.url(forResource: name, withExtension: "json"), "Missing fixture \(name).json")
    return try Data(contentsOf: url)
}

private func decodeFixture<T: Decodable>(_ name: String, as type: T.Type) throws -> T {
    try JukeAPI.decoder.decode(T.self, from: fixture(name))
}

private func jsonString<T: Encodable>(_ value: T) throws -> String {
    String(decoding: try JukeAPI.encoder.encode(value), as: UTF8.self)
}

private func assertThrows(_ expected: JukeAPIError, file: StaticString = #filePath, line: UInt = #line, _ body: () async throws -> Void) async {
    do {
        try await body()
        XCTFail("Expected \(expected)", file: file, line: line)
    } catch let error as JukeAPIError {
        XCTAssertEqual(error, expected, file: file, line: line)
    } catch {
        XCTFail("Unexpected \(error)", file: file, line: line)
    }
}

private struct RecordedRequest: Sendable {
    let method: String
    let path: String
    let query: String?
    let authorization: String?
    let body: String?
}

private final class RecordedRequests: @unchecked Sendable {
    private let lock = NSLock()
    private var values: [RecordedRequest] = []
    func append(_ value: RecordedRequest) { lock.lock(); defer { lock.unlock() }; values.append(value) }
    var all: [RecordedRequest] { lock.lock(); defer { lock.unlock() }; return values }
}

private func makeAPI(
    recorder: RecordedRequests = RecordedRequests(),
    token: String? = "secret-token",
    handler: @escaping @Sendable (URLRequest) throws -> (Int, Data)
) -> JukeAPI {
    let host = "\(UUID().uuidString.lowercased()).radio-tests.example"
    RadioURLProtocol.handlers.set({ request in
        let components = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)
        recorder.append(RecordedRequest(
            method: request.httpMethod ?? "GET",
            path: request.url!.path(percentEncoded: true),
            query: components?.percentEncodedQuery,
            authorization: request.value(forHTTPHeaderField: "Authorization"),
            body: request.readBody().map { String(decoding: $0, as: UTF8.self) }
        ))
        return try handler(request)
    }, host: host)
    let config = URLSessionConfiguration.ephemeral
    config.protocolClasses = [RadioURLProtocol.self]
    return JukeAPI(baseURL: URL(string: "https://\(host)/")!, session: URLSession(configuration: config), token: { token })
}

private final class RadioRequestHandlers: @unchecked Sendable {
    typealias Handler = @Sendable (URLRequest) throws -> (Int, Data)
    private let lock = NSLock()
    private var values: [String: Handler] = [:]
    func set(_ handler: @escaping Handler, host: String) { lock.lock(); defer { lock.unlock() }; values[host] = handler }
    func get(host: String) -> Handler? { lock.lock(); defer { lock.unlock() }; return values[host] }
}

private final class RadioURLProtocol: URLProtocol, @unchecked Sendable {
    static let handlers = RadioRequestHandlers()
    override class func canInit(with request: URLRequest) -> Bool { request.url?.host?.hasSuffix("radio-tests.example") == true }
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
    func readBody() -> Data? {
        if let httpBody { return httpBody }
        guard let stream = httpBodyStream else { return nil }
        stream.open(); defer { stream.close() }
        var result = Data(); var bytes = [UInt8](repeating: 0, count: 4096)
        while stream.hasBytesAvailable {
            let count = stream.read(&bytes, maxLength: bytes.count)
            if count <= 0 { break }
            result.append(contentsOf: bytes.prefix(count))
        }
        return result
    }
}
