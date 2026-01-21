import XCTest
@testable import ShotClock

final class ShotClockTests: XCTestCase {

    func testAPIClientBaseURL() {
        let client = APIClient(baseURL: "http://test.example.com")
        XCTAssertEqual(client.baseURL, "http://test.example.com")
    }

    func testUserProfilePreferredName_withDisplayName() {
        let profile = UserProfile(id: 1, username: "user1", displayName: "Display", bio: nil, avatarUrl: nil)
        XCTAssertEqual(profile.preferredName, "Display")
    }

    func testUserProfilePreferredName_withoutDisplayName() {
        let profile = UserProfile(id: 1, username: "user1", displayName: nil, bio: nil, avatarUrl: nil)
        XCTAssertEqual(profile.preferredName, "user1")
    }

    func testUserProfilePreferredName_emptyDisplayName() {
        let profile = UserProfile(id: 1, username: "user1", displayName: "", bio: nil, avatarUrl: nil)
        XCTAssertEqual(profile.preferredName, "user1")
    }

    func testLoginRequestEncoding() throws {
        let request = LoginRequest(username: "test", password: "pass123")
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(request)
        let dict = try JSONSerialization.jsonObject(with: data) as? [String: String]
        XCTAssertEqual(dict?["username"], "test")
        XCTAssertEqual(dict?["password"], "pass123")
    }

    func testRegisterRequestEncoding() throws {
        let request = RegisterRequest(username: "new", email: "a@b.com", password: "pass1234", passwordConfirm: "pass1234")
        let encoder = JSONEncoder()
        encoder.keyEncodingStrategy = .convertToSnakeCase
        let data = try encoder.encode(request)
        let dict = try JSONSerialization.jsonObject(with: data) as? [String: String]
        XCTAssertEqual(dict?["username"], "new")
        XCTAssertEqual(dict?["email"], "a@b.com")
        XCTAssertEqual(dict?["password_confirm"], "pass1234")
    }
}
