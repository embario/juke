import XCTest
@testable import JukeCore

final class JukeAuthServiceTests: XCTestCase {

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

    private var authService: JukeAuthService!
    private var session: URLSession!

    override func setUp() {
        super.setUp()
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockURLProtocol.self]
        session = URLSession(configuration: config)

        let apiConfig = JukeAPIConfiguration(baseURL: URL(string: "https://api.test.com")!)
        let apiClient = JukeAPIClient(configuration: apiConfig, session: session)
        authService = JukeAuthService(client: apiClient)
    }

    override func tearDown() {
        MockURLProtocol.requestHandler = nil
        authService = nil
        session = nil
        super.tearDown()
    }

    // MARK: - Login Tests

    func testLoginSuccess() async throws {
        MockURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertTrue(request.url?.path.contains("api-auth-token") ?? false)

            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 200,
                httpVersion: nil,
                headerFields: nil
            )!
            let data = """
            {"token": "testtoken123"}
            """.data(using: .utf8)!
            return (response, data)
        }

        let token = try await authService.login(username: "testuser", password: "testpass")
        XCTAssertEqual(token, "testtoken123")
    }

    func testLoginFailure() async {
        MockURLProtocol.requestHandler = { request in
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 401,
                httpVersion: nil,
                headerFields: nil
            )!
            let data = """
            {"detail": "Invalid credentials"}
            """.data(using: .utf8)!
            return (response, data)
        }

        do {
            _ = try await authService.login(username: "testuser", password: "wrongpass")
            XCTFail("Expected error")
        } catch let error as JukeAPIError {
            XCTAssertEqual(error, JukeAPIError.unauthorized)
        } catch {
            XCTFail("Unexpected error type: \(error)")
        }
    }

    // MARK: - Registration Tests

    func testRegisterSuccess() async throws {
        MockURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertTrue(request.url?.path.contains("register") ?? false)

            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 201,
                httpVersion: nil,
                headerFields: nil
            )!
            let data = """
            {"detail": "Check your inbox to confirm your account."}
            """.data(using: .utf8)!
            return (response, data)
        }

        let result = try await authService.register(
            username: "newuser",
            email: "new@example.com",
            password: "password123",
            passwordConfirm: "password123"
        )
        XCTAssertEqual(result.detail, "Check your inbox to confirm your account.")
    }

    func testRegisterFailure() async {
        MockURLProtocol.requestHandler = { request in
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 400,
                httpVersion: nil,
                headerFields: nil
            )!
            let data = """
            {"detail": "Username already exists"}
            """.data(using: .utf8)!
            return (response, data)
        }

        do {
            _ = try await authService.register(
                username: "existinguser",
                email: "existing@example.com",
                password: "password123",
                passwordConfirm: "password123"
            )
            XCTFail("Expected error")
        } catch let error as JukeAPIError {
            if case .server(let status, let message) = error {
                XCTAssertEqual(status, 400)
                XCTAssertEqual(message, "Username already exists")
            } else {
                XCTFail("Expected server error")
            }
        } catch {
            XCTFail("Unexpected error type: \(error)")
        }
    }

    // MARK: - Logout Tests

    func testLogoutSuccess() async throws {
        MockURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertTrue(request.url?.path.contains("logout") ?? false)
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Token mytoken")

            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 204,
                httpVersion: nil,
                headerFields: nil
            )!
            return (response, Data())
        }

        try await authService.logout(token: "mytoken")
        // Success - no error thrown
    }

    // MARK: - Verify Registration Tests

    func testVerifyRegistrationSuccess() async throws {
        MockURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertTrue(request.url?.path.contains("verify-registration") ?? false)

            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 200,
                httpVersion: nil,
                headerFields: nil
            )!
            let data = """
            {"token": "newtoken", "username": "verifieduser"}
            """.data(using: .utf8)!
            return (response, data)
        }

        let result = try await authService.verifyRegistration(
            userId: "123",
            timestamp: "1234567890",
            signature: "sig123"
        )
        XCTAssertEqual(result.token, "newtoken")
        XCTAssertEqual(result.username, "verifieduser")
    }

    // MARK: - Resend Verification Tests

    func testResendVerificationSuccess() async throws {
        MockURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            XCTAssertTrue(request.url?.path.contains("resend-registration") ?? false)

            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 200,
                httpVersion: nil,
                headerFields: nil
            )!
            let data = """
            {"detail": "Verification email sent."}
            """.data(using: .utf8)!
            return (response, data)
        }

        let result = try await authService.resendVerification(email: "user@example.com")
        XCTAssertEqual(result.detail, "Verification email sent.")
    }
}
