import XCTest
@testable import JukeKit

final class JukeAuthModelsTests: XCTestCase {

    // MARK: - Response Decoding Tests

    func testAuthTokenResponseDecoding() throws {
        let json = """
        {"token": "abc123xyz"}
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(JukeAuthTokenResponse.self, from: json)
        XCTAssertEqual(response.token, "abc123xyz")
    }

    func testRegisterResponseDecodingWithDetail() throws {
        let json = """
        {"detail": "Check your inbox to confirm your account."}
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(JukeRegisterResponse.self, from: json)
        XCTAssertEqual(response.detail, "Check your inbox to confirm your account.")
    }

    func testRegisterResponseDecodingWithoutDetail() throws {
        let json = """
        {}
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(JukeRegisterResponse.self, from: json)
        XCTAssertNil(response.detail)
    }

    func testVerifyResponseDecoding() throws {
        let json = """
        {"token": "newtoken123", "username": "testuser"}
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(JukeVerifyResponse.self, from: json)
        XCTAssertEqual(response.token, "newtoken123")
        XCTAssertEqual(response.username, "testuser")
    }

    func testVerifyResponseDecodingPartial() throws {
        let json = """
        {"username": "testuser"}
        """.data(using: .utf8)!

        let response = try JSONDecoder().decode(JukeVerifyResponse.self, from: json)
        XCTAssertNil(response.token)
        XCTAssertEqual(response.username, "testuser")
    }

    // MARK: - Request Encoding Tests

    func testLoginRequestEncoding() throws {
        let request = JukeLoginRequest(username: "testuser", password: "secret123")
        let data = try JSONEncoder().encode(request)
        let dict = try JSONSerialization.jsonObject(with: data) as! [String: String]

        XCTAssertEqual(dict["username"], "testuser")
        XCTAssertEqual(dict["password"], "secret123")
    }

    func testRegisterRequestEncoding() throws {
        let request = JukeRegisterRequest(
            username: "newuser",
            email: "new@example.com",
            password: "password123",
            passwordConfirm: "password123"
        )
        let data = try JSONEncoder().encode(request)
        let dict = try JSONSerialization.jsonObject(with: data) as! [String: String]

        XCTAssertEqual(dict["username"], "newuser")
        XCTAssertEqual(dict["email"], "new@example.com")
        XCTAssertEqual(dict["password"], "password123")
        XCTAssertEqual(dict["password_confirm"], "password123")
    }

    func testVerifyRegistrationRequestEncoding() throws {
        let request = JukeVerifyRegistrationRequest(
            userId: "123",
            timestamp: "1234567890",
            signature: "abc123sig"
        )
        let data = try JSONEncoder().encode(request)
        let dict = try JSONSerialization.jsonObject(with: data) as! [String: String]

        XCTAssertEqual(dict["user_id"], "123")
        XCTAssertEqual(dict["timestamp"], "1234567890")
        XCTAssertEqual(dict["signature"], "abc123sig")
    }

    func testResendVerificationRequestEncoding() throws {
        let request = JukeResendVerificationRequest(email: "user@example.com")
        let data = try JSONEncoder().encode(request)
        let dict = try JSONSerialization.jsonObject(with: data) as! [String: String]

        XCTAssertEqual(dict["email"], "user@example.com")
    }

    // MARK: - Init Tests

    func testAuthTokenResponseInit() {
        let response = JukeAuthTokenResponse(token: "mytoken")
        XCTAssertEqual(response.token, "mytoken")
    }

    func testRegisterResponseInit() {
        let response = JukeRegisterResponse(detail: "Success!")
        XCTAssertEqual(response.detail, "Success!")
    }

    func testVerifyResponseInit() {
        let response = JukeVerifyResponse(token: "token", username: "user")
        XCTAssertEqual(response.token, "token")
        XCTAssertEqual(response.username, "user")
    }
}
