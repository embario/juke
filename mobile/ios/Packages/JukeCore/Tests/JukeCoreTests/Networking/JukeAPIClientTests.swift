import XCTest
@testable import JukeCore

final class JukeAPIClientTests: XCTestCase {

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

    private var client: JukeAPIClient!
    private var session: URLSession!

    override func setUp() {
        super.setUp()
        let config = URLSessionConfiguration.ephemeral
        config.protocolClasses = [MockURLProtocol.self]
        session = URLSession(configuration: config)

        let apiConfig = JukeAPIConfiguration(baseURL: URL(string: "https://api.test.com")!)
        client = JukeAPIClient(configuration: apiConfig, session: session)
    }

    override func tearDown() {
        MockURLProtocol.requestHandler = nil
        client = nil
        session = nil
        super.tearDown()
    }

    // MARK: - Tests

    func testGetRequest() async throws {
        struct TestResponse: Decodable {
            let message: String
        }

        MockURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.httpMethod, "GET")
            XCTAssertTrue(request.url?.path.contains("test") ?? false)
            XCTAssertEqual(request.value(forHTTPHeaderField: "Content-Type"), "application/json")

            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 200,
                httpVersion: nil,
                headerFields: nil
            )!
            let data = """
            {"message": "Hello"}
            """.data(using: .utf8)!
            return (response, data)
        }

        let response: TestResponse = try await client.get("/api/v1/test/")
        XCTAssertEqual(response.message, "Hello")
    }

    func testPostRequestWithBody() async throws {
        struct TestRequest: Encodable {
            let username: String
        }
        struct TestResponse: Decodable {
            let token: String
        }

        MockURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.httpMethod, "POST")
            // Body is set - verify via httpBodyStream or content-type
            XCTAssertEqual(request.value(forHTTPHeaderField: "Content-Type"), "application/json")

            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 200,
                httpVersion: nil,
                headerFields: nil
            )!
            let data = """
            {"token": "abc123"}
            """.data(using: .utf8)!
            return (response, data)
        }

        let response: TestResponse = try await client.post("/api/v1/auth/", body: TestRequest(username: "test"))
        XCTAssertEqual(response.token, "abc123")
    }

    func testAuthorizationHeader() async throws {
        struct TestResponse: Decodable {}

        MockURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.value(forHTTPHeaderField: "Authorization"), "Token mytoken123")

            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 200,
                httpVersion: nil,
                headerFields: nil
            )!
            return (response, "{}".data(using: .utf8)!)
        }

        let _: TestResponse = try await client.get("/api/v1/protected/", token: "mytoken123")
    }

    func testUnauthorizedError() async throws {
        struct TestResponse: Decodable {}

        MockURLProtocol.requestHandler = { request in
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 401,
                httpVersion: nil,
                headerFields: nil
            )!
            return (response, "{}".data(using: .utf8)!)
        }

        do {
            let _: TestResponse = try await client.get("/api/v1/protected/")
            XCTFail("Expected unauthorized error")
        } catch let error as JukeAPIError {
            XCTAssertEqual(error, JukeAPIError.unauthorized)
        }
    }

    func testServerError() async throws {
        struct TestResponse: Decodable {}

        MockURLProtocol.requestHandler = { request in
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 500,
                httpVersion: nil,
                headerFields: nil
            )!
            let data = """
            {"detail": "Internal server error"}
            """.data(using: .utf8)!
            return (response, data)
        }

        do {
            let _: TestResponse = try await client.get("/api/v1/test/")
            XCTFail("Expected server error")
        } catch let error as JukeAPIError {
            if case .server(let status, let message) = error {
                XCTAssertEqual(status, 500)
                XCTAssertEqual(message, "Internal server error")
            } else {
                XCTFail("Expected server error")
            }
        }
    }

    func testEmptyResponseHandledAsEmptyObject() async throws {
        struct TestResponse: Decodable {}

        MockURLProtocol.requestHandler = { request in
            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 204,
                httpVersion: nil,
                headerFields: nil
            )!
            return (response, Data())
        }

        let _: TestResponse = try await client.get("/api/v1/test/")
        // Should not throw - empty responses are handled
    }

    func testQueryParameters() async throws {
        struct TestResponse: Decodable {}

        MockURLProtocol.requestHandler = { request in
            let components = URLComponents(url: request.url!, resolvingAgainstBaseURL: false)
            let queryItems = components?.queryItems ?? []
            XCTAssertTrue(queryItems.contains(where: { $0.name == "search" && $0.value == "hello" }))

            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 200,
                httpVersion: nil,
                headerFields: nil
            )!
            return (response, "{}".data(using: .utf8)!)
        }

        let _: TestResponse = try await client.get(
            "/api/v1/test/",
            queryItems: [URLQueryItem(name: "search", value: "hello")]
        )
    }

    func testDeleteRequest() async throws {
        MockURLProtocol.requestHandler = { request in
            XCTAssertEqual(request.httpMethod, "DELETE")

            let response = HTTPURLResponse(
                url: request.url!,
                statusCode: 204,
                httpVersion: nil,
                headerFields: nil
            )!
            return (response, Data())
        }

        try await client.delete("/api/v1/resource/1/")
    }

    func testBaseURLAccessor() {
        XCTAssertEqual(client.baseURL.absoluteString, "https://api.test.com")
    }
}
