import Foundation
import Testing
@testable import JukeApp

private final class CapturingProtocol: URLProtocol {
    nonisolated(unsafe) static var authorization: String?
    override class func canInit(with request: URLRequest) -> Bool { request.url?.path.contains("playback/state") == true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.authorization = request.value(forHTTPHeaderField: "Authorization")
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: 204, httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Suite(.serialized) struct PlaybackAuthTests {
    @Test func invalidatedClientRejectsRetainedCredentials() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingProtocol.self]
        CapturingProtocol.authorization = nil
        let client = VibeAPI(baseURL: URL(string: "https://old-server.example/api/v1/")!, session: URLSession(configuration: configuration))
        client.invalidate()
        await #expect(throws: CancellationError.self) {
            _ = try await client.spotifyPlayback(token: "old-server-token")
        }
        await #expect(throws: CancellationError.self) {
            _ = try await client.encryptedChanges(token: "old-server-token")
        }
        await #expect(throws: CancellationError.self) {
            _ = try await client.chat("private", currentTrack: nil, token: "old-server-token")
        }
        #expect(CapturingProtocol.authorization == nil)
    }

    @Test func spotifyPlaybackUsesTokenScheme() async throws {
        let configuration = URLSessionConfiguration.ephemeral
        configuration.protocolClasses = [CapturingProtocol.self]
        CapturingProtocol.authorization = nil
        let track = try await VibeAPI(session: URLSession(configuration: configuration)).spotifyPlayback(token: "abc123")
        #expect(track == nil)
        #expect(CapturingProtocol.authorization == "Token abc123")
    }
}
