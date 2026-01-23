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

    func testAppConfigurationEnvOverridesPlist() {
        let config = AppConfiguration(
            env: ["DISABLE_REGISTRATION": "yes"],
            plistValue: "false"
        )

        XCTAssertTrue(config.isRegistrationDisabled)
    }

    func testAppConfigurationPlistBooleanFallback() {
        let config = AppConfiguration(
            env: [:],
            plistValue: true
        )

        XCTAssertTrue(config.isRegistrationDisabled)
    }

    func testResolveBaseURLUsesEnvironment() {
        let resolved = APIClient.resolveBaseURL(
            environment: ["BACKEND_URL": "http://env.example.com"],
            plistURL: "http://plist.example.com"
        )

        XCTAssertEqual(resolved, "http://env.example.com")
    }

    func testResolveBaseURLUsesPlistWhenEnvironmentMissing() {
        let resolved = APIClient.resolveBaseURL(
            environment: [:],
            plistURL: "http://plist.example.com"
        )

        XCTAssertEqual(resolved, "http://plist.example.com")
    }
}
