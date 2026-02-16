//
//  juke_iOSTests.swift
//  juke-iOSTests
//
//  Created by Mario Barrenechea on 3/28/22.
//

import XCTest
import JukeCore
@testable import juke_iOS

class juke_iOSTests: XCTestCase {

    override func setUpWithError() throws {
        // Put setup code here. This method is called before the invocation of each test method in the class.
    }

    override func tearDownWithError() throws {
        // Put teardown code here. This method is called after the invocation of each test method in the class.
    }

    func testExample() throws {
        // This is an example of a functional test case.
        // Use XCTAssert and related functions to verify your tests produce the correct results.
        // Any test you write for XCTest can be annotated as throws and async.
        // Mark your test throws to produce an unexpected failure when your test encounters an uncaught error.
        // Mark your test async to allow awaiting for asynchronous code to complete. Check the results with assertions afterwards.
    }

    func testPerformanceExample() throws {
        // This is an example of a performance test case.
        self.measure {
            // Put the code you want to measure the time of here.
        }
    }

    func testAppConfigurationEnvOverridesPlist() {
        let config = JukeAppConfiguration(
            environment: ["DISABLE_REGISTRATION": "true"],
            plistValue: "false"
        )

        XCTAssertTrue(config.isRegistrationDisabled)
    }

    func testAppConfigurationPlistBooleanFallback() {
        let config = JukeAppConfiguration(
            environment: [:],
            plistValue: true
        )

        XCTAssertTrue(config.isRegistrationDisabled)
    }

    func testAPIConfigurationEnvOverridesPlist() {
        let config = JukeAPIConfiguration(
            environment: ["BACKEND_URL": "http://env.example.com"],
            backendPlist: "http://plist.example.com",
            frontendPlist: nil
        )

        XCTAssertEqual(config.baseURL.absoluteString, "http://env.example.com")
    }

    func testAPIConfigurationPlistFallback() {
        let config = JukeAPIConfiguration(
            environment: [:],
            backendPlist: "http://plist.example.com",
            frontendPlist: nil
        )

        XCTAssertEqual(config.baseURL.absoluteString, "http://plist.example.com")
    }

}

@MainActor
final class OnboardingStoreTests: XCTestCase {
    private func makeDefaults() -> UserDefaults {
        let suiteName = "juke-iOS.tests.onboarding.\(UUID().uuidString)"
        let defaults = UserDefaults(suiteName: suiteName)!
        defaults.removePersistentDomain(forName: suiteName)
        return defaults
    }

    func testDraftPersistsPerUserKey() {
        let defaults = makeDefaults()
        let storeA = OnboardingStore(userKey: "user-a", defaults: defaults)
        storeA.toggleFavoriteGenre("rock")

        let storeA2 = OnboardingStore(userKey: "user-a", defaults: defaults)
        XCTAssertEqual(storeA2.data.favoriteGenres, ["rock"])

        let storeB = OnboardingStore(userKey: "user-b", defaults: defaults)
        XCTAssertTrue(storeB.data.favoriteGenres.isEmpty)
    }

    func testMarkCompletedClearsDraft() {
        let defaults = makeDefaults()
        let store = OnboardingStore(userKey: "user-a", defaults: defaults)
        store.toggleFavoriteGenre("pop")
        store.markCompleted()

        XCTAssertTrue(OnboardingStore.isCompleted(for: "user-a", defaults: defaults))
        let refreshed = OnboardingStore(userKey: "user-a", defaults: defaults)
        XCTAssertTrue(refreshed.data.favoriteGenres.isEmpty)
    }

    func testFavoriteGenreToggleRespectsLimit() {
        let defaults = makeDefaults()
        let store = OnboardingStore(userKey: "user-a", defaults: defaults)
        store.toggleFavoriteGenre("rock")
        store.toggleFavoriteGenre("pop")
        store.toggleFavoriteGenre("jazz")
        store.toggleFavoriteGenre("hiphop")

        XCTAssertEqual(store.data.favoriteGenres.count, 3)
        XCTAssertFalse(store.data.favoriteGenres.contains("hiphop"))
    }

    func testSearchCitiesIsCaseInsensitiveAndLimited() {
        let results = searchCities("an")
        XCTAssertTrue(results.contains(where: { $0.name == "San Francisco" }))
        XCTAssertLessThanOrEqual(results.count, 10)
    }
}

private final class MockURLProtocol: URLProtocol {
    static var requestHandler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

    override class func canInit(with request: URLRequest) -> Bool { true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }

    override func startLoading() {
        guard let handler = MockURLProtocol.requestHandler else {
            let error = NSError(domain: "MockURLProtocol", code: -1, userInfo: [NSLocalizedDescriptionKey: "Missing request handler"])
            client?.urlProtocol(self, didFailWithError: error)
            return
        }

        do {
            let (response, data) = try handler(request)
            client?.urlProtocol(self, didReceive: response, cacheStoragePolicy: .notAllowed)
            client?.urlProtocol(self, didLoad: data)
            client?.urlProtocolDidFinishLoading(self)
        } catch {
            client?.urlProtocol(self, didFailWithError: error)
        }
    }

    override func stopLoading() {}
}

final class PlaybackServiceTests: XCTestCase {
    override func tearDown() {
        super.tearDown()
        MockURLProtocol.requestHandler = nil
    }

    func testNextSendsProviderAndDeviceAndDecodesState() async throws {
        let service = makeService()

        MockURLProtocol.requestHandler = { request in
            XCTAssertTrue(
                request.url?.path == "/api/v1/playback/next"
                    || request.url?.path == "/api/v1/playback/next/"
            )
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Token token-123")

            let body = try self.bodyData(for: request)
            let payload = try XCTUnwrap(try JSONSerialization.jsonObject(with: body) as? [String: Any])
            XCTAssertEqual(payload["provider"] as? String, "spotify")
            XCTAssertEqual(payload["device_id"] as? String, "device-1")

            let json = """
            {
              "provider": "spotify",
              "is_playing": true,
              "progress_ms": 1200,
              "track": {
                "id": "track-1",
                "uri": "spotify:track:track-1",
                "name": "Song A",
                "duration_ms": 240000,
                "artists": []
              },
              "device": {
                "id": "device-1",
                "name": "iPhone",
                "type": "Smartphone"
              }
            }
            """
            return try self.okResponse(for: request, json: json)
        }

        let state = try await service.next(token: "token-123", provider: "spotify", deviceId: "device-1")
        XCTAssertEqual(state?.provider, "spotify")
        XCTAssertEqual(state?.isPlaying, true)
        XCTAssertEqual(state?.track?.id, "track-1")
        XCTAssertEqual(state?.device?.id, "device-1")
    }

    func testResumeUsesPlayEndpointWithoutTrackOrContextFields() async throws {
        let service = makeService()

        MockURLProtocol.requestHandler = { request in
            XCTAssertTrue(
                request.url?.path == "/api/v1/playback/play"
                    || request.url?.path == "/api/v1/playback/play/"
            )
            XCTAssertEqual(request.httpMethod, "POST")

            let body = try self.bodyData(for: request)
            let payload = try XCTUnwrap(try JSONSerialization.jsonObject(with: body) as? [String: Any])
            XCTAssertEqual(payload["device_id"] as? String, "device-2")
            XCTAssertNil(payload["track_uri"])
            XCTAssertNil(payload["context_uri"])
            XCTAssertNil(payload["offset_uri"])

            let json = """
            {
              "provider": "spotify",
              "is_playing": true,
              "progress_ms": 0,
              "track": null,
              "device": {
                "id": "device-2",
                "name": "Web Player",
                "type": "Computer"
              }
            }
            """
            return try self.okResponse(for: request, json: json)
        }

        let state = try await service.resume(token: "token-123", provider: nil, deviceId: "device-2")
        XCTAssertEqual(state?.provider, "spotify")
        XCTAssertEqual(state?.device?.id, "device-2")
    }

    private func makeService() -> PlaybackService {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [MockURLProtocol.self]
        let session = URLSession(configuration: configuration)
        let apiConfig = JukeAPIConfiguration(
            environment: [:],
            backendPlist: "http://backend.example.com",
            frontendPlist: nil
        )
        let client = JukeAPIClient(configuration: apiConfig, session: session)
        return PlaybackService(client: client)
    }

    private func okResponse(for request: URLRequest, json: String) throws -> (HTTPURLResponse, Data) {
        let url = try XCTUnwrap(request.url)
        let response = try XCTUnwrap(
            HTTPURLResponse(url: url, statusCode: 200, httpVersion: nil, headerFields: nil)
        )
        return (response, Data(json.utf8))
    }

    private func bodyData(for request: URLRequest) throws -> Data {
        if let body = request.httpBody {
            return body
        }

        guard let stream = request.httpBodyStream else {
            throw NSError(
                domain: "PlaybackServiceTests",
                code: 1,
                userInfo: [NSLocalizedDescriptionKey: "Expected an HTTP body or HTTP body stream."]
            )
        }

        stream.open()
        defer { stream.close() }

        var data = Data()
        let bufferSize = 1024
        let buffer = UnsafeMutablePointer<UInt8>.allocate(capacity: bufferSize)
        defer { buffer.deallocate() }

        while stream.hasBytesAvailable {
            let read = stream.read(buffer, maxLength: bufferSize)
            if read < 0 {
                throw stream.streamError ?? NSError(
                    domain: "PlaybackServiceTests",
                    code: 2,
                    userInfo: [NSLocalizedDescriptionKey: "Unable to read HTTP body stream."]
                )
            }
            if read == 0 {
                break
            }
            data.append(buffer, count: read)
        }

        return data
    }
}
