import XCTest
@testable import JukeCore

@MainActor
final class JukeAuthViewModelTests: XCTestCase {

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

    // MARK: - Setup

    private var session: URLSession!
    private var defaults: UserDefaults!
    private let testKeyPrefix = "test.authvm"

    override func setUp() {
        super.setUp()
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockURLProtocol.self]
        session = URLSession(configuration: config)

        defaults = UserDefaults(suiteName: "JukeAuthViewModelTests")!
        defaults.removePersistentDomain(forName: "JukeAuthViewModelTests")
    }

    override func tearDown() {
        MockURLProtocol.requestHandler = nil
        defaults.removePersistentDomain(forName: "JukeAuthViewModelTests")
        session = nil
        defaults = nil
        super.tearDown()
    }

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

    private func makeTestConfiguration(registrationDisabled: Bool = false) -> JukeAppConfiguration {
        let env = registrationDisabled ? ["DISABLE_REGISTRATION": "true"] : [:]
        return JukeAppConfiguration(environment: env, plistValue: nil)
    }

    private func makeViewModel(session: JukeSessionStore? = nil, registrationDisabled: Bool = false) -> JukeAuthViewModel {
        let sessionStore = session ?? makeSessionStore()
        let apiConfig = JukeAPIConfiguration(baseURL: URL(string: "https://api.test.com")!)
        let apiClient = JukeAPIClient(configuration: apiConfig, session: self.session)
        let authService = JukeAuthService(client: apiClient)
        let config = makeTestConfiguration(registrationDisabled: registrationDisabled)
        return JukeAuthViewModel(session: sessionStore, authService: authService, configuration: config)
    }

    // MARK: - Initial State Tests

    func testInitialState() {
        let sessionStore = makeSessionStore()
        let viewModel = makeViewModel(session: sessionStore)

        XCTAssertEqual(viewModel.username, "")
        XCTAssertEqual(viewModel.email, "")
        XCTAssertEqual(viewModel.password, "")
        XCTAssertEqual(viewModel.passwordConfirm, "")
        XCTAssertFalse(viewModel.isRegistering)
        XCTAssertFalse(viewModel.isLoading)
        XCTAssertNil(viewModel.errorMessage)
        XCTAssertNil(viewModel.successMessage)
    }

    // MARK: - Mode Switching Tests

    func testSetModeToRegistering() {
        let sessionStore = makeSessionStore()
        let viewModel = makeViewModel(session: sessionStore)

        viewModel.setMode(registering: true)

        XCTAssertTrue(viewModel.isRegistering)
    }

    func testSetModeToLogin() {
        let sessionStore = makeSessionStore()
        let viewModel = makeViewModel(session: sessionStore)
        viewModel.setMode(registering: true)

        viewModel.setMode(registering: false)

        XCTAssertFalse(viewModel.isRegistering)
    }

    func testSetModeClearsMessages() {
        let sessionStore = makeSessionStore()
        let viewModel = makeViewModel(session: sessionStore)
        viewModel.errorMessage = "Some error"
        viewModel.successMessage = "Some success"

        viewModel.setMode(registering: true)

        XCTAssertNil(viewModel.errorMessage)
        XCTAssertNil(viewModel.successMessage)
    }

    // MARK: - Validation Tests

    func testSubmitEmptyUsername() async {
        let sessionStore = makeSessionStore()
        let viewModel = makeViewModel(session: sessionStore)
        viewModel.username = ""
        viewModel.password = "password123"

        await viewModel.submit()

        XCTAssertEqual(viewModel.errorMessage, "Username is required.")
    }

    func testSubmitWhitespaceUsername() async {
        let sessionStore = makeSessionStore()
        let viewModel = makeViewModel(session: sessionStore)
        viewModel.username = "   "
        viewModel.password = "password123"

        await viewModel.submit()

        XCTAssertEqual(viewModel.errorMessage, "Username is required.")
    }

    func testSubmitEmptyPassword() async {
        let sessionStore = makeSessionStore()
        let viewModel = makeViewModel(session: sessionStore)
        viewModel.username = "testuser"
        viewModel.password = ""

        await viewModel.submit()

        XCTAssertEqual(viewModel.errorMessage, "Password is required.")
    }

    // MARK: - Registration Validation Tests

    func testRegistrationMissingEmail() async {
        let sessionStore = makeSessionStore()
        let viewModel = makeViewModel(session: sessionStore)
        viewModel.setMode(registering: true)
        viewModel.username = "testuser"
        viewModel.email = ""
        viewModel.password = "password123"
        viewModel.passwordConfirm = "password123"

        await viewModel.submit()

        XCTAssertEqual(viewModel.errorMessage, "Email is required.")
    }

    func testRegistrationPasswordMismatch() async {
        let sessionStore = makeSessionStore()
        let viewModel = makeViewModel(session: sessionStore)
        viewModel.setMode(registering: true)
        viewModel.username = "testuser"
        viewModel.email = "test@example.com"
        viewModel.password = "password123"
        viewModel.passwordConfirm = "different"

        await viewModel.submit()

        XCTAssertEqual(viewModel.errorMessage, "Passwords do not match.")
    }

    func testRegistrationPasswordTooShort() async {
        let sessionStore = makeSessionStore()
        let viewModel = makeViewModel(session: sessionStore)
        viewModel.setMode(registering: true)
        viewModel.username = "testuser"
        viewModel.email = "test@example.com"
        viewModel.password = "short"
        viewModel.passwordConfirm = "short"

        await viewModel.submit()

        XCTAssertEqual(viewModel.errorMessage, "Password must be at least 8 characters.")
    }

    // MARK: - Login Success Test

    func testLoginSuccess() async {
        MockURLProtocol.requestHandler = { request in
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 200,
                httpVersion: nil,
                headerFields: nil
            )!

            let data: Data
            if request.url?.path.contains("api-auth-token") == true {
                data = """
                {"token": "testtoken123"}
                """.data(using: .utf8)!
            } else {
                // Profile request
                data = """
                {"id": 1, "username": "testuser", "is_owner": true}
                """.data(using: .utf8)!
            }
            return (response, data)
        }

        let sessionStore = makeSessionStore()
        let viewModel = makeViewModel(session: sessionStore)
        viewModel.username = "testuser"
        viewModel.password = "password123"

        await viewModel.submit()

        XCTAssertNil(viewModel.errorMessage)
        XCTAssertTrue(sessionStore.isAuthenticated)
        XCTAssertEqual(viewModel.password, "") // Should be cleared
    }

    // MARK: - Registration Disabled Tests

    func testRegistrationDisabledBlocksSetMode() {
        let viewModel = makeViewModel(registrationDisabled: true)

        viewModel.setMode(registering: true)

        XCTAssertFalse(viewModel.isRegistering)
        XCTAssertNotNil(viewModel.errorMessage)
    }

    func testIsRegistrationDisabled() {
        let viewModel = makeViewModel(registrationDisabled: true)

        XCTAssertTrue(viewModel.isRegistrationDisabled)
    }
}
