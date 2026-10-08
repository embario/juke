import Foundation
import Testing
@testable import JukeApp

private final class CapturingProtocol: URLProtocol {
    nonisolated(unsafe) static var authorization: String?
    override class func canInit(with request: URLRequest) -> Bool { request.url?.path.hasSuffix("playback/state/") == true }
    override class func canonicalRequest(for request: URLRequest) -> URLRequest { request }
    override func startLoading() {
        Self.authorization = request.value(forHTTPHeaderField: "Authorization")
        client?.urlProtocol(self, didReceive: HTTPURLResponse(url: request.url!, statusCode: 204, httpVersion: nil, headerFields: nil)!, cacheStoragePolicy: .notAllowed)
        client?.urlProtocolDidFinishLoading(self)
    }
    override func stopLoading() {}
}

@Suite(.serialized) struct PlaybackAuthTests {
    @Test func spotifyPlaybackUsesTokenScheme() async throws {
        URLProtocol.registerClass(CapturingProtocol.self); defer { URLProtocol.unregisterClass(CapturingProtocol.self) }
        CapturingProtocol.authorization = nil
        let track = try await VibeAPI().spotifyPlayback(token: "abc123")
        #expect(track == nil)
        #expect(CapturingProtocol.authorization == "Token abc123")
    }
}
