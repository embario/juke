import XCTest
@testable import JukeCore

final class JukeSessionStoreTests: XCTestCase {

    // MARK: - Mock URL Protocol

    private class MockURLProtocol: URLProtocol {
        static var requestHandler: ((URLRequest) throws -> (HTTPURLResponse, Data))?

        override class func canInit(with request: URLRequest) -> Bool {
            return true
        }

        override class func canonicalRequest(for request: URLRequest) -> URLRequest {
            return request
        }

        override func startLoading() {
            guard let handler = Self.requestHandler else {
                XCTFail("Request handler not set")
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

    // MARK: - Mock Delegate

    private class MockDelegate: JukeSessionStoreDelegate {
        var authStateChangedCount = 0
        var profileUpdatedCount = 0
        var lastProfile: JukeMusicProfile?

        func sessionStoreDidUpdateAuthState(_ store: JukeSessionStore) {
            authStateChangedCount += 1
        }

        func sessionStore(_ store: JukeSessionStore, didUpdateProfile profile: JukeMusicProfile?) {
            profileUpdatedCount += 1
            lastProfile = profile
        }
    }

    // MARK: - Setup

    private var session: URLSession!
    private var defaults: UserDefaults!
    private let testKeyPrefix = "test.jukecore"

    override func setUp() {
        super.setUp()
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockURLProtocol.self]
        session = URLSession(configuration: config)

        defaults = UserDefaults(suiteName: "JukeSessionStoreTests")!
        defaults.removePersistentDomain(forName: "JukeSessionStoreTests")
    }

    override func tearDown() {
        MockURLProtocol.requestHandler = nil
        defaults.removePersistentDomain(forName: "JukeSessionStoreTests")
        session = nil
        defaults = nil
        super.tearDown()
    }

    @MainActor
    private func makeSessionStore() -> JukeSessionStore {
        let apiConfig = JukeAPIConfiguration(baseURL: URL(string: "https://api.test.com")!)
        let apiClient = JukeAPIClient(configuration: apiConfig, session: session)
        let authService = JukeAuthService(client: apiClient)
        let profileService = JukeProfileService(client: apiClient)

        return JukeSessionStore(
            keyPrefix: testKeyPrefix,
            authService: authService,
            profileService: profileService,
            defaults: defaults
        )
    }

    // MARK: - Initial State Tests

    @MainActor
    func testInitialStateNotAuthenticated() {
        let store = makeSessionStore()

        XCTAssertNil(store.token)
        XCTAssertNil(store.username)
        XCTAssertNil(store.profile)
        XCTAssertFalse(store.isAuthenticated)
        XCTAssertFalse(store.isLoadingProfile)
    }

    @MainActor
    func testRestoresPersistedToken() {
        // Pre-set values in defaults
        defaults.set("persistedtoken", forKey: "\(testKeyPrefix).auth.token")
        defaults.set("persisteduser", forKey: "\(testKeyPrefix).auth.username")

        // Mock the profile endpoint to return unauthorized (simulating stale token)
        MockURLProtocol.requestHandler = { request in
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 401,
                httpVersion: nil,
                headerFields: nil
            )!
            return (response, Data())
        }

        let store = makeSessionStore()

        // Token should be restored from defaults
        XCTAssertEqual(store.token, "persistedtoken")
        XCTAssertEqual(store.username, "persisteduser")
        XCTAssertTrue(store.isAuthenticated)
    }

    // MARK: - Login Tests

    @MainActor
    func testLoginSuccess() async throws {
        var requestCount = 0
        MockURLProtocol.requestHandler = { request in
            requestCount += 1
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 200,
                httpVersion: nil,
                headerFields: nil
            )!

            let data: Data
            if request.url?.path.contains("api-auth-token") == true {
                data = """
                {"token": "newtoken123"}
                """.data(using: .utf8)!
            } else {
                // Profile request
                data = """
                {"id": 1, "username": "testuser", "is_owner": true}
                """.data(using: .utf8)!
            }
            return (response, data)
        }

        let store = makeSessionStore()
        let delegate = MockDelegate()
        store.delegate = delegate

        try await store.login(username: "testuser", password: "testpass")

        XCTAssertEqual(store.token, "newtoken123")
        XCTAssertEqual(store.username, "testuser")
        XCTAssertTrue(store.isAuthenticated)
        XCTAssertNotNil(store.profile)
        XCTAssertEqual(delegate.authStateChangedCount, 1)

        // Verify persistence
        XCTAssertEqual(defaults.string(forKey: "\(testKeyPrefix).auth.token"), "newtoken123")
    }

    @MainActor
    func testLoginFailure() async {
        MockURLProtocol.requestHandler = { request in
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 401,
                httpVersion: nil,
                headerFields: nil
            )!
            return (response, """
            {"detail": "Invalid credentials"}
            """.data(using: .utf8)!)
        }

        let store = makeSessionStore()

        do {
            try await store.login(username: "testuser", password: "wrongpass")
            XCTFail("Expected error")
        } catch {
            XCTAssertFalse(store.isAuthenticated)
            XCTAssertNil(store.token)
        }
    }

    // MARK: - Logout Tests

    @MainActor
    func testLogout() async throws {
        // First login
        MockURLProtocol.requestHandler = { request in
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 200,
                httpVersion: nil,
                headerFields: nil
            )!
            if request.url?.path.contains("api-auth-token") == true {
                return (response, """
                {"token": "token123"}
                """.data(using: .utf8)!)
            } else if request.url?.path.contains("logout") == true {
                return (response, Data())
            } else {
                return (response, """
                {"id": 1, "username": "testuser", "is_owner": true}
                """.data(using: .utf8)!)
            }
        }

        let store = makeSessionStore()
        let delegate = MockDelegate()
        store.delegate = delegate

        try await store.login(username: "testuser", password: "pass")
        XCTAssertTrue(store.isAuthenticated)
        XCTAssertEqual(delegate.authStateChangedCount, 1)

        store.logout()

        XCTAssertNil(store.token)
        XCTAssertNil(store.username)
        XCTAssertNil(store.profile)
        XCTAssertFalse(store.isAuthenticated)
        XCTAssertEqual(delegate.authStateChangedCount, 2)

        // Verify persistence cleared
        XCTAssertNil(defaults.string(forKey: "\(testKeyPrefix).auth.token"))
        XCTAssertNil(defaults.string(forKey: "\(testKeyPrefix).auth.username"))
    }

    // MARK: - Authenticate With Token Tests

    @MainActor
    func testAuthenticateWithToken() {
        MockURLProtocol.requestHandler = { request in
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 200,
                httpVersion: nil,
                headerFields: nil
            )!
            return (response, """
            {"id": 1, "username": "verifieduser", "is_owner": true}
            """.data(using: .utf8)!)
        }

        let store = makeSessionStore()
        let delegate = MockDelegate()
        store.delegate = delegate

        store.authenticateWithToken("directtoken", username: "verifieduser")

        XCTAssertEqual(store.token, "directtoken")
        XCTAssertEqual(store.username, "verifieduser")
        XCTAssertTrue(store.isAuthenticated)
        XCTAssertEqual(delegate.authStateChangedCount, 1)
    }

    // MARK: - Display Name Tests

    @MainActor
    func testCurrentDisplayNameWithProfile() async throws {
        MockURLProtocol.requestHandler = { request in
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 200,
                httpVersion: nil,
                headerFields: nil
            )!
            if request.url?.path.contains("api-auth-token") == true {
                return (response, """
                {"token": "token"}
                """.data(using: .utf8)!)
            } else {
                return (response, """
                {"id": 1, "username": "user", "display_name": "Cool User", "is_owner": true}
                """.data(using: .utf8)!)
            }
        }

        let store = makeSessionStore()
        try await store.login(username: "user", password: "pass")

        XCTAssertEqual(store.currentDisplayName, "Cool User")
    }

    @MainActor
    func testCurrentDisplayNameFallback() {
        let store = makeSessionStore()
        XCTAssertEqual(store.currentDisplayName, "User")
    }

    // MARK: - Registration Tests

    @MainActor
    func testRegister() async throws {
        var capturedPath: String?
        MockURLProtocol.requestHandler = { request in
            capturedPath = request.url?.path
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 201,
                httpVersion: nil,
                headerFields: nil
            )!
            return (response, """
            {"detail": "Check your inbox to confirm your account."}
            """.data(using: .utf8)!)
        }

        let store = makeSessionStore()
        let message = try await store.register(
            username: "newuser",
            email: "new@example.com",
            password: "password123",
            passwordConfirm: "password123"
        )

        XCTAssertEqual(message, "Check your inbox to confirm your account.")
        // Registration doesn't auto-login
        XCTAssertFalse(store.isAuthenticated)
        // Verify the register endpoint was called
        XCTAssertTrue(capturedPath?.contains("register") ?? false, "Expected register path, got: \(capturedPath ?? "nil")")
    }
}
